# Prochain déploiement VPS — checklist complète (08/11/2026)

Document unique pour ton prochain déploiement. Objectif : passer le VPS de son
état actuel à `main` = **487016e** (étapes 10 backtest + 11 rôles PostgreSQL +
fix UI #15, par-dessus ton dernier déploiement). Tout est copiable-collable.

> Règles de sécurité habituelles (D55) : jamais de secret affiché dans le terminal,
> jamais de `docker compose down -v`, aucune modif hors de `~/investia`, pas de git push.

## 0. Vérifier où en est le VPS

```bash
cd ~/investia && git checkout main && git log --oneline -1
# attendu après la procédure : 487016e
# si tu es déjà à jour, saute directement à l'étape 4 (vérifications)
```

## 1. Prérequis : le `.env` du VPS (`~/investia/.env`)

Édite `~/investia/.env` (jamais commité, jamais affiché) :

```bash
cd ~/investia
# Deux mots de passe NEufs pour les rôles applicatifs PostgreSQL (D68) :
INVESTIA_APP_DB_PASSWORD=$(openssl rand -hex 32)
LITELLM_APP_DB_PASSWORD=$(openssl rand -hex 32)
# Les écrire à la main dans .env (les lignes ci-dessus ne font que les générer,
# elles ne les écrivent pas dans le fichier — ne les affiche pas à l'écran en clair
# dans un historique partagé ; ici elles restent dans ton shell).
```

Puis mets à jour **4 lignes** dans `.env` :

```bash
# Rôles applicatifs sans SUPERUSER (D68) — le backend/LiteLLM ne passent plus par le compte admin :
DATABASE_URL=postgresql+asyncpg://investia_app:<INVESTIA_APP_DB_PASSWORD>@postgres:5432/investia
LITELLM_DATABASE_URL=postgresql://litellm_app:<LITELLM_APP_DB_PASSWORD>@postgres:5432/litellm
```

Vérifie que toutes les variables requises en prod sont bien renseignées (compose refusera de démarrer sinon, avec le nom de celles qui manquent) :
`POSTGRES_PASSWORD`, `AUTHELIA_DB_PASSWORD`, `AUTHELIA_SESSION_SECRET`, `AUTHELIA_STORAGE_ENCRYPTION_KEY`, `AUTHELIA_JWT_SECRET`, `EDGE_SECRET`, `APP_SECRET_KEY`, `INVESTIA_APP_DB_PASSWORD`, `LITELLM_APP_DB_PASSWORD`.

**Optionnel — mode live (D65)** : si tu veux que l'agent réponde vraiment, ajoute aussi les vraies clés :
`OPENROUTER_API_KEY`, `MISTRAL_API_KEY`, `FINNHUB_API_KEY`, `EODHD_API_KEY` (voir `docs/mode-live.md`). Sans elles, tout reste en simulation/mock — le site marche quand même.

## 2. ONE-SHOT : appliquer les rôles PostgreSQL dans le conteneur existant (D68)

Le volume PostgreSQL du VPS existe déjà : les scripts d'init ne rejouent pas.
Une seule fois :

```bash
cd ~/investia && git pull --ff-only origin main
sh deploy/postgres/apply-app-roles.sh
# attendu : « Rôles applicatifs à jour : investia_app (base investia), litellm_app (base litellm), sans SUPERUSER. »
```

Vérification (le rôle app doit être refusé hors de sa base) :

```bash
cd ~/investia/deploy
PW=$(grep '^INVESTIA_APP_DB_PASSWORD=' ../.env | cut -d= -f2-)
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env exec -T \
  -e PGPASSWORD="$PW" postgres psql -U investia_app -d postgres -c "SELECT 1" 2>&1 | head -1
# attendu : FATAL: permission denied for database "postgres"
```

## 3. Déployer la nouvelle version

```bash
bash ~/investia/deploy/update.sh
# = git pull main + build backend/dashboard + up -d + ps
# attendu : tous les conteneurs healthy (backend, litellm, dashboard, authelia, postgres, redis, backup)

# Migrations Alembic en tant qu'investia_app (nouvelle URL de connexion) :
cd ~/investia/deploy
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env exec backend uv run alembic upgrade head
# attendu : 0006_otel_spans (head) — no-op si déjà appliqué
```

## 4. Vérifications post-déploiement

```bash
cd ~/investia/deploy
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env"
$COMPOSE ps                                            # tout healthy
EDGE_SECRET=$(grep '^EDGE_SECRET=' ../.env | cut -d= -f2-)

curl -s http://127.0.0.1:8080/healthz                   # attendu : ok
curl -s -H "X-Edge-Secret: ${EDGE_SECRET}" http://127.0.0.1:8080/api/health   # attendu : {"status":"ok"}

# Sans session Authelia : jamais 200, toujours 302 vers /auth
curl -s -o /dev/null -w "/ -> %{http_code}\n" https://investia.valentin-fiess.fr/
curl -s -o /dev/null -w "/api/portfolio -> %{http_code}\n" https://investia.valentin-fiess.fr/api/portfolio
curl -s -o /dev/null -w "/mcp/ -> %{http_code}\n" https://investia.valentin-fiess.fr/mcp/
# attendu : 302 / 302 / 302

# Nouveau (étape 10) : le backtest répond avec les courbes portefeuille vs CW8.PA
curl -s -H "X-Edge-Secret: ${EDGE_SECRET}" http://127.0.0.1:8080/api/portfolio/backtest | head -c 300
# attendu : {"start_date":..., "benchmark_symbol":"CW8.PA", "points":[...]}

# Optionnel (mode live, D65) : live check LLM protégé par le token admin
ADMIN=$(grep '^APP_SECRET_KEY=' ../.env | cut -d= -f2-)
curl -s -H "X-Edge-Secret: ${EDGE_SECRET}" -H "X-Admin-Token: ${ADMIN}" https://investia.valentin-fiess.fr/api/live/llm
# attendu avec clés live : {"ok":true,...} ; sans clés : ok:false + raison claire
```

Dans le navigateur (connecté) :
- `/agent` : sélecteur « **Agent seul** | **Multi-agents (A2A)** » avec explication sous le sélecteur (PR #15)
- `/marche` : champ de recherche + taper un symbole à la main (ex. `air.pa` + Entrée) l'ajoute (PR #15)
- `/portefeuille` : module « **Backtest vs indice** » avec 2 courbes et les perfs %
- `/traces` : détail d'un run avec la section « **Spans OTel** » (étape 9)

Le lendemain : `docker compose ... ps` → le conteneur `backup` doit rester healthy (sauvegarde OK avec le compte admin).

## 5. Rollback si problème

```bash
cd ~/investia && git checkout <commit-avant>   # ex. le commit précédent affiché par git log
bash ~/investia/deploy/update.sh
```

⚠️ Les rôles PostgreSQL créés à l'étape 2 restent en place : ce n'est pas gênant —
l'ancien code se connecte avec l'ancienne URL (compte admin) qui fonctionne toujours.
Pour revenir en arrière sur les rôles : remettre les anciennes `DATABASE_URL` /
`LITELLM_DATABASE_URL` dans `.env` (aucun `down -v`, jamais de perte de données).

## Récapitulatif des nouveautés déployées

| PR | Contenu | Où le voir |
|---|---|---|
| #15 | Sélecteur de mode explicite + symbole manuel sur `/marche` | `/agent`, `/marche` |
| #16 | Backtest vs CW8.PA (étape 10) | `/portefeuille`, `GET /api/portfolio/backtest` |
| #17 | Rôles PostgreSQL sans SUPERUSER (étape 11, D68) | one-shot étape 2 ci-dessus |
| #14 | Spans OTel dans les traces (étape 9) | `/traces` |
