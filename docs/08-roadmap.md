# 08 — Roadmap

Ordre choisi : **du cœur vers l'avancé**. Chaque étape repose sur la précédente et se termine par une vérification claire.

| Étape | Contenu | Terminé quand |
|---|---|---|
| **0 — Fondations** | Dépôt GitHub privé, CI/CD (GitHub Actions : uv + ruff + pytest + coverage), structure du repo, Docker Compose local, PostgreSQL + Redis, squelette API FastAPI async, gestion des clés | `cd deploy && docker compose --env-file ../.env up` démarre tout, `/health` et `/ready` répondent 200, la CI est verte sur un premier push |
| **1 — Boucle + outils** | Boucle d'agent, outils prix / historique / indicateurs / actualités, connecteurs de données, cache Redis, routeur Jev (petit : GPT-6 Luna, gros : Mistral Large 4) | En ligne de commande, l'agent répond à une question avec des chiffres issus d'outils |
| **2 — Garde-fous + traces** | Validation de format, des chiffres, du langage ; enregistrement des exécutions en base | Une réponse avec chiffre inventé est bloquée ; toute exécution est rejouable |
| **3 — Evals + mémoire** | Jeu d'evals, commande unique, scores en base ; mémoire courte et longue | Les scores s'enregistrent, une régression se voit en chiffres |
| **4 — Dashboards + portefeuille** | API du portefeuille simulé (10 000 €, ajustable en mode admin), 4 pages (React 19 + TanStack + AG-UI pour le chat), SSE pour le temps réel | Les 4 pages fonctionnent en local, le mode admin ajuste le capital |
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

Étape 0. Le plan détaillé existe : `docs/superpowers/plans/2026-10-30-etape-0-fondations.md` (relu et corrigé le 31/10/2026). Les étapes 1 et 4 sont très grosses : à découper avant de les planifier (Q15).
