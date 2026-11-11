# 08 — Roadmap

Ordre choisi : **du cœur vers l'avancé**. Chaque étape repose sur la précédente et se termine par une vérification claire.

| Étape | Contenu | Terminé quand |
|---|---|---|
| **0 — Fondations** | Dépôt GitHub public, CI/CD (GitHub Actions : uv + ruff + pytest + coverage), structure du repo, Docker Compose local, PostgreSQL + Redis, squelette API FastAPI async, gestion des clés | `cd deploy && docker compose --env-file ../.env up` démarre tout, `/health` et `/ready` répondent 200, la CI est verte sur un premier push |
| **1.1 — Connecteurs données + cache** | Finnhub (quote temps réel), Stooq (historique CSV), CoinGecko Demo + Binance (crypto), Frankfurter/ECB (taux) ; cache Redis avec TTL ; tests avec fixtures (pas de réseau) | `get_quote("AAPL")` renvoie prix + source + horodatage ; le 2e appel est servi par le cache |
| **1.2 — Outils de l'agent** | `get_quote`, `get_history`, `get_indicators` (moyennes mobiles, volatilité — calculées en code avec Polars), `get_news` ; schéma d'entrée Pydantic + description pour le LLM | Chaque outil répond avec source + horodatage, testé sans appel réseau |
| **1.3 — Client LiteLLM + routeur** | Appels via le gateway (gpt-6-luna petit, mistral-large-4 gros), routeur en dur au début, budget max par exécution bloqué en code | Un appel au gateway répond, le coût est enregistré |
| **1.4 — Boucle agent en CLI** | `uv run python -m investia.cli "question"` : boucle max N tours, function calling, erreurs d'outils renvoyées lisibles au modèle | En CLI, l'agent répond à une question avec des chiffres venus des outils |
| **1.5 — Jev en test direct** | Tester l'API Jev (TypeSafe / OpenRouter) et sa compatibilité LiteLLM (Q10, D37) | On sait si Jev passe par le gateway ou en appel direct |
| **2 — Garde-fous + traces** | Validation de format, des chiffres, du langage ; enregistrement des exécutions en base | Une réponse avec chiffre inventé est bloquée ; toute exécution est rejouable |
| **3 — Evals + mémoire** | Jeu d'evals, commande unique, scores en base ; mémoire courte et longue | Les scores s'enregistrent, une régression se voit en chiffres |
| **4.1 — Modèle portefeuille en base** | Tables `portfolios`, `positions`, `orders`, `capital_adjustments` + migrations Alembic | `alembic upgrade head` applique le schéma, tests passent |
| **4.2 — API portefeuille** | Routes CRUD portefeuille, mode admin ajuste le capital (D27) | L'API répond, le capital est ajustable en admin |
| **4.3 — Squelette dashboard** | React 19 + Vite + TanStack Router/Query, les 4 pages, graphiques lightweight-charts | `npm run dev` affiche les 4 pages en local |
| **4.4 — Chat AG-UI + SSE** | Stream agent → dashboard (AG-UI/CopilotKit sur SSE, D14) | Un message de l'agent s'affiche en streaming dans le dashboard |
| **4.5 — Page Traces & evals** ✅ faite le 05/11/2026 | Lire runs/run_steps/eval_results en base et les afficher dans le dashboard, lien « voir la trace » depuis le chat | `GET /traces`, `/traces/{id}`, `/evals` répondent ; la page affiche exécutions, détail pas à pas et courbes d'evals |
| **4.6 — Outil `get_portfolio` + résumé portefeuille page Agent** ✅ faite le 05/11/2026 | Branche le portefeuille simulé dans le harness (outil `get_portfolio`) et affiche un résumé sur `/agent` | L'agent voit l'état du portefeuille dans ses réponses (source + horodatage) ; la page Agent affiche valeur totale / cash / positions |
| **4 bis — Mise en ligne** | Authelia derrière le NPM existant, proxy hosts sur `investia.valentin-fiess.fr`, VPS OVH VPS-1 partagé, sauvegardes, revue de sécurité | Rien n'est accessible sans connexion ; revue sans point bloquant |
| **5.1 — Validation humaine** ✅ faite le 07/11/2026 | Outil `simulate_order` + événement SSE `approval_request` + bouton Valider/Refuser dans le chat `/agent` (D57 : SSE maison, timeout = refus, trace en base, ordre = symbole + achat/vente + quantité) | Aucun ordre simulé sans accord ; la trace du run montre la demande et la décision |
| **5.2 — Serveur MCP** ✅ faite le 07/11/2026 | Outils Investia exposés en serveur MCP (FastMCP 4.1.6, Streamable HTTP sur `/mcp` derrière Authelia, D58) | Un client MCP externe liste et appelle les outils (`tools/list`, `tools/call`) |
| **6.1 — Multi-agents A2A** ✅ faite le 07/11/2026 | 3 agents spécialisés (analyste, risque, rédacteur) en A2A v1.0 réel via `a2a-sdk`, exposés comme 3 endpoints dans le backend (D60) | Les agents se découvrent (agent cards), se délèguent des tâches et produisent une réponse combinée |
| **6.2 — Harness reconstruit avec 3 frameworks** ✅ faite le 07/11/2026 | Le même harness dans `comparisons/` avec LangGraph, Pydantic AI, OpenAI Agents SDK (D61) | Chaque implémentation passe les mêmes evals que le harness maison |
| **6.3 — Comparaison chiffrée** ✅ faite le 07/11/2026 | Mêmes evals sur les 4 approches (maison + 3 frameworks), mock + ~2 € de réels (D62) ; métriques qualité/coût/latence ; + P7 : composant en Go comparé à Python | Rapport `docs/comparaison-etape-6.md` : chaque approche a son gain (ou non) chiffré |
| **8 — Mode live** ✅ code livré le 07/11/2026 (clés VPS à renseigner) | Vraies clés API dans `.env` VPS, live check `GET /api/live/llm` (admin token), evals réelles 6.3 avec budget 2 € bloqué en code | `docs/mode-live.md` : live check ok:true, evals réelles dans `results-live.json` |
| **7 — Dashboard v2** ✅ faite le 07/11/2026 | Thème sombre « salle de contrôle » (D64, zéro dépendance npm) + `GET /orders`, `GET /portfolio/adjustments`, `initial_capital` (read-only) ; 4 pages restylées, a11y (skip link, focus, 44px) | Spec `docs/specs/7-dashboard-v2.md` 15/15 critères cochés, captures des 4 pages relues |
| **9 — Observabilité OTel GenAI** ✅ faite le 07/11/2026 | Spans `gen_ai.chat` / `tool.call` (attributs sémantiques `gen_ai.*`) exportés dans PostgreSQL (`otel_spans`, migration 0006, liés au `run_id`), affichés dans `/traces` (D66, une seule dépendance : `opentelemetry-sdk`) | Un run produit des spans en base liés à son `run_id` (vérifié en live) ; `/traces/{id}` renvoie les spans ; page `/traces` les affiche ; 288 tests backend + 102 dashboard verts |
| **10 — Backtest vs indice de référence** ✅ faite le 08/11/2026 | Portefeuille simulé rejoué sur l'historique des clôtures (clôture du jour, frais 0,1 %, FX du jour) et comparé à un buy & hold CW8.PA depuis le capital initial ; `GET /portfolio/backtest` caché 24 h, module « Backtest vs indice » sur `/portefeuille` (D67, zéro dépendance) | Le moteur passe ses tests (frais, FX, trous, ajustements) ; l'API répond avec les vraies clôtures en live ; la page affiche 2 courbes + perfs ; 303 tests backend + 110 dashboard verts |
| **11 — Rôles PostgreSQL sans SUPERUSER** ✅ code livré le 08/11/2026 (one-shot VPS à faire par le propriétaire, D68) | `investia_app` / `litellm_app` owners de leurs bases, `NOSUPERUSER`, `REVOKE CONNECT` sur toutes les bases ; superuser réservé au backup ; script d'init idempotent + `apply-app-roles.sh` pour le VPS | Vérifié sur PostgreSQL jetable : Alembic migre en tant qu'investia_app (0006 head), connexions cross-base refusées, pg_dump admin OK ; 11 tests statiques verts |
| **12 — Approfondir le harness** (chantier en briques ; budget LLM mock d'abord) | Briques prévues : 12a plan-and-execute ✅, 12b réflexion/auto-critique ✅, 12c self-consistency ✅, 12d guardrails LLM (elephant + logprobs) ✅, 12e cache sémantique ✅, 12f outils avancés lecture seule (web_search + read_pdf) ✅ faits le 08/11/2026, 12g sandbox Python (run_python, revue sécurité faite) ✅ fait le 11/11/2026, routeur appris | Chaque brique : spec validée + plan + TDD + métriques d'evals étendues (`plan_suivi`, `reflexion`, `auto_corrections`, `consensus`, `safety_llm_ok`, `safety_logprobs_ok`, `cache_hit`), zéro dépendance sans accord |

## Règles pour chaque étape

1. Un plan court validé avec toi avant de coder.
2. Les tests d'abord (rouge, vert, amélioration), avec les skills TDD.
3. Aucune librairie ajoutée sans ton accord.
4. Avant de dire « terminé » : lancer la validation et montrer le résultat.
5. Revue de code avant chaque fin d'étape importante.

## Étape suivante

Étape 0 terminée le 31/10/2026 (branche `feat/etape-0-fondations`, CI verte). Prochaine : **1.1 — Connecteurs données + cache**, après le test D36 (couverture Europe de Finnhub). Les étapes 1 et 4 sont découpées en sous-étapes ci-dessus (D34, fait le 31/10/2026). Chaque sous-étape aura sa spec dans `docs/specs/` et son plan avant le code.
