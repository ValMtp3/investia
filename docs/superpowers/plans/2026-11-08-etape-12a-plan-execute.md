# Plan d'implémentation — Étape 12a : plan-and-execute

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un mode `reasoning="plan"` à la boucle d'agent : plan JSON produit par un appel LLM dédié en début de run, tracé en SSE + base, et métrique d'eval `plan_suivi` qui vérifie que les outils appelés suivent le plan.

**Architecture:** Nouveau module `agent/reasoning.py` (`PlanStep`, `parse_plan`, `make_plan`) appelé par `run_agent` quand `reasoning="plan"` ; le plan est émis (event SSE `plan`), loggé (step `plan`), stocké dans `AgentResult.plan` et noté par `compute_metrics`. Défaut `reasoning="none"` = comportement actuel inchangé. Zéro dépendance nouvelle.

**Tech Stack:** Python 3.12+, pytest + pytest-asyncio, dataclasses, uv/ruff/ty existants. Mock déterministe (FakeLlm/MockLlm), zéro réseau.

**Spec:** `docs/specs/12a-plan-execute.md` (validée le 08/11/2026)

## Global Constraints

- Zéro dépendance nouvelle ; aucun secret dans le code.
- Rétrocompatible : `reasoning="none"` par défaut, tous les tests existants doivent rester verts sans modification.
- TDD strict : test qui échoue → code minimal → test vert, pour chaque tâche.
- Le parsing du plan doit échouer en douceur (plan vide, jamais d'exception).
- Commandes de validation : `cd backend && uv run pytest -q`, `uv run ruff check .`, `uv run ty check`, `uv run python -m investia.evals`.

## Review Focus

- Un plan JSON malformé ne doit jamais faire planter le run (dégradé propre).
- Le coût de l'appel LLM du plan doit être compté dans `total_cost_cents`.
- Le client SSE du dashboard doit tolérer l'event `plan` inconnu (pas de page blanche).
- `plan_suivi` : plan vide → 1.0 ; outil appelé hors plan → 0.0 ; tous les outils dans le plan → 1.0.

---

### Task 1: Module `agent/reasoning.py` — PlanStep, parse_plan, make_plan

**Files:**
- Create: `backend/src/investia/agent/reasoning.py`
- Create: `backend/tests/test_reasoning_plan.py`
- Modify: `backend/src/investia/agent/prompts.py` (ajout `PLAN_PROMPT`)

**Interfaces:**
- Produces: `PlanStep(step: str, tool: str | None)` ; `Plan(steps: list[PlanStep])` ; `parse_plan(text: str) -> Plan` ; `async make_plan(llm: LlmChat, model_key: str, question: str, tool_names: list[str]) -> tuple[Plan, float]` (retourne le plan + le coût en centimes de l'appel).

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_reasoning_plan.py`:
  - `test_parse_plan_valid_json` : `parse_plan('{"steps": [{"step": "prix AAPL", "tool": "get_quote"}]}')` → 1 step, tool `get_quote`.
  - `test_parse_plan_invalid_json_returns_empty_plan` : `parse_plan("pas du json")` → `Plan(steps=[])` sans exception.
  - `test_parse_plan_tool_inconnu_devient_none` : tool non listé → `tool=None`.
  - `test_make_plan_calls_llm_once_and_returns_cost` : FakeLlm avec 1 réponse JSON valide → plan parsé + coût = cost_cents de la réponse ; `llm.calls` a 1 entrée, `tools=None` (pas de function calling pour le plan).
- [ ] **Step 2: Run** `cd backend && uv run pytest tests/test_reasoning_plan.py -q` → FAIL (module inexistant).
- [ ] **Step 3: Implement** `reasoning.py` + `PLAN_PROMPT` dans `prompts.py`. `PLAN_PROMPT` demande strictement `{"steps": [{"step": "...", "tool": "<nom d'outil ou null>"}]}` avec la liste des outils disponibles. `make_plan` appelle `llm.chat(model_key, [system PLAN_PROMPT, user question], tools=None)`, parse `response.content`, retourne `(plan, response.cost_cents)`.
- [ ] **Step 4: Run tests** → PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(12a): module reasoning — parse_plan + make_plan (TDD)"`.

### Task 2: Boucle `loop.py` — paramètre `reasoning`, event/step `plan`, `AgentResult.plan`

**Files:**
- Modify: `backend/src/investia/agent/loop.py`
- Modify: `backend/tests/test_reasoning_plan.py` (nouveaux tests) — réutilise `FakeLlm`/`FakeMarket` de `test_agent_loop.py` (mêmes patterns).

**Interfaces:**
- Consumes: `make_plan`, `Plan` from Task 1.
- Produces: `run_agent(..., reasoning: str = "none") -> AgentResult` ; `AgentResult.plan: Plan | None = None`.

- [ ] **Step 1: Write failing tests**:
  - `test_mode_none_no_plan_call` : `run_agent(q, FakeLlm([tool_call, final]), tools, reasoning="none")` → `result.plan is None`, le FakeLlm a exactement 2 appels (rétrocompat stricte).
  - `test_mode_plan_emits_plan_event_and_logs_step` : `reasoning="plan"` avec FakeLlm([plan_json, tool_call, final]) + `event_sink` collecteur + `trace_store` fake → event `plan` émis avec les steps, step `plan` loggé, `result.plan` rempli, coût du plan inclus dans `total_cost_cents`.
  - `test_mode_plan_invalid_json_degrades` : réponse plan invalide → run continue normalement, `result.plan.steps == []`, statut `ok`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** dans `loop.py` : signature `reasoning: str = "none"` ; champ `plan` dans `AgentResult` ; au début du run, si `reasoning == "plan"`, `plan, plan_cost = await make_plan(...)`, `total_cost += plan_cost`, `emit("plan", {"steps": [...]})`, `store.log_step(run_id, 0, "plan", {...})`. Valeurs autres que "none"/"plan" → ValueError.
- [ ] **Step 4: Run tests** → PASS, puis `uv run pytest tests/test_agent_loop.py tests/test_agent_guardrails.py tests/test_agent_approval.py -q` → PASS (non-régression boucle).
- [ ] **Step 5: Commit** `git commit -m "feat(12a): boucle — mode reasoning=plan, event SSE + step plan (TDD)"`.

### Task 3: Métrique `plan_suivi` dans les evals

**Files:**
- Modify: `backend/src/investia/evals/metrics.py`
- Modify: `backend/tests/test_evals.py` (ajout de tests)

**Interfaces:**
- Consumes: `AgentResult.plan`, `AgentResult.tool_calls`.
- Produces: `compute_metrics(...)` retourne un dict contenant en plus `plan_suivi: float`.

- [ ] **Step 1: Write failing tests**: `test_plan_suivi_ok` (outils appelés ⊆ outils du plan → 1.0) ; `test_plan_suivi_hors_plan` (outil non prévu → 0.0) ; `test_plan_suivi_plan_vide` (plan None ou vide → 1.0).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** : dans `compute_metrics`, `planned = {s.tool for s in result.plan.steps if s.tool}` ; `plan_suivi = 1.0 if not planned or all(c.tool in planned for c in result.tool_calls) else 0.0`. Si `result.plan is None` → 1.0.
- [ ] **Step 4: Run** `uv run pytest tests/test_evals.py -q` → PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(12a): métrique d'eval plan_suivi (TDD)"`.

### Task 4: Cas d'evals — `mock_plan` dans le runner + 2 nouveaux cas

**Files:**
- Modify: `backend/src/investia/evals/runner.py` (`EvalCase.mock_plan: str | None`, `MockLlm` rejoue le plan en 1re réponse)
- Modify: `evals/cases.yaml` (2 cas : `plan-suivi`, `plan-non-suivi`)
- Modify: `backend/tests/test_evals.py`

**Interfaces:**
- Consumes: Task 2 (`run_agent(reasoning="plan")`), Task 3.
- Produces: `run_evals` passe `reasoning="plan"` quand le cas a un `mock_plan`.

- [ ] **Step 1: Write failing test**: `test_run_evals_plan_suivi` — charge `evals/cases.yaml`, run en mock, assert que le cas `plan-suivi` a `plan_suivi == 1.0` et `plan-non-suivi` a `0.0`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** : `EvalCase` gagne `mock_plan`; `MockLlm.__init__` prepend une `LlmResponse` avec le contenu `mock_plan` si présent ; `run_evals` appelle `run_agent(..., reasoning="plan" if case.mock_plan else "none")`.
  - Cas `plan-suivi` : question "Analyse AAPL (prix + news)", mock_plan avec steps get_quote + get_news, mock_tool_call get_quote, final conforme.
  - Cas `plan-non-suivi` : mock_plan avec step get_quote, mock_tool_call get_news → plan_suivi 0.0. (Le mock_final doit contenir un chiffre sourcé par la sortie de get_news pour passer le garde-fou numbers — MockMarket renvoie des listes vides, donc le final ne doit contenir aucun chiffre hors confiance.)
- [ ] **Step 4: Run** `uv run pytest tests/test_evals.py -q` puis `uv run python -m investia.evals` → PASS, métrique `plan_suivi` visible dans les résultats.
- [ ] **Step 5: Commit** `git commit -m "feat(12a): cas d'evals plan-suivi / plan-non-suivi (TDD)"`.

### Task 5: Validation globale + docs

- [ ] **Step 1:** `cd backend && uv run pytest -q` → tout vert ; `uv run ruff check .` et `uv run ty check` → propres.
- [ ] **Step 2:** `uv run python -m investia.evals` → affiche `plan_suivi` pour les 5 cas.
- [ ] **Step 3:** Vérifier que le dashboard tolère l'event SSE `plan` inconnu : `cd dashboard && npm run test` (ou `tsc` + tests) vert, aucun changement frontend requis.
- [ ] **Step 4:** Mettre à jour `docs/STATUS.md` (étape 12a terminée) et `docs/08-roadmap.md` (ajout étape 12a cochée). Noter la décision dans `docs/09-decisions.md` (D69 : mode reasoning, plan tracé + métrique, défaut "none").
- [ ] **Step 5:** Commit docs.
