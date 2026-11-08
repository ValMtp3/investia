# Spec — 11 : Rôles PostgreSQL applicatifs sans SUPERUSER (risque D53 reporté)

*Écrite le : 2026-11-08 | Étape roadmap : 11 | Statut : terminée (2026-11-08) — reste le one-shot VPS côté propriétaire*

## Objectif

Le backend et LiteLLM ne se connectent plus avec le compte **superuser** `POSTGRES_USER` (risque assumé/reporté de la revue de sécurité D53). Deux rôles applicatifs sans privilège d'admin : `investia_app` (owner de la base `investia`) et `litellm_app` (owner de la base `litellm`). Le compte superuser reste, **réservé au conteneur `backup`** (pg_dump) et au healthcheck.

## Pourquoi

Un service compromis (LiteLLM est exposé en interne, le backend aussi) ne devait pas pouvoir lire/modifier n'importe quelle base ni créer des rôles. Principe du moindre privilège : chaque service = son rôle, sa base.

## Décisions (D68, validées avec le propriétaire le 08/11/2026)

- **Deux rôles séparés** : `investia_app` (base `investia`, utilisé par `DATABASE_URL` et Alembic) et `litellm_app` (base `litellm`, utilisé par `LITELLM_DATABASE_URL`). `NOSUPERUSER NOCREATEDB NOCREATEROLE`, `LOGIN`.
- **Superuser conservé pour le backup uniquement** : `POSTGRES_USER`/`POSTGRES_PASSWORD` restent le compte admin, utilisés par le conteneur `backup` (pg_dump a besoin de lire tous les catalogues) et `pg_isready`. Documenté dans le guide VPS.
- **Application sur le VPS (volume existant)** : les scripts `docker-entrypoint-initdb.d` ne tournent qu'à la création du volume → script one-shot `deploy/postgres/apply-app-roles.sh` (rejoue le script d'init idempotent dans le conteneur) + nouvelles variables dans le `.env` du VPS + nouvelles URLs de connexion. Exécuté par le propriétaire (D55).

## Contrat

- `deploy/postgres/init/03-create-app-roles.sh` : idempotent (rejouable), saute proprement sans les mots de passe (local), crée/met à jour les rôles, `ALTER DATABASE ... OWNER TO ...`, `REVOKE CONNECT ... FROM PUBLIC`, `REASSIGN OWNED` des objets existants dans chaque base.
- Compose : `INVESTIA_APP_DB_PASSWORD` / `LITELLM_APP_DB_PASSWORD` passés au service `postgres` (comme `AUTHELIA_DB_PASSWORD`).
- `.env.example` : URLs `investia_app` / `litellm_app`, nouvelles variables vides (hygiène secrets), `POSTGRES_USER=investia` annoté « admin, backup uniquement ».
- `deploy/postgres/apply-app-roles.sh` : one-shot VPS (`docker compose exec postgres sh .../03-create-app-roles.sh`), secrets jamais affichés.

## Vérifications

- [x] Tests statiques (`backend/tests/test_postgres_roles.py`, 11 tests) : rôles sans SUPERUSER, transfert des bases, `REVOKE CONNECT` (y compris `postgres`/`template1`), `CREATE EXTENSION vector` fait par l'admin, URLs .env.example, env passés au compose, backup reste sur le compte admin, script one-shot présent sans echo de secret.
- [x] **Vérif réelle** sur un PostgreSQL jetable (pgvector:pg17, volume temporaire) : init sans erreur et rejouable 2 fois ; `\du` → `investia_app`/`litellm_app` sans attribut admin ; `investia_app` crée/écrit dans `investia` mais est **refusé** sur `litellm`, `postgres`, `template1` et pour `CREATE ROLE` ; idem `litellm_app` ; tables existantes transférées (owner `investia_app`) ; **Alembic `upgrade head` en tant qu'investia_app → `0006_otel_spans (head)`, 11 tables toutes owner `investia_app`** (bug trouvé et corrigé : `CREATE EXTENSION vector` exige l'admin, `REASSIGN OWNED` refusé sur les objets partagés, catalogues système exclus des transferts) ; `pg_dump` OK avec le compte admin.
- [x] Backend : `uv run pytest -q -m "not integration"` + ruff + format + ty verts.
- [x] Procédure one-shot VPS documentée (`docs/mise-a-jour-vps-2026-11-07.md`).

## Hors périmètre

- Rôle backup dédié avec `pg_read_all_data` (pg_dump complet en non-superuser = avertissements ; le superuser reste confiné au conteneur backup).
- Rotation automatique des mots de passe.
- Chiffrement au repos, RLS (pas de multi-tenant par lignes ici).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `deploy/postgres/init/03-create-app-roles.sh` | création (idempotent) |
| `deploy/postgres/apply-app-roles.sh` | création (one-shot VPS) |
| `deploy/docker-compose.yml` | 2 nouvelles env sur le service postgres |
| `.env.example` | URLs app + 2 nouvelles variables |
| `backend/tests/test_postgres_roles.py` | tests statiques |
| `docs/07-deploiement-vps.md` (ou guide pas à pas) | procédure one-shot VPS |
| `docs/STATUS.md`, `docs/08-roadmap.md`, `docs/09-decisions.md` | avancement 11, D68 |
