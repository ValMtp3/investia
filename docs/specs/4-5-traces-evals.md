# Spec — 4.5 : Page Traces & evals du dashboard (données réelles) + bouton « voir la trace »

*Écrite le : 2026-11-05 | Étape roadmap : 4.5 (STATUS.md du 01/11 ; l'outil `get_portfolio` de la roadmap passe en 4.6) | Statut : validée le 2026-11-05, **terminée le 2026-11-05** (branche `feat/traces-evals`)*

## Objectif

La page **Traces & evals** du dashboard affiche les vraies données déjà en base : la liste des exécutions de l'agent (`runs`), le détail pas à pas d'une exécution (`run_steps`), et les courbes des scores d'evals dans le temps (`eval_runs` / `eval_results`). La page **Agent** gagne un lien « voir la trace » vers le run qui vient de se terminer.

## Pourquoi

Doc 05 page 4 : liste des exécutions (date, question, coût, statut des garde-fous), détail pas à pas, courbes des scores d'evals. La page `Traces.tsx` est un placeholder depuis la 4.3 (« arrive à l'étape 4.4/4.5 »). STATUS.md du 01/11 déclare cette page prochaine étape. Deux constats de code : (1) il n'existe **aucune route de lecture** des traces/evals (`DbTraceStore` n'a que `get_run`, `EvalStore` que `latest_scores`) ; (2) `POST /agent/run` ne passe **pas** de `trace_store` à `run_agent` (seule la CLI le fait, `cli.py:47`) : les runs lancés depuis le dashboard ne sont pas écrits en base, et l'événement SSE `start` ne contient pas le `run_id`.

## Contraintes

- **Zéro dépendance ajoutée** : courbes d'evals avec `lightweight-charts` (`LineSeries`, déjà utilisé pour le graphique Marché), TanStack Query + Router déjà là.
- Routes **read-only ajoutées** (`GET /traces`, `GET /traces/{run_id}`, `GET /evals`) : aucun contrat existant modifié, aucune écriture en base via ces routes, pas de migration.
- Un seul changement de contrat existant, rétrocompatible : l'événement SSE `start` de `/agent/run` gagne un champ `run_id` (les autres champs inchangés). `/agent/run` passe désormais `trace_store=DbTraceStore(get_session())` à `run_agent` (comme la CLI).
- Sécurité : `run_id` typé `UUID` (422 si invalide), 404 avec message clair si inconnu ; `limit` borné (1–200, défaut 50) ; les payloads sont déjà tronqués à 4 Ko à l'écriture (`tracing/store.py`) ; aucun secret dans les réponses.
- Ne pas casser : `/market/stream`, `/market/history`, `/portfolio`, `/orders`, `/portfolio/adjust`, la CLI, les tests existants (`test_sse.py` injectera un faux store de trace).
- Accessibilité : états chargement / erreur / vide lisibles (`ErrorNotice`), régions nommées, `aria-label` sur les graphiques, navigation clavier (liens `<Link>` natifs).
- Honnêteté : un run encore `running` s'affiche comme tel ; les courbes d'evals affichent la **moyenne par métrique et par eval_run** (pas un lissage inventé).

## Critères d'acceptation

- [x] `DbTraceStore.list_runs(limit=50)` renvoie `[{id, question, status, model, turns, total_cost_cents, created_at}]` triés par `created_at` décroissant (sans `answer` dans la liste) ; `get_run` renvoie aussi `created_at` dans chaque step.
- [x] `EvalStore.list_eval_runs()` renvoie `{runs: [{id, started_at, model, commit, mode, results: [{case_id, metric, score}]}]}` triés par `started_at` décroissant.
- [x] `GET /traces?limit=30` → 200 `{runs: [...]}` ; `limit` hors 1–200 → 422.
- [x] `GET /traces/{run_id}` → 200 `{run: {...}, steps: [{turn, kind, payload, created_at}]}` ; UUID invalide → 422 ; run inconnu → 404 `{"detail": "..."}`.
- [x] `GET /evals` → 200 `{runs: [...]}` comme ci-dessus.
- [x] `POST /agent/run` : l'événement `start` contient `run_id` (non null) et le run est écrit en base (vérifié via `GET /traces/{run_id}` après un run mocké).
- [x] `cd backend && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run ty check` passent (nouveaux tests : `test_traces_api.py` avec faux stores injectés — liste, détail, 404, 422, limit borné, evals, run_id dans `start` ; `test_sse.py` mis à jour avec un faux `trace_store`).
- [x] `dashboard/src/api.ts` : `fetchTraces(limit)`, `fetchTrace(runId)`, `fetchEvals()` + hooks TanStack Query + types.
- [x] Page `/traces` : module « Exécutions » (liste : date, question, statut, tours, coût — clic sélectionne le run), module « Détail » (question, réponse, statut, étapes `llm_call`/`tool_call`/`guardrail` avec leur payload lisible), module « Evals » (une courbe par métrique, un point par eval_run, axe des dates, légende) ; états chargement/erreur/vide ; `?run=<id>` présélectionne le run (route `/traces` avec `validateSearch`).
- [x] Page `/agent` : lien « Voir la trace » vers `/traces?run=<run_id>` affiché quand le run a un `run_id` (champ ajouté au type `AgentEvent` `start`).
- [x] `cd dashboard && npx vitest run && npx tsc --noEmit && npm run build` passent (nouveaux tests : page Traces mockée — liste, détail, courbe, états vide/erreur, présélection `?run=` ; test page Agent — lien « Voir la trace »).
- [x] Vérification réelle : backend Docker reconstruit, `curl http://127.0.0.1:8000/traces` et `/evals` répondent ; un `POST /agent/run` (clés LLM fictives → erreur propre) laisse au moins le run `running`/erreur tracé, visible dans `GET /traces`.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/tracing/store.py` | `list_runs(limit)` ajouté ; `get_run` renvoie `created_at` par step |
| `backend/src/investia/evals/store.py` | `list_eval_runs()` ajouté |
| `backend/src/investia/main.py` | `create_app(trace_store=None, eval_store=None)` injectables ; routes `GET /traces`, `GET /traces/{run_id}`, `GET /evals` ; `/agent/run` passe `trace_store` à `run_agent` |
| `backend/src/investia/agent/loop.py` | événement `start` : ajout de `run_id` |
| `backend/tests/test_traces_api.py` | création : tests des 3 routes + run_id dans `start` (faux stores) |
| `backend/tests/test_sse.py` | fixture `app` : injection d'un faux `trace_store` |
| `backend/tests/test_tracing_integration.py` | assertions `get_run` adaptées (created_at) + test `list_runs` |
| `dashboard/src/api.ts` | `fetchTraces`/`fetchTrace`/`fetchEvals` + hooks + types ; `AgentEvent` `start` gagne `run_id?` |
| `dashboard/src/App.tsx` | route `/traces` avec `validateSearch` (`run?: string`) |
| `dashboard/src/pages/Traces.tsx` | vraie page : 3 modules (exécutions, détail, courbes evals) |
| `dashboard/src/pages/Agent.tsx` | lien « Voir la trace » (`/traces?run=<id>`) |
| `dashboard/src/components/EvalChart.tsx` | création : multi-courbes (une ligne par métrique), même pattern que PriceChart |
| `dashboard/src/__tests__/Traces.test.tsx`, `Agent.test.tsx` | création / mise à jour |
| `docs/STATUS.md`, `docs/08-roadmap.md`, `docs/09-decisions.md` | avancement 4.5, `get_portfolio` renommé 4.6, note de décision |

## Comment vérifier

```bash
cd backend && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run ty check
cd dashboard && npx vitest run && npx tsc --noEmit && npm run build
cd deploy && docker compose --env-file ../.env up -d --build backend   # puis :
curl -s 'http://127.0.0.1:8000/traces?limit=10' | head -c 400
curl -s 'http://127.0.0.1:8000/evals' | head -c 400
```

## Risques connus

- ⚠️ Sans clé LLM valide, `/agent/run` échoue mais le run reste tracé en `running`/erreur : la page mostrera ces runs — c'est voulu (honnêteté), le statut est affiché.
- ⚠️ `eval_runs` peut être vide (evals lancées à la main) : module Evals affiche un état vide explicite, pas de courbe inventée.
- ⚠️ Les courbes d'evals ont peu de points au début (3 cas mockés) : lisible quand même, l'axe des dates est affiché.

## Hors périmètre

Outil `get_portfolio` pour l'agent (4.6), suppression/édition de runs, filtres avancés (par statut, par date), pagination infinie, export CSV/PDF, auth supplémentaire sur ces routes (le déploiement 4 bis met Authelia devant), spans OTel GenAI (2.3, D38), courbe de valeur du portefeuille.
