# Plan d'implémentation — Étape 12c : self-consistency (vote majoritaire)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter `consistency_k` à `run_agent` : k>1 → k sous-runs en parallèle (`asyncio.gather`), vote majoritaire sur la réponse finale (texte normalisé, ex-aequo → confiance la plus haute), métrique `consensus`, tracé SSE `consensus` + step base dans le run gagnant.

**Architecture:** Le corps actuel de `run_agent` est extrait en `_run_once(...) -> AgentResult` (inchangé fonctionnellement, plus `run_id` renseigné). `run_agent` devient un wrapper : validation des modes, k=1 → `_run_once` direct (rétrocompat totale) ; k>1 → gather de k `_run_once` (chacun avec son propre run en base, `event_sink=None` pour ne pas entremêler le chat), vote via `reasoning.vote()`, event `consensus` + step `consensus` dans le run gagnant. `llm_factory(i)` permet des LLM différents par sous-run (mock). `consistency_k>1` + `approval_registry` → `ValueError` (non supporté en v1). Zéro dépendance nouvelle.

**Tech Stack:** Python 3.12+, asyncio.gather, pytest (asyncio_mode=auto), dataclasses. Mock déterministe, zéro réseau.

**Spec:** `docs/specs/12c-self-consistency.md` (validée le 08/11/2026)

## Global Constraints

- Zéro dépendance nouvelle ; aucun secret dans le code.
- Rétrocompatible : `consistency_k=1` (défaut) = comportement actuel identique, mêmes events SSE, mêmes steps, coût identique.
- TDD strict : test qui échoue → code minimal → vert, par tâche.
- Vote déterministe (pas d'aléatoire) : normalisation minuscules/espaces ; ex-aequo → confiance (section « Confiance ») la plus haute ; encore ex-aequo → premier run.
- Coût total = somme des k sous-runs. En live, k>1 est opt-in (coûte k fois plus cher).
- Validation : `cd backend && uv run pytest -q -m "not integration"`, `uv run ruff check .`, `uv run ty check`, evals mock.

## Review Focus

- k=1 doit être strictement identique à aujourd'hui (events, steps, ordre, coût) — test de non-régression sur la suite existante.
- Le vote ne porte que sur la réponse finale, jamais sur les tool_calls intermédiaires.
- `consensus_k < 1` → ValueError. `consistency_k>1` + `approval_registry` → ValueError.
- En k>1, les sous-runs tracent chacun en base (run_id propre) mais n'émettent pas de SSE (sink=None) ; le parent émet start/consensus/answer/done.
- `vote([])` ne doit jamais être appelé (k>=1 garanti) mais retourner (0, 1.0) par garde-fou.

---

### Task 1: `reasoning.py` — normalize_answer, extract_confidence, vote (fonctions pures)

**Files:**
- Modify: `backend/src/investia/agent/reasoning.py`
- Create: `backend/tests/test_reasoning_consistency.py`

**Interfaces:**
- Produces: `normalize_answer(text: str) -> str` ; `extract_confidence(text: str) -> int` (0 si absente) ; `vote(answers: list[str]) -> tuple[int, float]` (index gagnant, consensus).

- [ ] **Step 1: Write failing tests**:
  - `test_vote_majoritaire` : `vote(["A", "a ", "B"])` → (0, 2/3) (normalisation casse/espaces).
  - `test_vote_ex_aequo_confiance` : trois textes différents, le 2e a « ## Confiance\n90 », les autres 50 → gagnant index 1, consensus 1/3.
  - `test_vote_ex_aequo_sans_confiance_premier_gagne` : A,B,C sans section confiance → (0, 1/3).
  - `test_vote_un_seul` : `vote(["x"])` → (0, 1.0) ; `vote([])` → (0, 1.0) (garde-fou).
  - `test_extract_confidence` : extrait 80 de "## Confiance\n80" ; 0 si absent.
- [ ] **Step 2: Run** `cd backend && uv run pytest tests/test_reasoning_consistency.py -q` → FAIL (import).
- [ ] **Step 3: Implement** fonctions pures dans `reasoning.py` (regex confiance `##?\s*confiance\s*[:#]?\s*(\d+)`, insensible à la casse).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(12c): vote majoritaire (normalize/extract_confidence/vote, TDD)`.

### Task 2: Boucle — `_run_once` + wrapper `run_agent(consistency_k, llm_factory)` + event/step `consensus`

**Files:**
- Modify: `backend/src/investia/agent/loop.py`
- Modify: `backend/tests/test_reasoning_consistency.py`

**Interfaces:**
- Consumes: `vote` from Task 1.
- Produces: `run_agent(..., reasoning="none", consistency_k=1, llm_factory=None)` ; `_run_once(...) -> AgentResult` (corps actuel, + `run_id` renseigné) ; `AgentResult.run_id: str | None`, `.consensus: float = 1.0`, `.answers: list[str]`.

- [ ] **Step 1: Write failing tests**:
  - `test_k1_comportement_identique` : k=1 (défaut) → 1 seul run, `result.consensus == 1.0`, `result.answers == []`, events identiques à avant (start, llm_call, tool_call, answer, done), coût identique.
  - `test_k3_vote_majoritaire` : `llm_factory` rendant 3 FakeLlm avec réponses finales A, A, B ; k=3 → `result.consensus == pytest.approx(2/3)`, `result.answers` length 3, `result.answer == A`, event `consensus` émis (sink parent), step `consensus` loggé dans le run gagnant (store), coût = somme des 3.
  - `test_k3_llm_factory_recoit_index` : factory enregistre les index appelés → [0, 1, 2].
  - `test_k_invalide_rejete` : consistency_k=0 → ValueError.
  - `test_k3_avec_approval_rejete` : consistency_k=3 + approval_registry → ValueError.
  - `test_k3_sans_factory_meme_llm` : k=3 sans factory → le même FakeLlm est utilisé 3 fois (compteur d'appels = 3 x appels d'un run).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** : extraire le corps de `run_agent` dans `_run_once` (mêmes paramètres + `modes: set[str]` ; renseigne `run_id` dans l'AgentResult) ; `run_agent` wrapper : parse modes, valide k, k=1 → `_run_once` avec sink/store tels quels ; k>1 → `asyncio.gather` de k `_run_once` avec `event_sink=None` (store conservé, run_id propre), puis `vote`, event `consensus` via sink parent + `store.log_step(winner.run_id, 0, "consensus", {"k": k, "winner": index, "scores": [...], "answers": [...]})`, retourne `dataclasses.replace(winner, consensus=consensus, answers=[r.answer for r in results])` ; émet aussi answer/done du gagnant. `llm_factory` : client = llm_factory(i) if llm_factory else llm.
- [ ] **Step 4: Run** `uv run pytest tests/test_reasoning_consistency.py -q` → PASS ; non-régression `uv run pytest tests/test_reasoning_plan.py tests/test_reasoning_reflect.py tests/test_agent_loop.py tests/test_agent_guardrails.py tests/test_agent_approval.py -q` → PASS.
- [ ] **Step 5: Commit** `feat(12c): self-consistency — k runs parallèles + vote (TDD)`.

### Task 3: Métrique `consensus`

**Files:**
- Modify: `backend/src/investia/evals/metrics.py`
- Modify: `backend/tests/test_evals.py`

- [ ] **Step 1:** test `test_metrics_consensus` : AgentResult par défaut → consensus 1.0 ; avec consensus=2/3 → 0.667.
- [ ] **Step 2:** Run → FAIL (KeyError).
- [ ] **Step 3:** Implement `"consensus": result.consensus`.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat(12c): métrique consensus (TDD)`.

### Task 4: Runner — `consistency_k` + `mock_variants` par cas + 2 cas YAML

**Files:**
- Modify: `backend/src/investia/evals/runner.py`
- Modify: `evals/cases.yaml`
- Modify: `backend/tests/test_evals.py`

**Interfaces:**
- Consumes: Task 2, Task 3.
- Produces: `EvalCase.consistency_k: int = 1`, `EvalCase.mock_variants: list[list[Any]] | None` ; `run_evals` construit une `llm_factory` rendant un `MockLlm` par variante quand `consistency_k > 1`.

- [ ] **Step 1:** test `test_run_evals_consensus_fort_et_unanime` : deux cas k=3 avec `mock_variants` [A,A,B] et [A,A,A] → consensus ≈ 2/3 et 1.0, tool_used 1.0.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement runner + 2 cas YAML (`consensus-fort`, `consensus-unanime` — réponses conformes aux garde-fous, A et B deux formulations différentes sourcées 344.63).
- [ ] **Step 4:** Run `uv run pytest tests/test_evals.py -q` → PASS ; evals mock complet → `consensus` affiché.
- [ ] **Step 5:** Commit `feat(12c): cas d'evals consensus-fort / consensus-unanime (TDD)`.

### Task 5: Validation globale + docs

- [ ] **Step 1:** `cd backend && uv run pytest -q -m "not integration"` → vert ; `uv run ruff check .` ; `uv run ty check` → propres.
- [ ] **Step 2:** `cd dashboard && npm run test` → verts (event `consensus` inconnu toléré).
- [ ] **Step 3:** `docs/STATUS.md` (12c terminée), `docs/08-roadmap.md` (12c cochée), `docs/09-decisions.md` (D71 + historique).
- [ ] **Step 4:** Commit docs.
