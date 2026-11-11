# Plan d'implémentation — Étape 12h : routeur appris (petit vs gros modèle)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un routeur appris `LearnedRouter` qui choisit `small`/`large` par k-NN sémantique pondéré sur une table pgvector `router_feedback` (k=7, fallback sur les règles D44 si < 5 feedbacks ou écart de score < 0,1), câblé dans `run_agent(..., router=None)` avec `AgentResult.router_source` et `record` automatique après chaque run, plus métrique d'evals `routeur_choix` et 2 cas mock.

**Architecture:** `llm/router.py` ajoute `RouterFeedbackStore` protocol (`record(question, model, success)`, `neighbors(question, k) -> list[Neighbor(similarity, model, success)]`) + `LearnedRouter.choose(question) -> (model_key, source)` (score par modèle = Σ(sim×success)/Σ(sim), fallback `choose()` règles). `llm/router_store.py` : `DbRouterFeedback` (SQL raw pgvector, pattern `DbSemanticCache`, embeddings existants). Migration `0008_router_feedback`. Zéro dépendance nouvelle.

**Tech Stack:** Python 3.12+, SQLAlchemy text() + pgvector, Pydantic, pytest. Tests unitaires avec store fake en mémoire (zéro DB) ; test DB marqué `integration` comme `test_semantic_cache.py`.

**Spec:** `docs/specs/12h-routeur-appris.md` (validée le 11/11/2026)

## Global Constraints

- Zéro librairie ajoutée. Embeddings existants (`Embeddings.embed`), dimension 1536.
- Rétrocompatible : `run_agent` sans `router` → `choose()` règles, `router_source="rules"` ; `model_key` explicite → `explicit`.
- Le feedback `record` après chaque run ne doit jamais faire échouer le run (erreur avalée). Pas de record si servi par le cache (from_cache).
- `AgentResult.router_source: str = "rules"` (défaut rétrocompatible pour les tests existants).
- TDD strict par tâche. Validation : `cd backend && uv run pytest -q -m "not integration"`, `ruff check`/`ty check` sur les fichiers touchés, evals mock 18 cas, dashboard 110 tests.

## Review Focus

- Fallback règles bien atteint quand peu de données (< 5) ou scores proches (< 0,1) — le routeur ne décide pas au hasard.
- `record` appelé avec `success = (status == "ok")`, jamais sur un run servi par cache.
- Coût : 1 embedding par question (comme le cache sémantique) — pas d'appel LLM.

---

### Task 1: `llm/router.py` — `LearnedRouter` + tests TDD (store fake en mémoire)

**Files:**
- Modify: `backend/src/investia/llm/router.py`
- Create: `backend/tests/test_llm_router_learned.py`

**Interfaces:**
- Produces: `Neighbor` dataclass (similarity: float, model: str, success: bool) ; `RouterFeedbackStore` protocol ; `LearnedRouter(store, fallback=choose, k=7, min_feedbacks=5, min_gap=0.1)` avec `async choose(question) -> tuple[str, str]` et `async record(question, model, success)`.

- [ ] **Step 1: Write failing tests** (FakeStore en mémoire) : `test_knn_choisit_le_modele_qui_a_reussi` (6 voisins small success → ("small", "learned")) ; `test_fallback_regles_si_moins_de_5_feedbacks` (store vide → ("…", "rules")) ; `test_fallback_regles_si_ecart_trop_faible` (scores ex-aequo → "rules") ; `test_pondération_par_similarité` (voisin proche success small vs voisin lointain success large → small gagne) ; `test_record_delegue_au_store`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `LearnedRouter` (scores pondérés, seuils, fallback).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(12h): LearnedRouter — k-NN sémantique pondéré + fallback règles (TDD)`.

### Task 2: Migration `0008_router_feedback` + `llm/router_store.py` (`DbRouterFeedback`)

**Files:**
- Create: `backend/alembic/versions/0008_router_feedback.py` (chaînée sur `0007_semantic_cache`, table + index HNSW cosinus, pattern migration 0007)
- Create: `backend/src/investia/llm/router_store.py` (`DbRouterFeedback(session_factory, embeddings)` : `record` = INSERT avec embedding ; `neighbors` = SELECT k plus proches avec `1 - (embedding <=> :e)` AS similarity, pattern `DbSemanticCache`)
- Create/Modify: `backend/tests/test_llm_router_learned.py` : test de chaîne de révisions (0008.down_revision == 0007.revision, lu dans les fichiers) ; test `DbRouterFeedback` marqué `@pytest.mark.integration` (même pattern que `test_semantic_cache.py`).

- [ ] **Step 1:** test chaînage révisions → FAIL (fichier 0008 absent).
- [ ] **Step 2:** créer migration + store ; test unitaire chaînage → PASS ; test integration skip sans DB.
- [ ] **Step 3:** `ruff`/`ty` ; commit `feat(12h): table router_feedback (migration 0008) + DbRouterFeedback pgvector`.

### Task 3: Câblage `run_agent(..., router=None)` + `AgentResult.router_source` + record feedback

**Files:**
- Modify: `backend/src/investia/agent/loop.py`
- Modify: `backend/tests/test_agent_loop.py` (ajouts)

- [ ] **Step 1: Write failing tests** : `test_router_learned_choisit_et_source_learned` (FakeRouter qui renvoie ("small", "learned")) ; `test_sans_router_source_rules` (rétrocompat) ; `test_model_key_explicite_source_explicit` ; `test_record_appele_avec_success_selon_status` (run ok → success True ; run bloqué → False) ; `test_record_pas_appele_si_cache_hit` ; `test_erreur_record_avalee` (store qui raise → run quand même ok).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement dans `loop.py` : résolution du modèle (explicit > router > règles), `router_source` dans tous les `AgentResult`, `record` dans le wrapper après le run (hors cache, erreur avalée).
- [ ] **Step 4:** Run `uv run pytest tests/test_agent_loop.py -q` → PASS.
- [ ] **Step 5:** Commit `feat(12h): run_agent câble le routeur appris + router_source + feedback record (TDD)`.

### Task 4: Evals — métrique `routeur_choix` + 2 cas (`routeur-learned`, `routeur-fallback`)

**Files:**
- Modify: `backend/src/investia/evals/metrics.py` (`routeur_choix` via `expected_model`)
- Modify: `backend/src/investia/evals/runner.py` (`EvalCase.expected_model`, `mock_router_neighbors` ; `FakeRouterFeedbackStore` ; `run_evals` construit un `LearnedRouter` fake par cas quand `mock_router_neighbors` est présent et le passe à `run_agent`)
- Modify: `evals/cases.yaml` (+2 cas)
- Modify: `backend/tests/test_evals.py`

- [ ] **Step 1:** tests : cas `routeur-learned` (6 voisins small success, question piège « analyse … » où les règles diraient large) → `routeur_choix=1.0`, `router_source=learned` ; cas `routeur-fallback` (0 voisin, question « analyse approfondie » → règles → large) → `routeur_choix=1.0`, source rules.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement metrics + runner + YAML.
- [ ] **Step 4:** Run `uv run pytest tests/test_evals.py -q` → PASS ; evals mock complet (18 cas) tous ok.
- [ ] **Step 5:** Commit `feat(12h): métrique routeur_choix + 2 cas evals routeur (TDD)`.

### Task 5: Validation globale + docs + push

- [ ] **Step 1:** `cd backend && uv run pytest -q -m "not integration"` vert ; `ruff check`/`ty check` sur les fichiers touchés ; `test_secrets_hygiene.py` vert ; evals mock 18 cas ok.
- [ ] **Step 2:** `cd dashboard && npm run test` → 110 tests verts.
- [ ] **Step 3:** `docs/STATUS.md` (12h terminée), `docs/08-roadmap.md` (12h cochée → chantier 12 terminé), `docs/09-decisions.md` (D76 + historique), spec marquée terminée.
- [ ] **Step 4:** Commit docs. Demander le push de la branche.
