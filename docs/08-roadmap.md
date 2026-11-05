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
| **5 — Validation humaine + MCP** | Accord humain avant ordre simulé ; serveur ou client MCP | Aucun ordre simulé sans ton accord |
| **6 — Multi-agents + comparaison** | Agents spécialisés en A2A, comparaison avec l'agent seul via les evals, **et** le même harness reconstruit avec LangGraph / Pydantic AI / OpenAI Agents SDK | Les evals montrent un gain (ou non, documenté) pour chaque approche |

## Règles pour chaque étape

1. Un plan court validé avec toi avant de coder.
2. Les tests d'abord (rouge, vert, amélioration), avec les skills TDD.
3. Aucune librairie ajoutée sans ton accord.
4. Avant de dire « terminé » : lancer la validation et montrer le résultat.
5. Revue de code avant chaque fin d'étape importante.

## Étape suivante

Étape 0 terminée le 31/10/2026 (branche `feat/etape-0-fondations`, CI verte). Prochaine : **1.1 — Connecteurs données + cache**, après le test D36 (couverture Europe de Finnhub). Les étapes 1 et 4 sont découpées en sous-étapes ci-dessus (D34, fait le 31/10/2026). Chaque sous-étape aura sa spec dans `docs/specs/` et son plan avant le code.
