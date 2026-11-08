# Guide — Mise à jour du VPS (procédure standard, versionnée dans le repo)

> **La procédure ne change plus** : elle vit dans `deploy/update.sh` (versionné).
> Sur le VPS, une mise à jour = une seule commande :
>
> ```bash
> bash ~/investia/deploy/update.sh
> ```
>
> Le script fait : `git checkout main && git pull --ff-only` → affiche le commit →
> `build backend dashboard` → `up -d` → `ps`. Rien d'autre à retenir.

> **Mode opératoire (D55)** : c'est toi (propriétaire) qui exécutes ces commandes sur le VPS,
> je te les prépare. Règles : jamais de secret affiché, jamais de `docker compose down -v`,
> aucune modification hors de `~/investia`, pas de git push, pas d'UI NPM.

## Quoi de neuf dans cette version

| Changement | Détail |
|---|---|
| Dashboard v2 (D64) | thème sombre « salle de contrôle », nouvelles pages Marché/Portefeuille/Agent/Traces, modules Ordres simulés + Ajustements |
| MCP (5.2, D58) | serveur MCP sur `/mcp` (dans le backend, servi par le nginx du dashboard) |
| Multi-agents A2A (6.1, D60) | `/api/agents/analyste\|risque\|redacteur` (agent cards + JSON-RPC) + orchestrateur `/api/agents/run` |
| Validation humaine (5.1, D57) | `POST /agent/runs/{id}/approval` pour valider/refuser un ordre simulé |
| Nouvelles routes read-only | `GET /orders`, `GET /portfolio/adjustments`, `initial_capital` dans `GET /portfolio` |
| Authelia one_factor (D63) | plus de TOTP : `deploy/authelia/configuration.yml` est monté depuis le repo, il faut **recréer** le conteneur authelia pour qu'il relise la config |

**Rien à changer dans NPM** : tout passe par le proxy host existant (`127.0.0.1:8080`, nginx du dashboard a les nouvelles locations `/mcp/` et `/api/agents/`). **Aucune nouvelle variable `.env`** requise (`A2A_BASE_URL` vaut `http://investia-backend:8000` par défaut, bon en prod).

## Commandes à exécuter sur le VPS

```bash
cd ~/investia
git fetch origin
git checkout main
git pull --ff-only origin main
git log --oneline -1        # doit afficher f3dc70c (Merge ... #4)
```

```bash
cd ~/investia/deploy
# 1. Validation syntaxe compose prod (avec tes vraies variables .env)
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env config --quiet \
  && echo "COMPOSE OK"

# 2. Rebuild backend (nouvelles deps fastmcp/a2a-sdk) + dashboard (v2 + nginx /mcp /api/agents)
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env build backend dashboard

# 3. Recréer authelia (relit configuration.yml -> one_factor) et tout remonter
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env up -d --force-recreate authelia
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env up -d

# 4. Tous les services doivent être healthy
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env ps
```

## Vérifications (depuis le VPS, puis en ligne)

```bash
# Santé interne (loopback, sans passer par NPM)
curl -s http://127.0.0.1:8080/api/health          # {"status":"ok"}
curl -s http://127.0.0.1:8080/api/agents/analyste/.well-known/agent-card.json | head -c 200
# (la card est derrière EDGE_SECRET côté nginx : sans l'en-tête X-Edge-Secret, 403 — normal)

# En ligne, sans session : redirection vers /auth, API jamais 200
curl -sI https://investia.valentin-fiess.fr/ | head -3                 # 302 -> /auth/
curl -s -o /dev/null -w "%{http_code}\n" https://investia.valentin-fiess.fr/api/portfolio   # 302
curl -s -o /dev/null -w "%{http_code}\n" https://investia.valentin-fiess.fr/mcp/             # 302
```

Puis dans ton navigateur, connecté (mot de passe seul, plus de TOTP — D63) :
1. Les 4 pages s'affichent en thème sombre.
2. `/portefeuille` affiche les modules **Ordres simulés** et **Ajustements de capital** (états vides propres si rien en base).
3. `/agent` : sélecteur « Agent seul / Multi-agents (A2A) » présent ; un ordre proposé affiche le bloc Valider/Refuser.
4. `GET /api/agents/redacteur/.well-known/agent-card.json` répond 200 une fois connecté (via le navigateur ou `curl` avec ta session).

## Rollback si problème

```bash
cd ~/investia
git checkout 6fd6719          # ancienne version (feat/get-portfolio poussée)
cd deploy
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env up -d --build \
  --force-recreate backend dashboard authelia
```

⚠️ Note : le rollback remet la config Authelia avec TOTP (`two_factor`) — la connexion redemandera un code TOTP que tu as retiré. Si tu rollback, reste en `one_factor` (ne recrée pas authelia depuis l'ancienne branche, ou réédite la config).

## Mise à jour du soir (PR #10, même jour)

Retours design après déploiement : sélecteur « Solo | Multi-agents » en boutons
segmentés sur `/agent`, et recherche d'entreprise sur `/marche` (autocomplétion
`GET /market/search`, watchlist 100 % perso en localStorage). Même procédure :

```bash
cd ~/investia && git checkout main && git pull --ff-only origin main   # attendu: 1fd394a
cd ~/investia/deploy
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env build backend dashboard
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env up -d
```

## À noter

- La CI GitHub Actions est en panne (quota épuisé depuis le 07/11) : les PR #4, #9 et #10 ont été mergées en admin après validation locale complète (280 tests backend, 100 tests frontend, ruff/ty/lint/build verts). Le quota revient le 01/12.

## Appliquer les rôles applicatifs PostgreSQL (étape 11, D68) — À FAIRE UNE FOIS SUR LE VPS

Le backend et LiteLLM ne doivent plus se connecter en superuser. Deux rôles sans
SUPERUSER sont créés (`investia_app` pour la base `investia`, `litellm_app` pour
`litellm`) ; le compte `POSTGRES_USER` reste superuser mais n'est plus utilisé que
par le conteneur `backup` (pg_dump). Les scripts d'init PostgreSQL ne tournent qu'à
la création du volume : sur le VPS (volume existant), procédure manuelle :

```bash
cd ~/investia && git checkout main && git pull --ff-only origin main
# 1. Deux mots de passe neufs dans le .env du VPS (jamais affichés, jamais commités) :
#    INVESTIA_APP_DB_PASSWORD=$(openssl rand -hex 32)
#    LITELLM_APP_DB_PASSWORD=$(openssl rand -hex 32)
#    (les écrire dans ~/investia/.env à la main, valeurs vides aujourd'hui)
# 2. URLs de connexion vers les rôles applicatifs dans le même .env :
#    DATABASE_URL=postgresql+asyncpg://investia_app:<INVESTIA_APP_DB_PASSWORD>@postgres:5432/investia
#    LITELLM_DATABASE_URL=postgresql://litellm_app:<LITELLM_APP_DB_PASSWORD>@postgres:5432/litellm
# 3. Appliquer les rôles dans le conteneur postgres existant (script idempotent) :
cd ~/investia && sh deploy/postgres/apply-app-roles.sh
# 4. Redéployer : migrations Alembic en tant qu'investia_app, puis la stack
cd ~/investia/deploy
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env exec backend uv run alembic upgrade head
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env build backend litellm 2>/dev/null || true
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env up -d
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env ps
```

Vérifications attendues : `backend` et `litellm` healthy, `curl -s http://127.0.0.1:8080/api/health` → `{"status":"ok"}` (avec `X-Edge-Secret`), connexion refusée pour `investia_app` sur la base `postgres` (`psql -U investia_app -d postgres` → « permission denied »), sauvegarde du lendemain toujours OK (healthcheck `backup`).
