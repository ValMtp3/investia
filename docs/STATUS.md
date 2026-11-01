# STATUS — où en est le projet

> **Mis à jour le : 01/11/2026.** C'est le seul endroit qui dit l'état *actuel*. Le reste des docs décrit la cible, pas le présent.

## Étape en cours

**Étape 0 — Fondations : TERMINÉE le 31/10/2026.** Branche `feat/etape-0-fondations` pushée sur GitHub (`ValMtp3/investia`), CI verte (run 41219238270 : ruff, format, ty, pytest 25 tests + couverture 89 % ≥ 80 %). Plan : `docs/superpowers/plans/2026-10-30-etape-0-fondations.md`.

- T1 structure + toolchain uv/Ruff/ty ✅ · T2 FastAPI + config + `/health` ✅ · T3 PostgreSQL async + Alembic + `/ready` ✅ · T4 Redis async ✅ · T5 Docker Compose (vérifié via OrbStack : 4 conteneurs healthy, `/health` 200, `/ready` 200, 0 port en prod) ✅ · T6 CI + push ✅
- `cd deploy && docker compose --env-file ../.env up -d` démarre tout en local ; `curl localhost:8000/ready` → 200 `{"db":"up","redis":"up"}`.

**Prochaine étape : 4.5 — page Traces & evals** (lire runs/run_steps/eval_results en base et les afficher). 4.4b terminée le 01/11/2026. (2.3 spans OTel GenAI en attente, D38.)

Avancement 4.4c/4.4d (01/11/2026) : **graphique Marché = vrais cours** (`GET /market/history`, ligne des clôtures journalières, source et devise affichées) · **cascade de sources** (D46) : AAPL = Yahoo → EODHD → Twelve Data → Massive, pause 10 min après un 429, cache 24 h ; SAP.DE sans prix en direct = dernière clôture EODHD étiquetée. Vérifié en vrai : AAPL via EODHD (Yahoo en 429), cache, pause Redis, repli SAP.DE. **À faire par le propriétaire** : créer des comptes gratuits Twelve Data et Massive et mettre `TWELVEDATA_API_KEY` / `MASSIVE_API_KEY` dans `.env` (sans clé, ces deux sources sont sautées). Durcissement après revue (même jour) : erreurs réseau/format et réponses vides tolérées par la cascade, échec total retenu 5 min, pause 429 aussi sur le prix, Redis facultatif, `/market/stream` validé (20 symboles, intervalle ≥ 1 s), graphique protégé (réponse vérifiée, pas de page blanche). Backend : 217 tests ; dashboard : 44 tests.

Avancement étape 4 : 4.1+4.2 ✅ portefeuille + API · 4.3 ✅ squelette dashboard (4 pages, build+tests+CI frontend) · **4.4a ✅ backend SSE** (`POST /agent/run` stream start/llm_call/tool_call/guardrail/answer/done, `GET /market/stream` pousse les prix, boucle émet via event_sink) · **4.4b ✅ frontend SSE** — client SSE maison zéro dépendance (`dashboard/src/lib/sse.ts`, fetch+ReadableStream, parser incrémental, abort via signal), page `/agent` chat streaming (étapes en direct aria-live, stop, erreur lisible), page `/marche` prix live (symbol/source/heure/badge différé), fix backend : `symbol` dans chaque quote + CORSMiddleware (`FRONTEND_ORIGIN`, défaut localhost:5173). 125 tests backend, 17 tests frontend, ruff/ty/tsc/build propres, test live curl OK.

Avancement étape 4 : **4.1+4.2 ✅ portefeuille simulé** — migration 0005 (portfolios/positions/orders/capital_adjustments), calculs en code (`portfolio/calc.py`, frais 0,1 % D35, prix dernier connu converti EUR), PortfolioService SQL, API (`GET /portfolio`, `POST /orders`, `POST /portfolio/adjust` admin via X-Admin-Token) — 133 tests, scénario buy/sell/adjust vérifié sur vraie base.

**Étape 3 — Evals + mémoire : terminée le 31/10/2026.** 3.1 ✅ evals (runner + métriques en code + scores en base) · 3.2 ✅ mémoire longue pgvector (table memories + HNSW, embeddings OpenRouter text-embedding-3-small, outils save_memory/recall_memory branchés au registre et à la CLI) — 121 tests, ruff/ty propres. Base de test unique : conteneur Docker pgvector (127.0.0.1:5432).

Avancement étape 3 : **3.1 ✅ evals** — runner maison (`uv run python -m investia.evals`), métriques en code (tool_used, numbers_sourced, format, langage, disclaimer, tours, coût), scores en base (`eval_runs`/`eval_results`, migration 0003), 3 cas mockés déterministes dans `evals/cases.yaml`, redteam Promptfoo (`evals/redteam.yaml`), deepeval en dev (D38) — 114 tests, ~90 % couv.

Avancement étape 2 : 2.1 ✅ garde-fous en code (format, chiffres sourcés ±0,5 %, langage interdit, disclaimer ; max 2 corrections puis refus) · **2.2 ✅ traces en base** (migration 0002 runs/run_steps JSONB, TraceStore async, branché boucle + CLI, statut ok/blocked/max_turns, test fuite de secrets) — 109 tests, 90,6 % couv. Critères étape 2 remplis : chiffre inventé bloqué (testé), exécution rejouable (get_run + steps). D43 : OpenRouter pour GPT+Jev, Mistral direct.

**Étape 1 — Boucle + outils : TERMINÉE le 31/10/2026.** 1.1 ✅ connecteurs + cache (Finnhub US, Yahoo quote Europe, EODHD historique Europe, CoinGecko, Frankfurter) · 1.2 ✅ outils agent (quote/history/indicators Polars/news) · 1.3 ✅ client LiteLLM + routeur + budget · 1.4 ✅ boucle agent CLI (`uv run python -m investia.cli "question"`) · 1.5 ✅ Jev via LiteLLM confirmé (Q10/D37, `/v1/systemone`, client `llm/jev.py`). 89+ tests, ~89 % couv. Live CLI/LLM en attente des vraies clés (`OPENAI_API_KEY`, `MISTRAL_API_KEY`, `TYPESAFE_API_KEY` dans `.env` — fictives pour l'instant).

Avancement étape 1 : 1.1 ✅ connecteurs + cache · 1.2 ✅ outils agent · **1.3 ✅ client LiteLLM** (retry, coût depuis `models.toml`, budget par exécution en centimes, routeur petit/gros en dur) — 82 tests, 93,5 % couv. EODHD live testé (SAP.XETRA, AIR.PA). ⚠️ Clés Finnhub/EODHD vues en clair dans le chat de session : à révoquer si le chat est sauvegardé. Clés manquantes pour le live LLM : `OPENAI_API_KEY`, `MISTRAL_API_KEY` dans `.env`.

Avancement étape 1 : **1.1 terminée le 31/10/2026** — connecteurs Finnhub (US temps réel) / Yahoo (Europe) / CoinGecko (crypto) / Frankfurter (taux), cache Redis TTL, routeur par symbole, 53 tests verts (91 % couverture) + test live Finnhub réel. D36 ✅ (Finnhub gratuit = US only, Europe via Yahoo, P8).

Environnement de test local : PostgreSQL 17.11 (brew, port 5433), Redis 8.10 (brew, port 6380) pour les tests `@pytest.mark.integration` ; Docker via OrbStack.

## Bloqueurs / à vérifier maintenant

| # | Quoi | Pourquoi | Statut |
|---|---|---|---|
| D36 | Couverture Europe de Finnhub en gratuit (temps réel ou US seulement ?) | Décide si on a du temps réel européen avant l'étape 1 | ✅ testé le 31/10/2026 : **gratuit = US uniquement** (quote+news US, search global). Europe = payant. Historique/prix Europe via Yahoo Finance (gratuit, testé OK), conversion via Frankfurter. Voir Q9/P8 dans `09-decisions.md` |
| D34 | Découper les étapes 1 et 4 de la roadmap en sous-étapes | Trop grosses pour un seul plan | ✅ fait le 31/10/2026 : étapes 1.1-1.5 et 4.1-4.5 dans `08-roadmap.md` |

## Zone de suppression (ne pas recréer)

| Quoi | Pourquoi retiré | Remplacé par |
|---|---|---|
| Hébergement Render | Supposé par erreur pendant le cadrage ; l'hébergement est le VPS perso | `docs/07-deploiement-vps.md` (Docker Compose derrière NPM) |
| Authentik | Trop lourd (~1-2 Go) pour un seul utilisateur | Authelia (~50 Mo), décision D12 |
| Caddy en frontal | Le VPS est partagé, NPM gère déjà 80/443 et le HTTPS | Nginx Proxy Manager existant, D13 |
| `redis-stack-server` | La recherche vectorielle est dans PostgreSQL (pgvector) | Image `redis:8`, D33 |
| pandas | Remplacé par Polars (10-100x plus rapide sur les séries de prix) | Polars + DuckDB, D30 |

## Organisation IA du projet (résumé — détail dans `AGENTS.md`)

- Règles toujours vraies : `AGENTS.md` (racine, lu par tous les outils d'IA).
- Procédures réutilisables : `.agents/skills/` (versionnées dans le repo).
- Spec avant code : `docs/specs/`.
- Commandes slash : `.claude/commands/`.
- Suivi : ce fichier.
