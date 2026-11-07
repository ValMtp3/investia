# Spec — 3.2 : Mémoire longue de l'agent (pgvector)

*Écrite le : 2026-10-31 | Étape roadmap : 3.2 | Statut : validée*

## Objectif

L'agent a une **mémoire longue** : profil de risque, préférences, faits retenus — stockés dans PostgreSQL avec une colonne `embedding` (pgvector), retrouvés par recherche sémantique via deux outils exposés à la boucle : `save_memory` et `recall_memory`. La mémoire courte reste la conversation en cours (fenêtre de contexte).

## Pourquoi

Doc 03 §5 : pgvector suffit à notre échelle (quelques milliers de souvenirs), zéro conteneur en plus (Q7). Sans mémoire, l'agent oublie tes préférences entre les sessions.

## Contraintes

- Migration `0004_memories.py` : `CREATE EXTENSION IF NOT EXISTS vector` + table `memories` (id UUID, content text, embedding `vector(1536)`, created_at) + index HNSW sur embedding. Dimension 1536.
- **Embeddings** via OpenRouter (`openai/text-embedding-3-small`, 1536 dims, ~$0.02/M tokens — négligeable) avec `OPENROUTER_API_KEY`. Client httpx mockable.
- `memory/store.py` : `save(content) -> id`, `recall(query, k=5) -> list[Memory]` (recherche cosinus pgvector : `ORDER BY embedding <=> :q LIMIT :k`).
- **Outils** `memory/tools.py` : `save_memory(content: str)` et `recall_memory(query: str, k=5)` — mêmes contrats que les autres outils (BaseTool, schéma Pydantic), ajoutés au registre `build_tools` quand un store est dispo.
- pgvector côté tests : le PostgreSQL **Docker** (image `pgvector/pgvector:pg17`, port 5432) a l'extension ; le brew local non. Les tests integration mémoire utilisent le conteneur Docker.
- TDD ; tests unitaires mockés (embeddings + store fake), integration marquée contre le conteneur pgvector.

## Critères d'acceptation

- [ ] `cd backend && uv run pytest -q` passe (tous les tests, y compris `test_memory_*`).
- [ ] `alembic upgrade head` applique `memories` + extension vector (test integration, conteneur Docker).
- [ ] Roundtrip réel : save 3 souvenirs, `recall("mon profil de risque")` retrouve le bon en top 1 (test integration).
- [ ] Recherche sémantique et non par mot-clé : une requête reformulée retrouve le souvenir (test integration).
- [ ] Les 2 outils apparaissent dans le registre `build_tools` et passent les checks du contrat LLM.
- [ ] Un run d'agent mocké peut appeler `recall_memory` (test boucle).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/alembic/versions/0004_memories.py` | création : extension vector + table memories + index HNSW |
| `backend/src/investia/memory/__init__.py`, `embeddings.py`, `store.py`, `tools.py` | création |
| `backend/src/investia/tools/__init__.py` | modification : registre + `save_memory`/`recall_memory` si store dispo |
| `backend/tests/test_memory*.py` | création : unitaires mockés + integration (conteneur pgvector) |

## Comment vérifier

```bash
cd backend && uv run pytest -q
# integration (conteneur postgres docker, port 5432) :
TEST_DATABASE_URL=postgresql+asyncpg://investia:localtest123@127.0.0.1:5432/investia_test uv run pytest -q -m integration -k memory
```

## Hors périmètre

Résumé automatique de la conversation (mémoire courte, étape ultérieure), partage de mémoire entre agents (étape 6), nettoyage/oubli (TTL mémoire, plus tard).
