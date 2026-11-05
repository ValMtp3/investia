# Spec — 4.6 : Outil `get_portfolio` pour l'agent + résumé portefeuille sur la page Agent

*Écrite le : 2026-11-05 | Étape roadmap : 4.6 | Statut : terminée le 2026-11-05 (branche `feat/get-portfolio`)*

## Objectif

L'agent a un nouvel outil **`get_portfolio`** qui renvoie l'état complet du portefeuille simulé (`PortfolioService.get_portfolio()` tel quel : cash, positions valorisées avec source + horodatage, `positions_value`, `total_value`, devise EUR). La page **Agent** du dashboard affiche en plus un résumé compact du portefeuille à côté du chat.

## Pourquoi

Roadmap 4.6 : « Branche le portefeuille simulé dans le harness — l'agent voit l'état du portefeuille dans ses réponses. » `docs/03-harness.md` prévoit `get_portfolio` (étape 4) avec la règle « sorties avec source et horodatage ». Aujourd'hui `build_tools()` ne reçoit aucun service portefeuille : ni `/agent/run`, ni la CLI, ni les evals ne peuvent l'utiliser. Décisions propriétaire du 2026-11-05 : sortie = `get_portfolio()` complet ; périmètre = harness + page Agent ; evals câblés aussi ; branche `feat/get-portfolio`.

## Contraintes

- **Zéro dépendance ajoutée** ; l'outil suit le pattern existant (`BaseTool[T]`, schéma Pydantic, `ToolError` en cas d'échec, `to_openai_tool()`).
- L'outil est **sans argument** (le portefeuille par défaut est unique) et en **lecture seule au sens métier** : aucun ordre, aucun ajustement de capital. (Précision revue 05/11/2026 : `PortfolioService.get_portfolio()` crée le portefeuille par défaut au premier appel s'il est absent — comportement idempotent préexistant, partagé avec `GET /portfolio` ; inchangé pour éviter toute régression.)
- Sortie = `PortfolioService.get_portfolio()` inchangé (déjà source + horodatage par position). Pas de nouveau calcul côté outil.
- `build_tools(market, memory_store=None, embeddings=None, portfolio_service=None)` : `get_portfolio` n'est enregistré **que** si `portfolio_service` est fourni (rétrocompatible : les evals mock et les tests existants sans portefeuille ne changent pas).
- Câblage : `POST /agent/run` (main.py) et la CLI passent leur `PortfolioService` ; le runner d'evals accepte un `portfolio_service` injectable (les evals live avec DB l'utilisent ; le mode mock peut rester sans).
- Le prompt système (`agent/prompts.py`) cite `get_portfolio` dans la liste des outils autorisés pour les chiffres.
- Page Agent : module « Portefeuille » compact (valeur totale, cash, valeur des positions) via le hook `usePortfolio()` existant (endpoint `GET /portfolio` déjà en place) ; états chargement/erreur via `role="status"` / `ErrorNotice` ; la page ne casse pas si `/portfolio` tombe (le chat continue).
- Ne pas casser : les 4 outils marché, la mémoire, les garde-fous (le chiffre du portefeuille vient d'un outil → compté comme sourcé), `/agent/run`, la CLI, les tests existants, les evals mock.
- Accessibilité : module nommé, états lisibles, pas de page blanche.

## Critères d'acceptation

- [x] `backend/src/investia/tools/portfolio.py` : `GetPortfolioTool` (name `get_portfolio`, args vide, description pour le LLM) ; `run()` renvoie le dict du service ; toute exception → `ToolError("get_portfolio", ...)` avec un **message générique** (le détail est loggé côté serveur, jamais renvoyé au LLM ni persisté dans les traces — revue sécurité 05/11/2026).
- [x] `to_openai_tool()` de l'outil : `parameters` avec `required: []` (aucun argument requis).
- [x] `build_tools(market, portfolio_service=svc)` contient `get_portfolio` ; sans `portfolio_service`, il est absent.
- [x] `POST /agent/run` : un run dont le LLM appelle `get_portfolio` produit un événement `tool_call` `ok: true` ; le payload du portefeuille est transmis au LLM (message `role: tool`) et persisté dans la trace `tool_call` (champ `result`) — l'événement SSE lui-même ne transporte que name/arguments/ok (contrat existant de tous les outils, inchangé). Test avec faux LLM + faux service + faux trace store qui conserve les payloads.
- [x] CLI : `build_tools` reçoit le `PortfolioService` construit sur la session.
- [x] Evals : `run_evals(..., portfolio_service=...)` passe l'outil à `build_tools` quand fourni (test avec faux service) ; sans, rien ne change.
- [x] `agent/prompts.py` cite `get_portfolio`.
- [x] `cd backend && uv run pytest -q -m "not integration" && uv run ruff check . && uv run ruff format --check . && uv run ty check` passent (nouveaux tests : `test_tools_portfolio.py`, test SSE tool_call get_portfolio, test evals câblage).
- [x] Page `/agent` : module « Portefeuille » avec valeur totale / cash / positions (module nommé, `role="status"` au chargement, `ErrorNotice` en erreur) ; `cd dashboard && npx vitest run && npm run lint && npm run build` passent (nouveau test Agent.test.tsx : le module s'affiche, et la page fonctionne même si /portfolio renvoie 500).
- [x] Vérification réelle : outil `get_portfolio` exécuté contre la base scratch (PostgreSQL local, migrations 0005 appliquées) avec un vrai `PortfolioService` → payload complet avec `source` + `price_timestamp` ; test d'intégration `test_portfolio_integration.py` passé en local ; le chemin `POST /agent/run` est couvert par le test SSE avec LLM fictif.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/tools/portfolio.py` | création : `GetPortfolioTool` |
| `backend/src/investia/tools/__init__.py` | `build_tools(..., portfolio_service=None)` enregistre `get_portfolio` si fourni |
| `backend/src/investia/main.py` | `/agent/run` : `build_tools(market, portfolio_service=portfolio_service)` |
| `backend/src/investia/cli.py` | construit `PortfolioService` et le passe à `build_tools` |
| `backend/src/investia/evals/runner.py` (+ `__main__.py`) | `run_evals(..., portfolio_service=None)` le transmet à `build_tools` |
| `backend/src/investia/agent/prompts.py` | cite `get_portfolio` dans les outils autorisés |
| `backend/tests/test_tools_portfolio.py` | création : outil (succès, ToolError, schéma sans args), build_tools avec/sans service |
| `backend/tests/test_sse.py` | test : run avec appel `get_portfolio` → tool_call ok |
| `backend/tests/test_evals.py` (ou runner) | test : evals câblent le portefeuille quand fourni |
| `dashboard/src/pages/Agent.tsx` | module « Portefeuille » (résumé compact via `usePortfolio`) |
| `dashboard/src/__tests__/Agent.test.tsx` | renderAgent avec QueryClientProvider + fetch stub /portfolio ; tests module + erreur /portfolio + payload malformé |
| `docs/STATUS.md`, `docs/08-roadmap.md`, `docs/09-decisions.md` | avancement 4.6, roadmap cochée, note de décision |

## Comment vérifier

```bash
cd backend && uv run pytest -q -m "not integration" && uv run ruff check . && uv run ruff format --check . && uv run ty check
cd dashboard && npx vitest run && npm run lint && npm run build
# live : lancer le backend contre une base scratch, POST /agent/run (LLM fictif
# appelant get_portfolio), observer l'événement tool_call ; curl /portfolio
```
