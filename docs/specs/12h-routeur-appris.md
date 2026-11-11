# Spec — 12h : routeur appris (petit vs gros modèle LLM)

*Écrite le : 11/11/2026 | Étape roadmap : 12 (approfondir le harness) | Statut : validée le 11/11/2026 (table router_feedback pgvector, k-NN k=7 pondéré, fallback règles si <5 feedbacks ou écart <0,1, métrique routeur_choix, zéro dépendance)*

## Objectif

Un **routeur appris** qui choisit `small` ou `large` pour chaque question, en apprenant des feedbacks passés (quelle question a réussi avec quel modèle), avec **fallback sur le routeur à règles** (D44) quand les preuves manquent.

## Pourquoi

Le budget LLM est serré (10-20 €/mois, D22) : `small` (gpt-6-luna) coûte 0,10 $/M tokens en entrée contre 1,36 $ pour `large` (mistral-large-4) — `models.toml`. Le routeur à règles devine par mots-clés et se trompe ; un routage appris sur des cas réels oriente le budget vers le bon modèle.

## Contraintes

- **Zéro dépendance nouvelle** : pgvector + embeddings existants (text-embedding-3-small), SQL raw comme `DbSemanticCache` (12e).
- Migration Alembic `0008_router_feedback` : table `router_feedback` (question text, embedding vector(1536), model text, success boolean, created_at) + index HNSW cosinus.
- Algorithme : **k-NN sémantique pondéré**, k=7 voisins les plus proches ; `score(model) = Σ(similarité × success) / Σ(similarités)` par modèle ; si moins de 5 feedbacks au total ou `|score_small − score_large| < 0,1` → fallback `choose()` (règles, D44).
- `record(question, model, success)` appelé automatiquement par `run_agent` après chaque run (status `ok` → success, `blocked`/`max_turns` → échec) ; erreurs avalées (le routage ne doit jamais faire échouer un run).
- `run_agent(..., router=None)` : si `model_key` est passé → « explicit » ; sinon si router fourni → il décide, sinon `choose()` règles. `AgentResult.router_source` = `explicit` | `learned` | `rules`.
- Rétrocompatible : sans `router`, comportement identique à aujourd'hui. En evals mock : `FakeRouterFeedback` déterministe, zéro DB.
- Métrique d'evals `routeur_choix` : le modèle choisi égale `expected_model` du cas (optionnel).

## Critères d'acceptation

- [ ] `uv run pytest tests/test_llm_router_learned.py -q` passe (store fake déterministe, zéro DB) : k-NN pondéré choisit le bon modèle ; fallback règles si < 5 feedbacks ; fallback si écart < 0,1 ; `record` persiste question+model+success.
- [ ] Migration `0008_router_feedback` chaînée après `0007_semantic_cache` (vérifié à la lecture du fichier).
- [ ] `run_agent` avec routeur fake : `router_source` = `learned` quand le routeur décide, `rules` en fallback, `explicit` si `model_key` passé ; `record` appelé avec le bon `success` selon `status`.
- [ ] 2 cas d'evals (`routeur-learned`, `routeur-fallback`) : `routeur_choix = 1.0`.
- [ ] `uv run pytest -q -m "not integration"`, `ruff check` + `ty check` sur les fichiers touchés, dashboard 110 tests verts, evals mock (18 cas) tous ok.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/alembic/versions/0008_router_feedback.py` | création (table + index HNSW) |
| `backend/src/investia/llm/router.py` | `RouterFeedbackStore` protocol + `LearnedRouter.choose/record` (k-NN pondéré + fallback) |
| `backend/src/investia/llm/router_store.py` | création : `DbRouterFeedback` (SQL raw pgvector, comme `DbSemanticCache`) |
| `backend/src/investia/agent/loop.py` | `run_agent(..., router=None)` + `AgentResult.router_source` + `record` après le run |
| `backend/src/investia/evals/metrics.py` | métrique `routeur_choix` |
| `backend/src/investia/evals/runner.py` + `evals/cases.yaml` | `FakeRouterFeedback`, `expected_model`, +2 cas |
| `backend/tests/test_llm_router_learned.py` | création (TDD) |
| `backend/tests/test_agent_loop.py`, `test_evals.py` | ajouts |

## Comment vérifier

```bash
cd backend
uv run pytest tests/test_llm_router_learned.py -q
uv run pytest -q -m "not integration"
uv run ruff check src/investia/llm/ && uv run ty check
```

## Hors périmètre

Vrai classifieur entraîné (régression logistique, etc.), routage par outil ou par étape du plan, plus de 2 modèles, ré-entraînement automatique des poids, feedback utilisateur explicite (bouton 👍/👎 — une piste pour plus tard).
