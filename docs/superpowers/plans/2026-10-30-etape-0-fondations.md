# Étape 0 — Fondations : Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un repo GitHub privé avec une stack qui démarre en local (`cd deploy && docker compose up`) : API FastAPI async + PostgreSQL 17 + Redis + LiteLLM, test de santé passant, CI verte.

**Architecture:** Monorepo léger à la racine d'`Investia/` : `backend/` (Python, uv, code source + tests), `deploy/` (3 fichiers compose + init Postgres + config LiteLLM), `dashboard/` et `evals/` (vides, étapes 4 et 3), `.github/workflows/` (CI). Le backend parle à PostgreSQL (SQLAlchemy 2.0 async) et Redis (redis-py async) ; LiteLLM tourne à côté comme gateway LLM. Toute la config passe par variables d'environnement (Pydantic Settings), validée au démarrage.

**Tech Stack:** Python 3.12+ · uv · Ruff · ty · FastAPI (async) · SQLAlchemy 2.0 async + asyncpg + Alembic · redis-py (async) · Pydantic v2 / pydantic-settings · pytest + pytest-asyncio + pytest-cov · PyYAML (tests de config) · Docker Compose · PostgreSQL 17 + pgvector (`pgvector/pgvector:pg17`) · Redis 8 · LiteLLM (image épinglée) · GitHub Actions.

**Spec:** `docs/08-roadmap.md` (étape 0), `docs/02-architecture.md`, `docs/06-securite-et-legal.md`, `docs/09-decisions.md` (D10, D15, D18-D23, D29), `docs/11-stack-moderne-2026.md`.

## Dépendances à valider avant la Task 1

P1 a validé la stack, pas chaque paquet. Ces paquets sont **à valider avec l'utilisateur** avant tout `uv add` :

| Paquet | À quoi ça sert | Groupe |
|---|---|---|
| `asyncpg` | Pilote PostgreSQL async pour SQLAlchemy | app |
| `redis` (redis-py) | Client Redis async | app |
| `pydantic-settings` | Lire et valider les variables d'environnement | app |
| `pytest-cov` | Mesurer la couverture de tests | dev |
| `pyyaml` | Lire les fichiers compose et CI dans les tests de config | dev |

## Global Constraints

- Python 3.12 minimum (3.10 est EOL en oct. 2026). Gestion de projet : **uv** uniquement (`pyproject.toml`, `uv.lock` commité), pas de pip/poetry/venv manuel.
- Lint/format : **Ruff** (`ruff check` + `ruff format`), type check : **ty**. La CI bloque si l'un échoue.
- Tests d'abord (TDD) : chaque task commence par un test qui échoue, finit par un test qui passe. Pas de raccourci.
- **Tous les tests vivent dans `backend/tests/`** (y compris ceux qui vérifient `deploy/` et `.github/`), lancés depuis `backend/` avec `uv run pytest`. Les tests retrouvent la racine du repo avec `REPO_ROOT = Path(__file__).resolve().parents[2]`. Les tests qui ont besoin de PostgreSQL ou Redis portent `@pytest.mark.integration`.
- Tests **hermétiques** : un test ne lit jamais le vrai `.env` du développeur (`Settings(_env_file=None)` + variables posées avec `monkeypatch`).
- Secrets : uniquement en variables d'environnement, typés `SecretStr`. `.env` dans `.gitignore`, `.env.example` commité sans valeurs. Aucune clé dans le code.
- Docker Compose : 3 fichiers — `deploy/docker-compose.yml` (base, **aucun `ports:`**), `deploy/docker-compose.override.yml` (local, auto-chargé, ports liés à `127.0.0.1`), `deploy/docker-compose.prod.yml` (VPS, aucun port publié).
- **Commande compose officielle** : `cd deploy && docker compose --env-file ../.env up -d`. Compose charge l'override et cherche les chemins depuis le dossier où on le lance : on se place donc dans `deploy/`, et on indique le `.env` de la racine avec `--env-file`.
- Images : **une seule image par service**, la même en local, en CI et en prod (`pgvector/pgvector:pg17`, `redis:8` — à vérifier que la recherche vectorielle est incluse, sinon `redis/redis-stack-server`).
- LiteLLM : image Docker **épinglée à une version précise** (incident supply chain mars 2026), jamais `latest`.
- Docker : le backend tourne avec un **utilisateur non-root**. Un `.dockerignore` exclut `.env`, `.git`, `.venv`.
- Santé : `/health` = « le processus tourne » (sert au healthcheck Docker, ne dépend de rien). `/ready` = « la base et Redis répondent » (503 + détail `up/down` par service, jamais le texte d'une exception).
- Git : repo GitHub **privé**. Travail sur branche dédiée (`feat/etape-0-fondations`), jamais de push sur `main` sans validation. Chaque commit est validé avec l'utilisateur avant d'être fait.
- Doc en français, code et noms de variables en anglais.
- Aucune librairie ajoutée sans validation de l'utilisateur.

## Review Focus

1. **Clé requise manquante au démarrage** → erreur claire et immédiate (nom des variables manquantes, code de sortie 1, pas de stack trace) : testé dans Task 2.
2. **Base ou Redis indisponible** → l'app **démarre quand même**, `/health` reste 200, `/ready` renvoie 503 avec le détail : testé dans Task 3/4.
3. **Fuite de secret** → `.env` jamais commité, `.env.example` sans valeurs : testé dans Task 1 (`test_secrets_hygiene.py`) et lancé par la CI (Task 6).
4. **`docker compose up` depuis un clone neuf** → tout démarre, healthchecks verts : vérifié dans Task 5 avec la commande officielle.
5. **CI sur un PR** → uv + ruff + ty + pytest passent, couverture ≥ 80 % exigée : vérifié dans Task 6.

---

### Task 1: Structure du repo + toolchain Python (uv, Ruff, git)

**Files:**
- Create: `backend/pyproject.toml`, `backend/uv.lock` (généré)
- Create: `backend/.python-version`
- Create: `.gitignore`
- Create: `.env.example` (variables d'infra : `POSTGRES_PASSWORD`, `DATABASE_URL`, `REDIS_URL`, `LITELLM_BASE_URL`, `LITELLM_MASTER_KEY`, `APP_SECRET_KEY`, valeurs vides ; complété en Task 2)
- Create: `backend/src/investia/__init__.py`
- Modify: `README.md` racine (structure du repo + commandes utiles)
- Create: `dashboard/.gitkeep`, `evals/.gitkeep`
- Test: `backend/tests/test_project_config.py`, `backend/tests/test_secrets_hygiene.py`

**Interfaces:**
- Consumes: la liste des dépendances validées (section ci-dessus).
- Produces: layout de repo standard ; `pyproject.toml` déclare les dépendances app (fastapi, uvicorn[standard], sqlalchemy[asyncio], asyncpg, alembic, redis, pydantic, pydantic-settings, httpx) et le groupe dev (pytest, pytest-asyncio, pytest-cov, pyyaml, ruff, ty).

- [ ] **Step 1: Écrire les tests de config projet** — `test_project_config.py` : `pyproject.toml` existe, déclare `requires-python >= "3.12"`, `uv.lock` existe. `test_secrets_hygiene.py` : `git check-ignore .env` réussit ; chaque variable de `.env.example` dont le nom finit par `_KEY`, `_PASSWORD` ou `_SECRET` a une valeur vide.
- [ ] **Step 2: Run test → FAIL** (`cd backend && uv run pytest tests/test_project_config.py tests/test_secrets_hygiene.py -v`). Pour que `uv run` démarre, créer d'abord un `pyproject.toml` minimal ; les tests échouent sur les assertions, pas sur l'absence d'uv.
- [ ] **Step 3: Implémenter** — `pyproject.toml` complet (ruff et pytest configurés dedans, marqueur `integration` déclaré), `.python-version` (`3.12`), `.gitignore` (`.env`, `__pycache__`, `.venv`, etc.), `.env.example`, dossiers vides, `uv lock`.
- [ ] **Step 4: Run test → PASS**.
- [ ] **Step 5: `git init`, branche `feat/etape-0-fondations`, commit** (avec validation utilisateur).

### Task 2: Squelette FastAPI async + configuration (Pydantic Settings) + `/health`

**Files:**
- Create: `backend/src/investia/config.py`
- Create: `backend/src/investia/main.py`
- Modify: `.env.example` (ajout des clés optionnelles ci-dessous)
- Test: `backend/tests/test_config.py`, `backend/tests/test_health.py`

**Interfaces:**
- Consumes: `pyproject.toml` (Task 1).
- Produces: `Settings` (pydantic-settings) avec :
  - **champs requis** : `DATABASE_URL`, `REDIS_URL`, `LITELLM_BASE_URL`, `LITELLM_MASTER_KEY`, `APP_SECRET_KEY`.
  - **champs optionnels** (`None` par défaut, rendus requis à l'étape 1 quand le code s'en sert) : `OPENAI_API_KEY`, `MISTRAL_API_KEY`, `TYPESAFE_API_KEY`, `FINNHUB_API_KEY`, `COINGECKO_DEMO_API_KEY`, `STOOQ_API_KEY`.
  - Toutes les clés en `SecretStr`.
  - `get_settings()` en singleton (`lru_cache`). `create_app() -> FastAPI` avec `GET /health` → `{ "status": "ok" }` (200), sans aucune dépendance externe.

- [ ] **Step 1: Test en échec** — `test_config.py` : `Settings(_env_file=None)` sans variables → `ValidationError` qui liste les champs requis manquants ; démarrage de l'app sans config → `SystemExit(1)` et un message qui nomme les variables manquantes (`capsys`). `test_health.py` : `httpx.ASGITransport` + `GET /health` → 200 `{"status":"ok"}`.
- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError` / `ValidationError` non levée).
- [ ] **Step 3: Implémenter** `config.py` (BaseSettings, `env_file=".env"`, extra="ignore") et `main.py` (app FastAPI, route `/health`, au démarrage : erreur de validation → log clair + exit code 1, sans stack trace).
- [ ] **Step 4: Run → PASS** (variables posées avec `monkeypatch`, jamais le vrai `.env`).
- [ ] **Step 5: Commit** (validation utilisateur).

### Task 3: Connexion PostgreSQL async + Alembic + `/ready` (base)

**Files:**
- Create: `backend/src/investia/db.py`
- Create: `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/0001_baseline.py`
- Modify: `backend/src/investia/main.py` (`/ready` inclut la base)
- Test: `backend/tests/test_db.py`

**Interfaces:**
- Consumes: `Settings.DATABASE_URL` (Task 2).
- Produces: `get_engine()` (créé sans se connecter), `get_session()` (session async SQLAlchemy 2.0), `check_db() -> bool`. **Alembic est la seule source du schéma** : pas de `create_all`. La migration `0001_baseline` est vide (l'étape 0 ne crée pas de schéma métier). `GET /ready` → `{"db": "up"|"down", ...}`, 200 si tout est up, sinon 503.

- [ ] **Step 1: Test en échec** — `test_db.py` : (`@pytest.mark.integration`) avec une URL Postgres de test, `check_db()` → `True` et `SELECT 1` via session OK. (unitaire) URL injoignable → l'app démarre, `/health` → 200, `/ready` → 503 avec `"db": "down"` et sans message d'exception.
- [ ] **Step 2: Run → FAIL**.
- [ ] **Step 3: Implémenter** `db.py` (engine asyncpg, `async_sessionmaker`, fermeture propre dans le `lifespan`), `alembic/` (env.py async, `alembic upgrade head` passe sur une base vide).
- [ ] **Step 4: Run → PASS** (Postgres via `cd deploy && docker compose --env-file ../.env up -d postgres`, ou service CI).
- [ ] **Step 5: Commit** (validation utilisateur).

### Task 4: Connexion Redis async + `/ready` (cache)

**Files:**
- Create: `backend/src/investia/cache.py`
- Modify: `backend/src/investia/main.py` (`/ready` inclut Redis)
- Test: `backend/tests/test_cache.py`

**Interfaces:**
- Consumes: `Settings.REDIS_URL` (Task 2).
- Produces: `get_redis() -> redis.asyncio.Redis` (singleton, `decode_responses=True`), `check_redis() -> bool`, `close_redis()`. `/ready` renvoie `"redis": "up"|"down"` ; 503 si l'un des deux services est down.

- [ ] **Step 1: Test en échec** — `test_cache.py` : (`integration`) `PING` → `True` avec Redis up. (unitaire) Redis injoignable → `/health` 200, `/ready` 503 avec `"redis": "down"`.
- [ ] **Step 2: Run → FAIL**.
- [ ] **Step 3: Implémenter** `cache.py` + fermeture dans le `lifespan` de `main.py`.
- [ ] **Step 4: Run → PASS**.
- [ ] **Step 5: Commit** (validation utilisateur).

### Task 5: Docker Compose local complet (postgres, redis, backend, litellm)

**Files:**
- Create: `deploy/docker-compose.yml` (base, aucun `ports:`)
- Create: `deploy/docker-compose.override.yml` (local : ports sur `127.0.0.1`, build du backend)
- Create: `deploy/docker-compose.prod.yml` (prod : aucun port publié, restart policies)
- Create: `deploy/postgres/init/01-create-litellm-db.sql` (crée la base `litellm` sur le même serveur PostgreSQL)
- Create: `deploy/litellm/config.yaml` (modèles `gpt-6-luna` et `mistral-large-4` ; clés via env ; base `litellm` + master key)
- Create: `backend/Dockerfile`, `backend/.dockerignore`
- Test: `backend/tests/test_compose.py`

**Interfaces:**
- Consumes: `backend/` (Tasks 1-4), `.env.example`.
- Produces: `cd deploy && docker compose --env-file ../.env up -d` démarre `pgvector/pgvector:pg17`, `redis:8`, backend (build local, utilisateur non-root, healthcheck sur `/health`), litellm (image épinglée, ex. `ghcr.io/berriai/litellm:v1.x.y-stable` — version exacte à vérifier au moment du build, digest si possible).
- ⚠️ **Jev n'est pas déclaré dans LiteLLM** : son API renvoie des probabilités (`/api/alpha/decisions`), pas du chat. On le teste en appel direct (ou via OpenRouter) à l'étape 1, et on décidera alors s'il passe par le gateway.

- [ ] **Step 1: Test en échec** — `test_compose.py` : parser les 3 fichiers YAML ; assert services `postgres`, `redis`, `backend`, `litellm` présents ; assert **aucun `ports:` dans `docker-compose.yml` ni `docker-compose.prod.yml`** ; assert dans l'override que chaque port est lié à `127.0.0.1` ; assert image litellm épinglée (pas `latest`) ; assert que `pgvector/pgvector` est l'image de `postgres`.
- [ ] **Step 2: Run → FAIL**.
- [ ] **Step 3: Implémenter** les 3 compose + `Dockerfile` (python:3.12-slim, uv installé, `uv sync --frozen`, utilisateur non-root, commande `uvicorn investia.main:app`) + `.dockerignore` + script SQL + `litellm/config.yaml` minimal.
- [ ] **Step 4: Vérification réelle** — `cp .env.example .env` (valeurs bidons), `cd deploy && docker compose --env-file ../.env up -d`, attendre les healthchecks, `curl localhost:8000/health` → 200 et `curl localhost:8000/ready` → 200 avec db + redis `up`. Vérifier aussi `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` : aucun port publié. Documenter les commandes dans le README.
- [ ] **Step 5: Commit** (validation utilisateur).

### Task 6: CI GitHub Actions + repo GitHub privé + premier push

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `README.md` (badge CI + commandes utiles)
- Test: `backend/tests/test_ci_config.py`

**Interfaces:**
- Consumes: `backend/` (Tasks 1-4), compose (Task 5).
- Produces: CI verte sur push/PR — jobs : `ruff check`, `ruff format --check`, `ty`, `pytest --cov --cov-fail-under=80` (avec services GitHub `pgvector/pgvector:pg17` et `redis:8`, env de test). Tous les jobs tournent avec `working-directory: backend`. Les tests de config (`test_secrets_hygiene.py`, `test_compose.py`) sont donc lancés par la CI.

- [ ] **Step 1: Test en échec** — `test_ci_config.py` : parser `.github/workflows/ci.yml` ; assert les 4 jobs (ruff, format, ty, pytest) et le seuil `--cov-fail-under=80`.
- [ ] **Step 2: Run → FAIL**.
- [ ] **Step 3: Implémenter** `ci.yml` (setup-uv, cache uv, services postgres/redis, `uv run pytest --cov --cov-fail-under=80`).
- [ ] **Step 4: Créer le repo GitHub privé** (`gh repo create investia --private --source . --remote origin` — nom confirmé : `investia`, D32), puis pousser la branche (validation utilisateur requise).
- [ ] **Step 5: Vérifier la CI** — test de config en local → PASS ; la CI du push est verte sur l'UI GitHub.

---

## Self-Review (mise à jour après la relecture du 31/10/2026)

1. **Couverture spec** : étape 0 = repo GitHub privé (T6), CI (T6), structure (T1), compose local (T5), PostgreSQL+Redis (T3/T4), squelette API (T2), gestion des clés (T1/T2), healthchecks `/health` + `/ready` (T2-T4). Tout est couvert.
2. **Steps** : chaque step = une action cochable (test / run / code / run / commit).
3. **Types** : `Settings`, `get_settings()`, `create_app()`, `get_engine()`, `get_session()`, `check_db()`, `get_redis()`, `check_redis()` — cohérents entre tasks.
4. **Review Focus** : chaque item a son test (T2 config + exit code, T3/T4 `/ready`, T1 + T6 fuite de secret, T5 compose neuf, T6 CI + couverture).
5. **Proportion** : le plan décrit des interfaces et des tests, pas le code des fonctions.

## Notes d'exécution

- La création du repo GitHub et chaque push/commit sont des actions soumises à validation de l'utilisateur (règle « ne jamais décider seul »).
- ✅ Repo GitHub nommé **`investia`** (D32).
- ✅ Premier commit sur `main` avec les docs seules avant `feat/etape-0-fondations` (D31).
- ✅ Image Redis : **`redis:8`** (D33), la recherche vectorielle est côté PostgreSQL (pgvector).
- La version exacte de l'image LiteLLM sera fixée au moment du Task 5 (vérifier la dernière version stable publiée).
- Choix faits lors de la relecture, confirmés : l'app démarre même si la base ou Redis est down (`/ready` renvoie 503) ; Alembic est la seule source du schéma ; une image par service ; clés des fournisseurs optionnelles jusqu'à l'étape 1.
