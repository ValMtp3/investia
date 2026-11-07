# Spec — Étape 0 : Fondations (repo + stack locale + CI)

*Écrite le : 2026-10-31 | Étape roadmap : 0 | Statut : validée*

## Objectif

Avoir un repo GitHub public `investia` avec une stack qui démarre en local en une commande, une API FastAPI qui répond, et une CI verte.

## Pourquoi

Avant toute fonctionnalité métier, il faut une base saine : structure de repo standard, secrets jamais commités, base et cache accessibles, tests qui passent en CI. Décisions D18, D19, D23, D29, D31.

## Contraintes

- Python 3.12+, gestion de projet **uv uniquement**, lint **Ruff**, types **ty**, tests **pytest**.
- TDD : chaque task commence par un test qui échoue, finit par un test qui passe.
- Secrets uniquement en variables d'environnement (`SecretStr`), `.env` gitignoré, `.env.example` sans valeurs.
- Docker Compose : 3 fichiers (`docker-compose.yml` sans `ports:`, `override` local sur `127.0.0.1`, `prod` sans port publié). Commande officielle : `cd deploy && docker compose --env-file ../.env up -d`.
- Images épinglées (`pgvector/pgvector:pg17`, `redis:8`, LiteLLM version précise, jamais `latest`).
- Plan détaillé task par task : `docs/superpowers/plans/2026-10-30-etape-0-fondations.md` (6 tasks, exécutées une par une, commit entre chaque).

## Critères d'acceptation

- [ ] `cd deploy && docker compose --env-file ../.env up -d` démarre postgres, redis, backend, litellm (healthchecks verts).
- [ ] `curl localhost:8000/health` → 200 `{"status":"ok"}`.
- [ ] `curl localhost:8000/ready` → 200 avec `db` et `redis` à `"up"` (503 avec détail si un service est down).
- [ ] `cd backend && uv run pytest` passe (unitaires + intégration), couverture ≥ 80 %.
- [ ] `uv run ruff check .` et `uv run ty check` passent sans erreur.
- [ ] `git check-ignore .env` réussit ; `.env.example` existe sans aucune valeur de secret.
- [ ] La CI GitHub Actions est verte sur le premier push de la branche.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/pyproject.toml`, `backend/uv.lock`, `backend/.python-version` | création (toolchain uv) |
| `backend/src/investia/{__init__,config,main,db,cache}.py` | création (config, app, connexions) |
| `backend/alembic/` | création (migrations, baseline vide) |
| `backend/tests/` | création (tests config, secrets, health, db, cache, compose, CI) |
| `deploy/docker-compose*.yml`, `deploy/postgres/init/`, `deploy/litellm/config.yaml` | création (stack locale) |
| `backend/Dockerfile`, `backend/.dockerignore` | création |
| `.github/workflows/ci.yml` | création (CI) |
| `.gitignore`, `.env.example`, `README.md` | création / modification |

## Comment vérifier

```bash
cd backend && uv run pytest -q          # tous les tests passent
uv run ruff check . && uv run ty check   # lint + types OK
cp .env.example .env                     # valeurs bidons
cd ../deploy && docker compose --env-file ../.env up -d
curl localhost:8000/health               # 200 {"status":"ok"}
curl localhost:8000/ready                # 200 db+redis up
```

## Hors périmètre

- Aucun schéma métier en base (migration baseline vide), aucune route métier.
- Pas de frontend (étape 4), pas de boucle d'agent (étape 1), pas de déploiement VPS (étape 4 bis).
- Jev n'est pas déclaré dans LiteLLM à cette étape.
