# Spec — 16b : embeddings locaux (sentence-transformers) derrière l'interface `Embeddings`

*Écrite le : 14/11/2026 | Étape roadmap : 16 (mémoire & contexte) | Statut : terminée le 14/11/2026 (551 tests non-integration passed / 1 skip, ruff/ty/format propres)*

## Objectif

Permettre de calculer les embeddings **en local** (zéro appel API, zéro coût, zéro fuite de données vers OpenRouter) via `sentence-transformers`, derrière l'interface `Embeddings` existante. Un réglage `EMBEDDINGS_BACKEND=local` suffit ; `openrouter` reste le défaut (rétrocompatible).

## Pourquoi

Veille 14/11/2026 (§6) : Qwen3-Embedding-0.6B (Apache-2.0, 103 M téléchargements sur HF) ou `microsoft/harrier-oss-v1-0.6b` (MIT) sont les meilleurs modèles locaux de leur taille en nov 2026. jina-embeddings-v5 est exclu (licence CC BY-NC, pas pour un usage commercial). Aujourd'hui 100 % de nos embeddings passent par OpenRouter (coût + dépendance réseau + données qui partent) — utile en secours, pénible comme défaut.

## Contraintes

- **Zéro migration de schéma** : la colonne `memories.embedding` reste `vector(1536)`. Un vecteur local de dimension d (ex. 1024) est **complété par des zéros** jusqu'à 1536. Pour la similarité cosinus c'est exact : ajouter des zéros ne change ni le produit scalaire ni la norme, donc `cos(a,b)` est identique avec ou sans padding.
- Dépendance `sentence-transformers` (déjà validée par le propriétaire, ajoutée à `pyproject.toml` + `uv.lock`). Modèle par défaut `Qwen3-Embedding-0.6B`, surchargeable via `LOCAL_EMBEDDING_MODEL`. Le téléchargement du modèle (~1,2 Go) a lieu au premier chargement (cache HF local), jamais par appel.
- Imports lazy : `sentence_transformers` importé dans le constructeur, pas au niveau du module (le package reste importable sans la dep, ex. tests unitaires).
- **Fallback** : si `sentence-transformers` n'est pas installé ou si le modèle ne peut pas être chargé, `build_memory` retombe sur `OpenRouterEmbeddings` avec un warning loggé (zéro régression runtime).
- Pas de GPU supposé (`device="cpu"`), pas de batch énorme (mémoire longue = petites listes).
- Sécurité : aucun secret en dur ; le nom du modèle vient de la config (env), validé contre une liste de caractères simples.

## Changements prévus

### `backend/src/investia/memory/embeddings.py`
- `LocalEmbeddings(Embeddings)` : constructeur `(model_name: str = "Qwen3-Embedding-0.6B", device: str = "cpu", http_client=None n/a)` ; charge `sentence_transformers.SentenceTransformer` en lazy ; `embed(texts) -> list[list[float]]` : `model.encode(texts, normalize_embeddings=True)` → liste de vecteurs, complétés à `EMBEDDING_DIM` (1536) par des zéros (tronqués si plus grands, avec un warning).
- `pad_to_dim(vector, dim)` helper testable seul.

### `backend/src/investia/config.py`
- `embeddings_backend: Literal["openrouter", "local"] = "openrouter"` (env `EMBEDDINGS_BACKEND`).
- `local_embedding_model: str = "Qwen3-Embedding-0.6B"` (env `LOCAL_EMBEDDING_MODEL`), validé par un pattern simple (`^[A-Za-z0-9._/-]+$`).

### `backend/src/investia/memory/__init__.py`
- `build_memory(settings)` : si `embeddings_backend == "local"` → essaie `LocalEmbeddings(settings.local_embedding_model)`, fallback `OpenRouterEmbeddings` + `logger.warning` en cas d'échec ; si `"openrouter"` → comportement actuel inchangé. Le type de retour devient `tuple[DbMemoryStore, Embeddings]`.

### `backend/pyproject.toml` + `uv.lock`
- ajout `sentence-transformers` (version épinglée `>=` la dernière stable de nov 2026).

## Critères d'acceptation

- [ ] `cd backend && uv run pytest tests/test_embeddings_local.py tests/test_memory.py tests/test_memory_temporal.py -q` passe (TDD).
- [ ] Unitaire : `pad_to_dim` (1024 → 1536 zéros, tronqué si > dim, cosinus conservé — test avec deux vecteurs connus) ; `LocalEmbeddings.embed` avec un faux module `sentence_transformers` injecté dans `sys.modules` → vecteurs normalisés, dim 1536, appel unique au modèle ; `build_memory` backend=local → `LocalEmbeddings`, backend=openrouter → `OpenRouterEmbeddings` (inchangé), local indisponible (import simulé en échec) → fallback OpenRouter + warning.
- [ ] `uv run pytest -q -m "not integration"` passe en entier ; ruff/ty/format propres.
- [ ] Aucun téléchargement réseau pendant les tests (faux modèle injecté).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/memory/embeddings.py` | `LocalEmbeddings` + `pad_to_dim` (import lazy) |
| `backend/src/investia/config.py` | `embeddings_backend`, `local_embedding_model` |
| `backend/src/investia/memory/__init__.py` | `build_memory` choisit le backend + fallback |
| `backend/pyproject.toml`, `backend/uv.lock` | `sentence-transformers` (validé) |
| `backend/tests/test_embeddings_local.py` | tests TDD (faux sentence_transformers) |
| `.env.example` | 2 lignes commentées pour le backend local |
| `docs/STATUS.md` | étape 16b |

## Comment vérifier

```bash
cd backend && uv run pytest tests/test_embeddings_local.py tests/test_memory.py -q
cd backend && uv run pytest -q -m "not integration"
cd backend && uv run ruff check src/investia/memory src/investia/config.py tests/test_embeddings_local.py && uv run ty check src/investia/memory
# chargement réel du modèle (une fois, réseau HF) :
EMBEDDINGS_BACKEND=local uv run python -c "from investia.memory.embeddings import LocalEmbeddings; import asyncio; print(len(asyncio.run(LocalEmbeddings().embed(['test']))[0]))"
```

## Hors périmètre

- Changer `EMBEDDING_DIM` ou ré-embadder les souvenirs existants (le padding à 1536 rend ça inutile).
- 16c : compaction de `run_agent` (chantier séparé).
- GPU / batch massif / modèles > 1B params.
- Le dashboard n'est pas touché.
