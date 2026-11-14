# Plan d'implémentation — Étape 12e : cache sémantique des réponses LLM

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un cache sémantique pgvector sert les questions déjà posées sans appel LLM (seuil cosinus 0,92) : `lookup` avant le run, `store` après un run `ok`. Event SSE `cache_hit`, `AgentResult.from_cache`, métrique `cache_hit`.

**Architecture:** Migration `0007_semantic_cache` (table + index HNSW, style `0004_memories`). Nouveau `agent/semantic_cache.py` : `SemanticCacheProtocol` + `DbSemanticCache` (même pattern que `DbMemoryStore`, champ `answer`). Dans le wrapper `run_agent` : `semantic_cache=None` par défaut ; lookup avant toute chose (une fois, pas par sous-run), hit → résultat `from_cache=True` (turns=0, coût=0) + event `cache_hit` ; après le run (k=1 ou gagnant k>1), si `status=="ok"` et pas from_cache → `store`. Erreurs cache avalées (jamais de crash). Zéro dépendance nouvelle.

**Tech Stack:** Python 3.12+, pgvector (`<=>` cosinus), `Embeddings` existant (text-embedding-3-small), Alembic, pytest. Mock déterministe, zéro réseau.

**Spec:** `docs/specs/12e-cache-semantique.md` (validée le 08/11/2026)

## Global Constraints

- Zéro dépendance nouvelle ; aucun secret dans le code.
- Rétrocompatible : `semantic_cache=None` → aucun appel d'embedding, comportement identique.
- Sert uniquement si score ≥ `CACHE_THRESHOLD = 0.92` ; stocke uniquement les réponses `status="ok"`.
- Erreur du cache (embedding/base) → lookup None, store silencieux : jamais de crash du run.
- TDD strict par tâche. Validation : `cd backend && uv run pytest -q -m "not integration"`, `uv run ruff check .`, `uv run ty check`, evals mock ; test integration pgvector marqué `integration`.

## Review Focus

- Un hit ne passe PAS par les garde-fous (la réponse a déjà été validée quand stockée) — mais elle doit contenir le disclaimer (stockée seulement si ok).
- `from_cache=True` → turns=0, cost=0, model="cache" : bien visible dans les traces.
- Le store n'écrase pas : une question peut exister en plusieurs entrées (INSERT, pas UPSERT) ; le lookup prend le meilleur score.
- En k>1 : lookup/store une seule fois au niveau du wrapper, pas par sous-run.
- Migration downgrade propre (DROP TABLE).

---

### Task 1: Migration `0007_semantic_cache` + `agent/semantic_cache.py` (DbSemanticCache)

**Files:**
- Create: `backend/alembic/versions/0007_semantic_cache.py`
- Create: `backend/src/investia/agent/semantic_cache.py`
- Create: `backend/tests/test_semantic_cache.py`

**Interfaces:**
- Produces: `CACHE_THRESHOLD = 0.92` ; `SemanticCacheProtocol` (`lookup(question) -> str | None`, `store(question, answer) -> None`) ; `DbSemanticCache(session_factory, embeddings, threshold=CACHE_THRESHOLD)`.

- [ ] **Step 1: Write failing tests** in `test_semantic_cache.py` (unitaires avec `FakeEmbeddingsForTests` + session fake, et un test `integration` pgvector réel comme `test_memory_integration.py`) :
  - `test_lookup_renvoie_none_si_table_vide_ou_score_faible`
  - `test_lookup_renvoie_answer_si_score_au_dessus_du_seuil`
  - `test_store_insere_question_answer_embedding`
  - `test_seuil_par_defaut_092`
  - `test_integration_lookup_store_roundtrip` (marqué `@pytest.mark.integration`, pgvector local — skippé sans base)
- [ ] **Step 2: Run** `uv run pytest tests/test_semantic_cache.py -q -m "not integration"` → FAIL.
- [ ] **Step 3: Implement** migration (table `semantic_cache(id UUID PK, question TEXT, answer TEXT, embedding vector(1536), created_at)`, index HNSW `vector_cosine_ops`, downgrade DROP) + `DbSemanticCache` (SQL brut comme `DbMemoryStore`, `1 - (embedding <=> ...) AS score`, `ORDER BY ... LIMIT 1`, filtre `score >= threshold`).
- [ ] **Step 4: Run** tests → PASS (unitaires) ; `uv run pytest tests/test_semantic_cache.py -q -m integration` → skippé/vert selon base.
- [ ] **Step 5: Commit** `feat(12e): migration 0007 + DbSemanticCache (TDD)`.

### Task 2: Boucle — `semantic_cache` dans le wrapper, `from_cache`, event `cache_hit`, store après ok

**Files:**
- Modify: `backend/src/investia/agent/loop.py`
- Modify: `backend/tests/test_semantic_cache.py`

**Interfaces:**
- Consumes: Task 1.
- Produces: `run_agent(..., semantic_cache=None)` ; `AgentResult.from_cache: bool = False` ; event `cache_hit` ; lookup une fois avant le run, store après si ok.

- [ ] **Step 1: Write failing tests**:
  - `test_cache_hit_renvoie_sans_appel_llm` : FakeCache avec hit="réponse cachée" ; FakeLlm qui plante si appelé → result.answer == hit, turns == 0, cost == 0, model == "cache", from_cache True, status "ok", event `cache_hit` émis, aucun appel LLM.
  - `test_cache_miss_run_normal_puis_store_si_ok` : FakeCache sans hit, store espionné → run normal, store appelé avec (question, answer), from_cache False.
  - `test_pas_de_store_si_bloque` : run bloqué (garde-fou) → store PAS appelé.
  - `test_erreur_cache_ne_plante_pas` : cache qui lève → run normal, from_cache False.
  - `test_sans_cache_rien_ne_change` : semantic_cache=None → aucun appel cache, from_cache False.
  - `test_k3_lookup_store_une_seule_fois` : k=3 + cache → lookup appelé 1 fois, store 1 fois.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** dans le wrapper `run_agent` : param `semantic_cache`; avant le dispatch k=1/k>1, lookup (try/except → None) ; si hit → emit start/cache_hit/answer/done et retourner AgentResult from_cache ; sinon run normal puis store si `status=="ok" and not from_cache` (try/except). `AgentResult.from_cache`.
- [ ] **Step 4: Run** `uv run pytest tests/test_semantic_cache.py -q` → PASS ; non-régression `uv run pytest tests/test_reasoning_consistency.py tests/test_guardrails_llm.py tests/test_agent_loop.py -q` → PASS.
- [ ] **Step 5: Commit** `feat(12e): boucle — cache sémantique (lookup/store, event cache_hit) (TDD)`.

### Task 3: Métrique `cache_hit`

**Files:**
- Modify: `backend/src/investia/evals/metrics.py`
- Modify: `backend/tests/test_evals.py`

- [ ] **Step 1:** test `test_metrics_cache_hit` : from_cache=True → 1.0 ; défaut → 0.0.
- [ ] **Step 2:** Run → FAIL (KeyError).
- [ ] **Step 3:** Implement `"cache_hit": 1.0 if result.from_cache else 0.0`.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat(12e): métrique cache_hit (TDD)`.

### Task 4: Runner — `mock_cache_hit` + `FakeSemanticCache` + 2 cas YAML

**Files:**
- Modify: `backend/src/investia/evals/runner.py`
- Modify: `evals/cases.yaml`
- Modify: `backend/tests/test_evals.py`

- [ ] **Step 1:** test `test_run_evals_cache_hit` : cas avec `mock_cache_hit` → cache_hit=1.0, turns=0.0, cost_cents=0.0, status ok ; cas normal → cache_hit=0.0.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `EvalCase.mock_cache_hit`, `FakeSemanticCache` (lookup rend mock_cache_hit, store no-op + espion), `run_evals` passe `semantic_cache=FakeSemanticCache(case) if case.mock_cache_hit else None` ; 1 cas `cache-hit` dans `cases.yaml` (mock_cache_hit avec une réponse conforme).
- [ ] **Step 4:** Run `uv run pytest tests/test_evals.py -q` → PASS ; evals mock → `cache_hit` affiché.
- [ ] **Step 5:** Commit `feat(12e): cas d'eval cache-hit via mock_cache_hit (TDD)`.

### Task 5: Validation globale + docs

- [ ] **Step 1:** `cd backend && uv run pytest -q -m "not integration"` → vert ; `uv run ruff check .` ; `uv run ty check` → propres ; migration check : `uv run alembic heads` → 0007.
- [ ] **Step 2:** `cd dashboard && npm run test` → 110 tests verts (event `cache_hit` toléré).
- [ ] **Step 3:** `docs/STATUS.md` (12e terminée), `docs/08-roadmap.md` (12e cochée), `docs/09-decisions.md` (D73 + historique).
- [ ] **Step 4:** Commit docs.
