# Spec — 16a : schéma temporel de la mémoire longue (valid_from / valid_until / superseded_by)

*Écrite le : 14/11/2026 | Étape roadmap : 16 (mémoire & contexte) | Statut : terminée le 14/11/2026 (542 tests non-integration passed / 1 skip, ruff/ty/format propres, alembic head 0009)*

## Objectif

Donner à la table `memories` une **histoire temporelle** : chaque souvenir a une période de validité, peut être remplacé par une version plus récente (sans perdre l'ancienne), et peut être « oublié » sans suppression. L'agent gagne deux nouveaux outils (`update_memory`, `forget_memory`) et le `recall_memory` filtre par défaut sur les souvenirs encore valides.

## Pourquoi

Veille 14/11/2026 (§6 mémoire) : Mem0 (opérations ADD/UPDATE/DELETE/NOOP) et Graphiti (`valid_at`/`invalid_at`) sont le standard de fait — un souvenir qui change (ex. « profil de risque prudent » → « modéré ») doit laisser une trace, pas écraser l'ancien. Aujourd'hui notre `memories` n'a qu'un `created_at` : un UPDATE écraserait l'historique et un DELETE le perdrait. Zéro dépendance nouvelle : on reste en SQL/pgvector maison.

## Contraintes

- **Zéro régression** : `save(content, embedding)` et `recall(query, k)` gardent leur comportement par défaut (rétrocompatible) ; `test_memory.py` et `test_memory_integration.py` existants passent (le test d'intégration est étendu, pas cassé).
- **Jamais de DELETE** sur `memories` : l'oubli = `valid_until = now()` (soft delete). L'historique reste en base.
- Migration Alembic `0009_temporal_memories` (up/down), zéro dépendance ajoutée.
- Pas de secret, pas de réseau au runtime ; embeddings toujours via l'interface `Embeddings` existante.

## Changements prévus

### Migration `backend/alembic/versions/0009_temporal_memories.py`
- `ALTER TABLE memories ADD COLUMN valid_from TIMESTAMPTZ NOT NULL DEFAULT now()`, `valid_until TIMESTAMPTZ NULL`, `superseded_by UUID NULL REFERENCES memories(id)`, `provenance TEXT NOT NULL DEFAULT 'agent'`, `scope TEXT NOT NULL DEFAULT 'global'`.
- Index HNSW partiel : `CREATE INDEX ix_memories_current_embedding ON memories USING hnsw (embedding vector_cosine_ops) WHERE valid_until IS NULL` (le recall ne scanne que les courants).
- Index B-tree sur `valid_from`. Downgrade : drop index + colonnes.

### `backend/src/investia/memory/store.py`
- `save(content, embedding=None, *, provenance="agent", scope="global", dedup_threshold: float = 0.97) -> SaveResult` où `SaveResult` est un petit dataclass `{"id": str, "duplicate": bool}`. **Dédup sémantique à l'écriture** : si un souvenir courant (valid_until IS NULL) a un score cosinus ≥ `dedup_threshold`, ne rien insérer et retourner l'id existant avec `duplicate=True` (écriture idempotente — comme appuyer deux fois sur le bouton d'ascenseur, le résultat est le même). Le tool `save_memory` aplati ce contrat en `{"saved": True, "id": ..., "duplicate": bool}`.
- `supersede(old_id, new_content, embedding=None, *, provenance="agent", scope="global") -> str` : transaction — `UPDATE memories SET valid_until=now(), superseded_by=:new WHERE id=:old AND valid_until IS NULL` puis INSERT de la nouvelle version. Si `old_id` inconnu ou déjà archivé → `ValueError`. Retourne le nouvel id.
- `forget(memory_id) -> bool` : `UPDATE memories SET valid_until=now() WHERE id=:id AND valid_until IS NULL` ; `True` si une ligne touchée, `False` sinon.
- `recall(query, k=5, *, include_history=False) -> list[dict]` : filtre `valid_until IS NULL` par défaut ; chaque résultat gagne `id`, `provenance`, `scope`, `valid_from`, `valid_until` (None si courant).
- `history(memory_id) -> list[dict]` : chaîne des versions via `superseded_by`, ordre chronologique (la plus récente d'abord).
- `MemoryStoreProtocol` mis à jour (nouvelles méthodes avec défauts côté appel).

### `backend/src/investia/memory/tools.py`
- `SaveMemoryTool` : args optionnels `provenance: str = "agent"`, `scope: str = "global"` ; résultat + `"duplicate": bool`.
- `RecallMemoryTool` : arg optionnel `include_history: bool = False`.
- Nouveaux outils `UpdateMemoryTool` (`memory_id`, `content`, `provenance?`, `scope?`) → `{"updated": True, "id": new_id, "superseded": old_id}` ; `ForgetMemoryTool` (`memory_id`) → `{"forgotten": bool}`. Erreur store (ValueError) → `ToolError`.

### `backend/src/investia/tools/__init__.py`
- Câble les 4 outils mémoire quand `memory_store` est fourni (rétrocompatible : `build_tools` sans mémoire inchangé).

## Critères d'acceptation

- [ ] `cd backend && uv run pytest tests/test_memory_temporal.py tests/test_memory.py -q` passe (TDD : fakes temporels in-memory, tests écrits avant le code).
- [ ] Unitaire : save avec doublon sémantique → même id retourné, `duplicate=True` ; supersede → l'ancien a `valid_until` renseigné + `superseded_by`, le nouveau est courant ; forget → soft delete, `history` conserve tout ; recall filtre les archivés par défaut, les inclut avec `include_history=True`.
- [ ] `uv run pytest -q -m "not integration"` passe en entier ; ruff/ty/format propres sur les fichiers touchés.
- [ ] `test_memory_integration.py` étendu (save/supersede/forget/recall/history contre vraie table pgvector, marqué `integration`, non lancé ici) — migration 0009 appliquée.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/alembic/versions/0009_temporal_memories.py` | nouvelle migration (colonnes + index partiels) |
| `backend/src/investia/memory/store.py` | `save` dédup, `supersede`, `forget`, `recall(include_history)`, `history` |
| `backend/src/investia/memory/tools.py` | 2 outils existants étendus + `UpdateMemoryTool` / `ForgetMemoryTool` |
| `backend/src/investia/tools/__init__.py` | câblage des 4 outils |
| `backend/tests/test_memory_temporal.py` | tests TDD (fakes in-memory) |
| `backend/tests/test_memory.py` | `FakeMemoryStore` étendu au nouveau protocol |
| `backend/tests/test_memory_integration.py` | cas temporels contre pgvector (marqué integration) |
| `docs/STATUS.md` | étape 16a |

## Comment vérifier

```bash
cd backend && uv run pytest tests/test_memory_temporal.py tests/test_memory.py -q
cd backend && uv run pytest -q -m "not integration"
cd backend && uv run ruff check src/investia/memory tests/test_memory_temporal.py && uv run ruff format --check src/investia/memory && uv run ty check src/investia/memory
```

## Hors périmètre

- 16b : embeddings locaux (sentence-transformers) derrière l'interface `Embeddings` — chantier séparé.
- 16c : compaction de `run_agent` (sliding window + résumé « untrusted") — chantier séparé.
- Recall hybride BM25 + vectoriel (tsvector/GIN) et colonne `confidence` (veille §6) : reportés, on verra après 16b/16c.
- Le dashboard n'est pas touché (les outils mémoire restent consommés par l'agent seul).
