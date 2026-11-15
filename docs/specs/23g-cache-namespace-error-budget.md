# Spec 23g — Cache sémantique namespacé par user + seuil plancher 0,9 + error budget

*Écrite le : 15/11/2026 | Étape veille D94 (CVE-2026-89032, arXiv:2601.23088/2611.02498) | Statut : brouillon*

## Objectif

Durcir le cache sémantique 12e contre la fuite cross-user (CVE-2026-89032 LiteLLM) :
(1) **namespace** sur chaque entrée du cache, (2) **plancher de seuil à 0,9** imposé en
config, (3) **error budget** : au-delà d'un nombre d'erreurs consécutives, le cache passe
en mode dégradé (fail-open) au lieu d'échouer silencieusement, (4) câblage prod du cache
dans `main.py` (la brique 12e existe mais n'est pas encore branchée en prod).

## Pourquoi

CVE-2026-89032 : le cache sémantique de la gateway fuit des réponses entre utilisateurs.
Notre `semantic_cache` (migration 0007) n'a aucune colonne de propriétaire : une entrée
stockée par un utilisateur serait servie à un autre. L'app est mono-utilisateur derrière
Authelia aujourd'hui, mais la structure doit être prête (namespace par déploiement en v1,
par requête quand le multi-user arrivera). Les papiers arXiv 2601.23088/2611.02498 ajoutent
l'error budget : un cache qui échoue ne doit pas casser les runs (fail-open) mais doit être
observable et se désactiver proprement au-delà d'un budget d'erreurs.

## Contraintes

- Zéro régression : protocole `SemanticCacheProtocol` inchangé (méthodes sans namespace,
  rétrocompatible avec les fakes existants) ; `CACHE_THRESHOLD = 0.92` reste le défaut.
- Le namespace est lié à l'instance (`DbSemanticCache(..., namespace=...)`) ; la boucle
  (`loop.py`) ne change pas.
- Fail-open : une erreur de cache ne bloque jamais un run (déjà le cas côté boucle).
- Sécurité : namespace validé par pattern (`^[a-z0-9_-]{1,64}$`), seuil validé `0,9 ≤ t ≤ 1`.
- Aucune dépendance ajoutée.

## Contrat détaillé

### 1. Migration 0014

```sql
ALTER TABLE semantic_cache ADD COLUMN namespace TEXT NOT NULL DEFAULT 'default';
CREATE INDEX ix_semantic_cache_namespace ON semantic_cache (namespace);
```
(downgrade : drop index + drop column)

### 2. `DbSemanticCache` — namespace lié à l'instance

- Constructeur : `DbSemanticCache(session_factory, embeddings, threshold=CACHE_THRESHOLD, namespace="default")`.
- `lookup`/`store` ajoutent `WHERE namespace = :ns` (param lié au constructeur) sur
  `semantic_cache`. L'index HNSW existant reste global ; le filtre namespace passe en
  post-filtre (volume faible, cache = centaines d'entrées).

### 3. Config (`config.py` + `.env.example`)

- `semantic_cache_threshold: float = Field(default=0.92, ge=0.9, le=1.0)` — plancher 0,9
  (veille) ; une valeur < 0,9 est rejetée (ValidationError).
- `semantic_cache_namespace: str = Field(default="default", pattern="^[a-z0-9_-]{1,64}$")`.

### 4. Error budget — `BudgetedSemanticCache` (dans `semantic_cache.py`)

- Enveloppe un `SemanticCacheProtocol` : `lookup`/`store` délèguent ; chaque erreur
  (exception) incrémente un compteur d'erreurs **consécutives** ; au-delà de
  `error_budget` (défaut 5) → `degraded = True` : `lookup` renvoie None, `store` no-op,
  warning loggé une fois. Un succès remet le compteur à 0 et `degraded = False`.
- `stats() -> {"lookups": int, "hits": int, "errors": int, "degraded": bool}`.

### 5. Câblage prod (`main.py`)

- Nouvelle helper testable `_build_semantic_cache(settings) -> SemanticCacheProtocol | None` :
  construit `DbSemanticCache(get_session(), embeddings, threshold=settings.semantic_cache_threshold,
  namespace=settings.semantic_cache_namespace)` enveloppé dans `BudgetedSemanticCache` ;
  toute exception → None + warning (zéro régression).
- `create_app` : `semantic_cache = semantic_cache or _build_semantic_cache(settings)` dans le
  bloc « vraie base montée » ; passé à `run_agent(..., semantic_cache=semantic_cache)`.

## Critères d'acceptation

- [ ] `uv run pytest -q -m "not integration"` vert avec les nouveaux tests TDD :
  BudgetedSemanticCache (dégradation après 5 erreurs, recovery au succès, stats),
  config (threshold 0,5 → ValidationError ; namespace invalide → ValidationError),
  `_build_semantic_cache` (None si DB down, instance Budgeted sinon),
  fake existant `FakeSemanticCache` inchangé et toujours conforme au protocole.
- [ ] Test intégration pgvector marqué : isolation namespace (store "a" / lookup "b" →
  None ; lookup "a" → hit).
- [ ] `ruff check`, `ruff format --check`, `ty check` propres ; dashboard inchangé.
- [ ] `uv run alembic upgrade head` applique 0014 (couvert par test_db).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/alembic/versions/0014_semantic_cache_namespace.py` | création |
| `backend/src/investia/agent/semantic_cache.py` | namespace constructeur + `BudgetedSemanticCache` |
| `backend/src/investia/config.py` | 2 nouveaux champs validés |
| `backend/src/investia/main.py` | `_build_semantic_cache` + câblage `run_agent(semantic_cache=...)` |
| `.env.example` | doc des 2 variables |
| `backend/tests/test_semantic_cache.py` | tests TDD (budget, config, intégration namespace) |
| `docs/STATUS.md`, `docs/09-decisions.md` | D101 |

## Comment vérifier

```bash
cd backend && uv run pytest -q -m "not integration" && uv run ruff check . && uv run ty check
```

## Hors périmètre

- Namespace par requête/user réel (l'app est mono-user derrière Authelia ; le namespace
  est par déploiement en v1).
- Purge/éviction du cache, métrique `cache_degraded` dans `AgentResult` (stats() suffit).
- Cache du gateway LiteLLM lui-même (hors notre code — procédure VPS : config LiteLLM).
