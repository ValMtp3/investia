# Spec — 12e : Cache sémantique des réponses LLM

*Écrite le : 08/11/2026 | Étape roadmap : 12 (approfondir le harness) | Statut : validée le 08/11/2026 (seuil 0,92, pas de TTL en v1)*

## Objectif

Avant tout appel LLM, chercher dans un **cache sémantique** (pgvector) si une question très proche a déjà été répondue : si oui (similarité cosinus ≥ 0,92), renvoyer la réponse cachée **sans aucun appel LLM** (coût 0, tours 0), avec un event SSE `cache_hit`. Après un run terminé `ok`, la réponse est stockée dans le cache. Métrique d'eval `cache_hit`.

## Pourquoi

Une même question revient souvent (« prix de AAPL ? », « analyse CW8.PA cette semaine »). Le cache sémantique sert ces redites à ~0 € au lieu d'un appel LLM : hit rate attendu 25-40 % sur le trafic agent (doc 03 §2). C'est la brique la plus rentable pour le budget 10-20 €/mois (D22).

## Contraintes

- Zéro dépendance nouvelle : pgvector + `Embeddings` (text-embedding-3-small) existants, même pattern que `DbMemoryStore`.
- Rétrocompatible : `run_agent(..., semantic_cache=None)` — sans cache, aucun appel d'embedding, comportement inchangé.
- On ne **sert** que si score ≥ `CACHE_THRESHOLD = 0.92` (seuil haut : en finance, deux questions proches ne sont pas identiques). On ne **stocke** que les réponses `status="ok"` (jamais une réponse bloquée).
- Toute erreur du cache (embedding, base) est avalée et loggée → `lookup` renvoie None, `store` ne plante jamais le run (dégradé propre).
- Le lookup a lieu une fois par `run_agent` (pas par sous-run en k>1) ; le store une fois, après le run gagnant si ok.
- Migration Alembic `0007_semantic_cache` (table `semantic_cache` : id UUID, question, answer, embedding vector(1536), created_at + index HNSW cosinus), même style que `0004_memories`.
- Pas de TTL en v1 (le cache sémantique n'a pas la fraîcheur d'un prix en direct : on stocke la réponse de l'agent, pas le prix — la réponse cite des sources horodatées). Hors périmètre v1 : invalidation par fraîcheur.

## Critères d'acceptation

- [ ] `uv run pytest tests/test_semantic_cache.py -q` passe (TDD) + test d'intégration pgvector marqué `integration` (comme `test_memory_integration.py`).
- [ ] Migration : `alembic upgrade head` applique `0007_semantic_cache` (vérifié sur base jetable en test d'intégration).
- [ ] `DbSemanticCache.lookup` renvoie la réponse si score ≥ 0,92, None sinon ; `store` insère question+answer+embedding.
- [ ] Boucle : avec `semantic_cache`, un hit → `AgentResult(answer=<cachée>, turns=0, total_cost_cents=0, model="cache", status="ok", from_cache=True)` + event `cache_hit` ; pas de hit → run normal, puis `store(question, answer)` si status ok. Sans cache → rien (rétrocompat).
- [ ] Métrique `cache_hit` : 1.0 si `from_cache`, 0.0 sinon.
- [ ] 2 nouveaux cas dans `evals/cases.yaml` : `cache-hit` (mock_cache_hit renseigné → cache_hit=1.0, turns=0, cost=0) et un cas normal (cache_hit=0.0).
- [ ] `uv run python -m investia.evals` (mock) affiche `cache_hit`.
- [ ] `uv run ruff check .`, `uv run ty check`, `uv run pytest -q -m "not integration"` verts ; dashboard 110 tests verts.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/alembic/versions/0007_semantic_cache.py` | création (table + index HNSW) |
| `backend/src/investia/agent/semantic_cache.py` | création : `SemanticCacheProtocol`, `DbSemanticCache` (lookup/store, seuil 0,92) |
| `backend/src/investia/agent/loop.py` | param `semantic_cache` (wrapper), `AgentResult.from_cache`, event `cache_hit`, lookup avant / store après si ok, erreurs avalées |
| `backend/src/investia/evals/metrics.py` | + `cache_hit` |
| `backend/src/investia/evals/runner.py` | `EvalCase.mock_cache_hit` + `FakeSemanticCache` |
| `evals/cases.yaml` | + 2 cas (`cache-hit`, le reste sert de miss) |
| `backend/tests/test_semantic_cache.py` | tests TDD (+ integration pgvector) |

## Comment vérifier

```bash
cd backend
uv run pytest tests/test_semantic_cache.py -q
uv run pytest -q -m "not integration"
uv run ruff check . && uv run ty check
uv run python -m investia.evals
# intégration (base pgvector locale) :
uv run pytest tests/test_semantic_cache.py -q -m integration
```

## Hors périmètre

TTL/invalidation par fraîcheur des entrées, cache sémantique au niveau des appels d'outils (seulement la réponse finale de l'agent), compression de prompts, cache Redis partagé multi-instance. Aucun changement du comportement sans `semantic_cache`.
