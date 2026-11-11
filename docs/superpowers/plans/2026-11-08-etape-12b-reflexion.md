# Plan d'implémentation — Étape 12b : réflexion (auto-critique)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter le mode `reasoning="reflect"` (et `"plan+reflect"`) à la boucle : chaque réponse finale candidate passe par une auto-critique LLM (JSON ok/problèmes) avant les garde-fous, tracée en SSE/base, notée par les métriques `reflexion` et `auto_corrections`.

**Architecture:** `agent/reasoning.py` gagne `ReflectionDecision` / `parse_reflection` / `reflect()` (appel LLM dédié, sorties d'outils tronquées, parsing en douceur → ok=True si illisible). La boucle appelle `reflect()` avant `run_all_checks` quand le mode reflect est actif ; une critique négative s'ajoute aux `failed` (mécanisme de correction existant). Les garde-fous en code restent l'autorité finale. Zéro dépendance nouvelle.

**Tech Stack:** Python 3.12+, pytest + pytest-asyncio (asyncio_mode=auto), dataclasses. Mock déterministe, zéro réseau.

**Spec:** `docs/specs/12b-reflexion.md` (validée le 08/11/2026)

## Global Constraints

- Zéro dépendance nouvelle ; aucun secret dans le code.
- Rétrocompatible : `"none"` (défaut) et `"plan"` inchangés ; `"reflect"`, `"plan+reflect"` nouveaux ; toute autre valeur → `ValueError`.
- TDD strict : test qui échoue → code minimal → vert, par tâche.
- Parsing de la critique en douceur : JSON illisible → `ok=True` (la réflexion ne bloque jamais seule).
- Coût des appels de réflexion compté dans `total_cost_cents`.
- Validation : `cd backend && uv run pytest -q -m "not integration"`, `uv run ruff check .`, `uv run ty check`, evals mock.

## Review Focus

- Une critique illisible ne doit jamais bloquer le run (ok=True par défaut).
- La réflexion ne peut pas débloquer une réponse bloquée par les garde-fous en code (failed = checks + réflexion).
- Le coût de la réflexion est compté ; l'event SSE `reflection` ne casse pas le dashboard (110 tests existants verts).
- `auto_corrections` compte les passes négatives ; `reflexion` = 1.0 si au moins une passe a eu lieu.
- MockLlm : `mock_responses` (séquence ordonnée) doit rester rétrocompatible avec `mock_plan`/`mock_tool_call`/`mock_final`.

---

### Task 1: `reasoning.py` — ReflectionDecision, parse_reflection, reflect + REFLECT_PROMPT

**Files:**
- Modify: `backend/src/investia/agent/reasoning.py`
- Modify: `backend/src/investia/agent/prompts.py` (+ `REFLECT_PROMPT`)
- Create: `backend/tests/test_reasoning_reflect.py`

**Interfaces:**
- Produces: `ReflectionDecision(ok: bool, problemes: list[str])` ; `parse_reflection(text: str) -> ReflectionDecision` ; `async reflect(llm: LlmChat, model_key: str, answer: str, tool_outputs: list[str]) -> tuple[ReflectionDecision, float]`.

- [ ] **Step 1: Write failing tests** in `backend/tests/test_reasoning_reflect.py` (réutiliser le `FakeLlm` de `test_reasoning_plan.py` — le copier localement, même pattern) :
  - `test_parse_reflection_valid` : `'{"ok": false, "problemes": ["chiffre non sourcé"]}'` → ok=False, 1 problème.
  - `test_parse_reflection_invalid_returns_ok_true` : `"pas du json"` → ok=True, problemes=[] (dégradé propre).
  - `test_reflect_calls_llm_once_truncates_outputs_and_returns_cost` : FakeLlm 1 réponse `{"ok": true, "problemes": []}` cost 0.02 ; `tool_outputs` avec une grosse string (10 000 car.) → `llm.calls[0]["messages"]` contient une version tronquée (< 5000 car.) ; retour (ok=True, 0.02) ; `tools=None`.
- [ ] **Step 2: Run** `cd backend && uv run pytest tests/test_reasoning_reflect.py -q` → FAIL (import).
- [ ] **Step 3: Implement** : `REFLECT_PROMPT` (JSON strict `{"ok": bool, "problemes": [...]}`, ne juger que des problèmes objectifs : chiffre absent des sorties d'outils, section manquante, langage interdit, disclaimer manquant) ; `parse_reflection` (extrait {..}, défaut ok=True) ; `reflect()` joint les sorties d'outils tronquées à 4000 car. dans le message user.
- [ ] **Step 4: Run tests** → PASS.
- [ ] **Step 5: Commit** `feat(12b): reflect() — auto-critique LLM (TDD)`.

### Task 2: Boucle `loop.py` — modes reflect/plan+reflect, event/step `reflection`, `AgentResult.reflections`

**Files:**
- Modify: `backend/src/investia/agent/loop.py`
- Modify: `backend/tests/test_reasoning_reflect.py`

**Interfaces:**
- Consumes: `reflect`, `ReflectionDecision` from Task 1.
- Produces: `run_agent(..., reasoning: str = "none")` accepte `"none" | "plan" | "reflect" | "plan+reflect"` ; `AgentResult.reflections: list[ReflectionDecision]`.

- [ ] **Step 1: Write failing tests**:
  - `test_mode_reflect_emits_event_logs_step_counts_cost` : reasoning="reflect", FakeLlm([tool_call, final_ok, reflect_ok cost 0.02]) + sink + store → event `reflection` émis (ok=True), step `reflection` loggé, `result.reflections` length 1, coût total = 0.01+0.01+0.02.
  - `test_mode_reflect_ko_triggers_correction_then_ok` : FakeLlm([tool_call, final_bogueux, reflect_ko, final_ok, reflect_ok]) → statut final ok, `result.reflections` = [ko, ok], le message de correction envoyé au modèle contient "reflection".
  - `test_mode_plan_reflect_combine` : reasoning="plan+reflect" avec [plan_json, tool_call, final, reflect_ok] → plan + reflection présents.
  - `test_mode_inconnu_rejetee` : reasoning="plan+bidule" → ValueError.
  - `test_mode_none_aucune_reflection` : reasoning="none" → `result.reflections == []`, 2 appels LLM seulement.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** : parsing des modes (`set(reasoning.split("+"))`, validation contre `{"none","plan","reflect"}` avec règle « none » exclusif) ; champ `reflections` dans AgentResult (et passage dans les 3 constructeurs) ; dans la branche réponse finale, AVANT `run_all_checks`, si `"reflect" in modes` : `decision, c = await reflect(llm, model_key, response.content, tool_outputs)`, `total_cost += c`, `reflections.append(decision)`, emit + log_step, et si `not decision.ok` → `failed.append(("reflection", ...))` (failed calculé après les checks ; l'ordre d'évaluation reflect-then-checks ne change que l'ordre des events).
- [ ] **Step 4: Run** `uv run pytest tests/test_reasoning_reflect.py tests/test_reasoning_plan.py -q` → PASS ; non-régression : `uv run pytest tests/test_agent_loop.py tests/test_agent_guardrails.py tests/test_agent_approval.py -q` → PASS.
- [ ] **Step 5: Commit** `feat(12b): boucle — modes reflect/plan+reflect, event SSE + step reflection (TDD)`.

### Task 3: Métriques `reflexion` et `auto_corrections`

**Files:**
- Modify: `backend/src/investia/evals/metrics.py`
- Modify: `backend/tests/test_evals.py`

- [ ] **Step 1: Write failing tests**: `test_metrics_reflexion` (AgentResult avec reflections=[ok] → reflexion=1.0, auto_corrections=0.0 ; avec [ko, ok] → auto_corrections=1.0 ; sans reflections → reflexion=0.0, auto_corrections=0.0).
- [ ] **Step 2: Run** → FAIL (KeyError).
- [ ] **Step 3: Implement** dans `compute_metrics`.
- [ ] **Step 4: Run** `uv run pytest tests/test_evals.py -q` → PASS.
- [ ] **Step 5: Commit** `feat(12b): métriques reflexion / auto_corrections (TDD)`.

### Task 4: Runner — `mock_responses` + `reasoning` par cas + 2 nouveaux cas YAML

**Files:**
- Modify: `backend/src/investia/evals/runner.py`
- Modify: `evals/cases.yaml`
- Modify: `backend/tests/test_evals.py` (ou `test_reasoning_reflect.py`)

**Interfaces:**
- Consumes: Task 2, Task 3.
- Produces: `EvalCase.mock_responses: list | None`, `EvalCase.reasoning: str | None` ; `MockLlm` construit sa file depuis `mock_responses` si présent (élément `{"tool_call": {...}}` → réponse avec tool_calls ; élément string → content), sinon depuis `mock_plan`/`mock_tool_call`/`mock_final` (rétrocompat) ; `run_evals` passe `reasoning=case.reasoning or ("plan" if case.mock_plan else "none")`.

- [ ] **Step 1: Write failing test**: `test_run_evals_reflexion_ok_et_corrige` — deux EvalCase avec `mock_responses` (séquences ci-dessus) et `reasoning="reflect"` → `reflexion-ok` : reflexion=1.0, auto_corrections=0.0 ; `reflexion-corrige` : auto_corrections=1.0, statut ok, tool_used=1.0.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** runner + 2 cas dans `evals/cases.yaml` (`reflexion-ok`, `reflexion-corrige` — le candidat bogueux contient un chiffre inventé 999999, la réflexion le signale, la réponse corrigée cite 344.63 sourcé).
- [ ] **Step 4: Run** `uv run pytest tests/test_evals.py -q` → PASS ; puis evals mock complet : `uv run python -c "import asyncio; from investia.evals import load_cases, run_evals; s=asyncio.run(run_evals(load_cases(), mode='mock')); [print(r['case_id'], {k: round(v,3) for k,v in r['metrics'].items()}) for r in s['results']]"` → affiche reflexion/auto_corrections.
- [ ] **Step 5: Commit** `feat(12b): cas d'evals reflexion-ok / reflexion-corrige (TDD)`.

### Task 5: Validation globale + docs

- [ ] **Step 1:** `cd backend && uv run pytest -q -m "not integration"` → vert ; `uv run ruff check .` ; `uv run ty check` → propres.
- [ ] **Step 2:** `cd dashboard && npm run test` → 110 tests verts (event `reflection` inconnu toléré, aucun changement frontend).
- [ ] **Step 3:** `docs/STATUS.md` (12b terminée), `docs/08-roadmap.md` (12b cochée), `docs/09-decisions.md` (D70 + historique).
- [ ] **Step 4:** Commit docs.
