# STATUS — où en est le projet

> **Mis à jour le : 31/10/2026.** C'est le seul endroit qui dit l'état *actuel*. Le reste des docs décrit la cible, pas le présent.

## Étape en cours

**Étape 0 — Fondations : TERMINÉE le 31/10/2026.** Branche `feat/etape-0-fondations` pushée sur GitHub (`ValMtp3/investia`), CI verte (run 41219238270 : ruff, format, ty, pytest 25 tests + couverture 89 % ≥ 80 %). Plan : `docs/superpowers/plans/2026-10-30-etape-0-fondations.md`.

- T1 structure + toolchain uv/Ruff/ty ✅ · T2 FastAPI + config + `/health` ✅ · T3 PostgreSQL async + Alembic + `/ready` ✅ · T4 Redis async ✅ · T5 Docker Compose (vérifié via OrbStack : 4 conteneurs healthy, `/health` 200, `/ready` 200, 0 port en prod) ✅ · T6 CI + push ✅
- `cd deploy && docker compose --env-file ../.env up -d` démarre tout en local ; `curl localhost:8000/ready` → 200 `{"db":"up","redis":"up"}`.

**Prochaine étape : 3.2 — Mémoire longue (pgvector)** + evals DeepEval en CI. Spec à écrire avant le code. (2.3 spans OTel GenAI en attente, D38.)

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
