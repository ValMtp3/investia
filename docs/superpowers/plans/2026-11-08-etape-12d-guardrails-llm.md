# Plan d'implémentation — Étape 12d : guardrails LLM en renfort (elephant-1 + logprobs)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deux nouveaux garde-fous LLM en renfort des garde-fous en code, jamais à leur place : `safety_llm` (elephant-1 via `DecisionClient.decide`, bloque si proba unsafe ≥ 0,7 et confiance ≥ 0,6) et `safety_logprobs` (LLM-as-Jev : LLM chat répond Oui/Non avec `logprobs=True`, bloque si P(Non) ≥ 0,7). Tracés comme les autres checks, métriques `safety_llm_ok` / `safety_logprobs_ok`.

**Architecture:** `llm/client.py` gagne `chat(logprobs=False)` + `LlmResponse.first_token_logprobs` (softmax des top_logprobs du 1er token). Nouveau `guardrails/llm_check.py` avec `check_safety_llm` (fonction `decide` injectée, erreur → ok=True) et `check_safety_logprobs` (appelle `llm.chat(..., logprobs=True, temperature=0.0)`). La boucle accepte `decision_client=None` / `logprobs_guardrail=False` et ajoute les checks après `run_all_checks`. Zéro dépendance nouvelle.

**Tech Stack:** Python 3.12+, pytest (asyncio_mode=auto), httpx.MockTransport pour les tests client. Mock déterministe, zéro réseau.

**Spec:** `docs/specs/12d-guardrails-llm.md` (validée le 08/11/2026)

## Global Constraints

- Zéro dépendance nouvelle ; aucun secret dans le code.
- Rétrocompatible : sans `decision_client` ni `logprobs_guardrail`, aucun appel LLM supplémentaire, comportement identique.
- Les checks LLM s'ajoutent aux checks en code dans le même `failed` ; un « safe » LLM ne débloque jamais un échec code.
- Dégradé propre : erreur du client de décision ou logprobs absents → ok=True avec détail « indisponible », jamais de crash.
- Seuils en constantes nommées : `UNSAFE_BLOCK_THRESHOLD = 0.7`, `MIN_CONFIDENCE = 0.6`, `NON_BLOCK_THRESHOLD = 0.7`.
- TDD strict par tâche. Validation : `cd backend && uv run pytest -q -m "not integration"`, `uv run ruff check .`, `uv run ty check`, evals mock.

## Review Focus

- Un check LLM en erreur ne bloque jamais (ok=True) et ne fait jamais planter le run.
- `first_token_logprobs` doit être normalisé (somme ≈ 1) ; sans logprobs dans la réponse → None → check passe.
- Le protocole `LlmChat.chat` gagne `logprobs: bool = False` : tous les fakes de test (FakeLlm, MockLlm) doivent accepter le kwarg.
- En k>1 (12c), les nouveaux paramètres sont aussi transmis aux sous-runs.

---

### Task 1: `llm/client.py` — `chat(logprobs=...)` + `first_token_logprobs`

**Files:**
- Modify: `backend/src/investia/llm/client.py`
- Modify: `backend/tests/test_llm.py`

**Interfaces:**
- Produces: `LlmResponse.first_token_logprobs: dict[str, float] | None` (None si non demandé/absent) ; `LlmClient.chat(..., logprobs: bool = False)`.

- [ ] **Step 1: Write failing tests** in `test_llm.py` (style MockTransport existant) :
  - `test_chat_logprobs_parsed_and_normalized` : handler renvoie un payload avec `choices[0].logprobs.content[0] = {"token": "Non", "logprob": -0.1, "top_logprobs": [{"token": "Non", "logprob": -0.1}, {"token": "Oui", "logprob": -2.3}]}` ; `chat("small", msgs, logprobs=True)` → `first_token_logprobs` somme ≈ 1.0, "Non" > "Oui" ; le payload de la requête contient `"logprobs": true`.
  - `test_chat_sans_logprobs_renvoie_none` : appel par défaut → `first_token_logprobs is None` et le payload ne contient pas `logprobs`.
- [ ] **Step 2: Run** `uv run pytest tests/test_llm.py -q -k logprobs` → FAIL.
- [ ] **Step 3: Implement** : champ sur `LlmResponse` ; paramètre `logprobs` sur `chat` ; payload `logprobs: True, top_logprobs: 5` si demandé ; parsing + softmax (math.exp) des top_logprobs du 1er token.
- [ ] **Step 4: Run** `uv run pytest tests/test_llm.py -q` → PASS.
- [ ] **Step 5: Commit** `feat(12d): client LLM — chat(logprobs=True) + first_token_logprobs (TDD)`.

### Task 2: `guardrails/llm_check.py` — check_safety_llm + check_safety_logprobs

**Files:**
- Create: `backend/src/investia/guardrails/llm_check.py`
- Modify: `backend/src/investia/guardrails/__init__.py`
- Create: `backend/tests/test_guardrails_llm.py`

**Interfaces:**
- Produces: `UNSAFE_BLOCK_THRESHOLD`, `MIN_CONFIDENCE`, `NON_BLOCK_THRESHOLD` ; `async check_safety_llm(answer, decide) -> CheckResult` ; `async check_safety_logprobs(answer, llm, model_key) -> CheckResult` ; `LOGPROBS_PROMPT`.

- [ ] **Step 1: Write failing tests** in `test_guardrails_llm.py` :
  - `test_safety_llm_bloque_si_unsafe_confiant` : decide renvoie DecisionAnswer(value="unsafe", probabilities={"unsafe": 0.9}, confidence=0.95) → ok=False.
  - `test_safety_llm_passe_si_confiance_basse` : unsafe 0.9, confiance 0.3 → ok=True.
  - `test_safety_llm_passe_si_safe` : safe 0.95 → ok=True.
  - `test_safety_llm_erreur_indisponible` : decide lève → ok=True, detail contient « indisponible ».
  - `test_safety_logprobs_bloque_si_non_probable` : FakeLlm rend `LlmResponse(content="Non", first_token_logprobs={"Non": 0.98, "Oui": 0.02}, ...)` quand logprobs=True → ok=False ; et l'appel a bien `logprobs=True, tools=None, temperature=0.0`.
  - `test_safety_logprobs_passe_si_oui` : {"Oui": 0.9, "Non": 0.1} → ok=True.
  - `test_safety_logprobs_sans_logprobs_indisponible` : first_token_logprobs=None → ok=True « indisponible ».
- [ ] **Step 2: Run** → FAIL (import).
- [ ] **Step 3: Implement** `llm_check.py` : questions elephant `{"safety": {"type": "choice", "instructions": "...", "criteria": {"safe": "...", "unsafe": "..."}}}` ; logprobs : prompt Oui/Non strict, `chat(model_key, msgs, tools=None, temperature=0.0, logprobs=True)`, P(Non) = somme des proba des tokens commençant par « non » / (oui+non), insensible à la casse.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(12d): checks safety_llm (elephant) + safety_logprobs (LLM-as-Jev) (TDD)`.

### Task 3: Boucle — protocole `logprobs`, paramètres `decision_client` / `logprobs_guardrail`

**Files:**
- Modify: `backend/src/investia/agent/loop.py`
- Modify: `backend/tests/test_guardrails_llm.py`

**Interfaces:**
- Consumes: Task 1, Task 2.
- Produces: `LlmChat.chat(..., logprobs: bool = False)` ; `run_agent(..., decision_client=None, logprobs_guardrail=False)` (wrapper + `_run_once`, transmis aussi aux sous-runs k>1).

- [ ] **Step 1: Write failing tests**:
  - `test_boucle_safety_llm_present_avec_decision_client` : FakeDecisionClient safe + run_agent(decision_client=...) → `safety_llm` dans guardrails, event guardrail émis, step loggé, statut ok.
  - `test_boucle_safety_llm_bloque_si_unsafe` : unsafe → après corrections, statut blocked, guardrails contient safety_llm ok=False.
  - `test_boucle_safety_logprobs_avec_flag` : logprobs_guardrail=True, FakeLlm rend logprobs {"Non": 0.98} → bloqué ; sans flag → pas de check safety_logprobs, aucun appel avec logprobs=True.
  - `test_sans_rien_aucun_check_llm` : défaut → guardrails sans safety_llm/safety_logprobs, FakeLlm.calls aucun avec logprobs=True.
  - `test_k3_transmet_les_guardrails_llm` : k=3 + logprobs_guardrail=True → chaque sous-run a fait un appel logprobs=True.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** : protocol `LlmChat.chat` + `logprobs` ; wrapper et `_run_once` gagnent les 2 paramètres (transmis au gather) ; dans `_run_once` après `run_all_checks` : `if decision_client is not None: checks.append(("safety_llm", await check_safety_llm(response.content, decision_client.decide)))` ; `if logprobs_guardrail: checks.append(("safety_logprobs", await check_safety_logprobs(response.content, llm, model_key)))` — avant `guardrails.extend` pour qu'ils soient tracés/émis comme les autres. Tous les FakeLlm des tests existants doivent accepter `logprobs` (kwarg avec défaut, ils ont `tools=None` signé — vérifier et ajouter `logprobs=False` aux signatures FakeLlm/MockLlm).
- [ ] **Step 4: Run** `uv run pytest tests/test_guardrails_llm.py tests/test_reasoning_consistency.py tests/test_reasoning_plan.py tests/test_reasoning_reflect.py tests/test_agent_loop.py tests/test_evals.py -q` → PASS.
- [ ] **Step 5: Commit** `feat(12d): boucle — checks safety_llm / safety_logprobs en renfort (TDD)`.

### Task 4: Métriques + runner + 3 cas YAML

**Files:**
- Modify: `backend/src/investia/evals/metrics.py`
- Modify: `backend/src/investia/evals/runner.py` (+ `FakeDecisionClient`, MockLlm rend `mock_logprobs` quand `logprobs=True`)
- Modify: `evals/cases.yaml`
- Modify: `backend/tests/test_guardrails_llm.py` (ou test_evals.py)

- [ ] **Step 1: Write failing tests**: métriques (`safety_llm_ok`/`safety_logprobs_ok` selon guardrails) + `test_run_evals_safety_ok_unsafe_logprobs` : 3 cas (`safety-ok` mock_decision safe ; `safety-unsafe` unsafe 0.9/0.95 ; `logprobs-unsafe` mock_logprobs {"Non": 0.98, "Oui": 0.02}) → ok / blocked+safety_llm_ok=0 / blocked+safety_logprobs_ok=0.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** metrics + runner (`EvalCase.mock_decision`, `mock_logprobs` ; `run_evals` passe `decision_client=FakeDecisionClient(case) if case.mock_decision else None`, `logprobs_guardrail=bool(case.mock_logprobs)`) + 3 cas YAML.
- [ ] **Step 4: Run** `uv run pytest tests/test_evals.py tests/test_guardrails_llm.py -q` → PASS ; evals mock complet → métriques visibles.
- [ ] **Step 5: Commit** `feat(12d): métriques + cas evals safety-ok / safety-unsafe / logprobs-unsafe (TDD)`.

### Task 5: Validation globale + docs

- [ ] **Step 1:** `cd backend && uv run pytest -q -m "not integration"` → vert ; `uv run ruff check .` ; `uv run ty check` → propres.
- [ ] **Step 2:** `cd dashboard && npm run test` → 110 tests verts.
- [ ] **Step 3:** `docs/STATUS.md` (12d terminée), `docs/08-roadmap.md` (12d cochée), `docs/09-decisions.md` (D72 + historique).
- [ ] **Step 4:** Commit docs.
