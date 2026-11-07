# Spec — 5.1 : Validation humaine avant ordre simulé (human-in-the-loop)

*Écrite le : 2026-11-07 | Étape roadmap : 5.1 | Statut : terminée le 2026-11-07 (branche `feat/validation-humaine`)*

## Objectif

Quand l'agent propose un ordre d'achat/vente via l'outil `simulate_order`, la boucle s'interrompt, émet un événement SSE `approval_request` dans le chat `/agent` du dashboard, et **attend ton accord** (boutons Valider / Refuser). Aucun ordre n'est exécuté sans accord explicite ; **pas de réponse = refus** après un délai (D57).

## Pourquoi

Roadmap étape 5 : « Aucun ordre simulé sans ton accord. » `docs/03-harness.md` §8 prévoit l'arrêt de l'agent avant un ordre simulé. Décision D57 (2026-11-07) : événement SSE maison + bouton dans le chat (pas de migration CopilotKit), tout ordre soumis à validation, timeout = refus, trace en base dans le run, paramètres = symbole + achat/vente + quantité.

## Contraintes

- **Zéro nouvelle dépendance** : on réutilise le client SSE maison du dashboard (`dashboard/src/lib/sse.ts`) et on ajoute un événement + un POST.
- Nouvel outil agent `simulate_order(symbol, side: buy|sell, quantity > 0)` enregistré dans `build_tools` quand un `portfolio_service` est fourni (rétrocompatible, comme `get_portfolio`).
- La boucle `run_agent` traite `simulate_order` comme un **outil spécial** : au lieu d'exécuter directement, elle émet `approval_request` {run_id, symbol, side, quantity, prix estimé si dispo}, loggue un step `approval_request` (statut `pending`) dans le run, puis **attend la décision** via un registre en mémoire (`ApprovalRegistry` : run_id → asyncio.Queue). Délai max d'attente (ex. 300 s) : au-delà, décision = `refused`, l'agent reprend avec un message « ordre refusé (timeout) ».
- La décision arrive par `POST /agent/runs/{run_id}/approval` (body `{decision: "approved"|"refused"}`) : elle est écrite en base (step `approval` avec la décision, statut final) puis poussée dans la queue du run. 404 si run inconnu, 409 si déjà décidé, 422 si body invalide.
- Si `approved` : exécution réelle via `portfolio_service.place_order(symbol, side, quantity)` (dernier prix connu + frais 0,1 %, D35), le résultat est renvoyé au LLM comme résultat d'outil classique. Si `refused` : résultat d'outil = « ordre refusé par l'utilisateur », le LLM poursuit.
- La trace montre tout : step `approval_request` (pending) + step `approval` (approved/refused) + step `tool_call` final (ok/erreur). Rejouable via `GET /traces/{run_id}`.
- Dashboard page `/agent` : à la réception de `approval_request`, le chat affiche un bloc « Ordre proposé : acheter 3 AAPL » avec **[Valider]** / **[Refuser]** (boutons accessibles clavier, `aria-live` déjà présent sur le flux) ; au clic, POST vers `/agent/runs/{run_id}/approval` ; à réception de l'événement suivant (`tool_call` simulate_order ou `approval`), le bloc se fige (désactivé, « Validé » / « Refusé »). Le chat ne casse pas si le POST échoue (message d'erreur lisible, le flux continue).
- Ne pas casser : les 5 outils existants, la boucle sans portefeuille (CLI/evals mock restent sans `simulate_order`), `/agent/run` existant, les traces, les tests.
- Sécurité : l'endpoint d'approbation est derrière Authelia comme le reste (même préfixe `/api`) ; pas de jeton admin requis (D51 réservé à `/portfolio/adjust`) ; symboles validés (pattern existant), quantité > 0, side buy|sell.

## Critères d'acceptation

- [x] `backend/src/investia/tools/order.py` : `SimulateOrderTool` (name `simulate_order`, schéma Pydantic `symbol`/`side`/`quantity`) — mais sa `run()` ne sert que hors boucle (MCP, 5.2) ; dans la boucle, l'outil est intercepté avant exécution.
- [x] `run_agent` accepte un `approval_registry` (ou `approval_store`) optionnel ; sans, `simulate_order` se comporte comme un outil normal (rétrocompatible CLI/evals).
- [x] Appel de `simulate_order` dans la boucle → événement SSE `approval_request` {run_id, symbol, side, quantity} + step `approval_request` pending en base + attente bloquante (asyncio) avec timeout → `refused`.
- [x] `POST /agent/runs/{run_id}/approval` : 200 + step `approval` en base + déblocage de la boucle ; 404 run inconnu ; 409 déjà décidé ; 422 décision invalide. Test : approuver → `place_order` appelé (faux service) → tool_call ok ; refuser → tool_call avec « refusé » ; timeout → refus.
- [x] Événements SSE émis dans l'ordre : `approval_request` puis (après décision) `tool_call` (simulate_order) puis le flux continue (`llm_call`… `done`). Le `done` porte le statut final du run.
- [x] `build_tools(..., portfolio_service=...)` enregistre `simulate_order` ; sans service, absent.
- [x] Le prompt système (`agent/prompts.py`) cite `simulate_order` et précise qu'il exige une validation humaine.
- [x] `cd backend && uv run pytest -q -m "not integration" && uv run ruff check . && uv run ruff format --check . && uv run ty check` passent (nouveaux tests : outil, interception boucle, registry, endpoint 200/404/409/422, timeout=refus, trace des steps).
- [x] `cd dashboard && npx vitest run && npm run lint && npm run build` passent (nouveau test Agent.test.tsx : réception `approval_request` → bloc avec 2 boutons ; clic Valider → POST appelé avec approved ; le bloc se fige après décision ; page OK si le POST échoue).
- [x] Vérification réelle : lancer le backend sur la base scratch, `POST /agent/run` avec un faux LLM qui appelle `simulate_order`, observer `approval_request` dans le flux SSE, appeler `POST /agent/runs/{id}/approval` approved, voir l'ordre en base via `GET /portfolio` ; refaire avec refused → pas d'ordre. Trace visible dans `GET /traces/{id}`.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/tools/order.py` | création : `SimulateOrderTool` |
| `backend/src/investia/tools/__init__.py` | `build_tools(..., portfolio_service=None)` enregistre aussi `simulate_order` si fourni |
| `backend/src/investia/agent/loop.py` | interception de `simulate_order` : `approval_request` + attente via registry + timeout=refus |
| `backend/src/investia/agent/approval.py` | création : `ApprovalRegistry` (run_id → asyncio.Queue, en mémoire) |
| `backend/src/investia/main.py` | `POST /agent/runs/{run_id}/approval` + passage du registry à `run_agent` dans `/agent/run` |
| `backend/src/investia/tracing/store.py` | (si besoin) persistance des steps `approval_request`/`approval` — `log_step` générique suffit |
| `backend/src/investia/agent/prompts.py` | cite `simulate_order` + règle de validation humaine |
| `backend/tests/test_agent_approval.py` | création : tous les scénarios ci-dessus |
| `backend/tests/test_main_approval.py` | création : endpoint approval (200/404/409/422) |
| `dashboard/src/pages/Agent.tsx` | bloc Valider/Refuser sur `approval_request` + POST |
| `dashboard/src/lib/api.ts` (ou sse.ts) | helper `respondApproval(runId, decision)` |
| `dashboard/src/__tests__/Agent.test.tsx` | tests du bloc et du POST |
| `docs/STATUS.md`, `docs/08-roadmap.md`, `docs/09-decisions.md` | avancement 5.1, roadmap cochée, D57 (déjà noté) |

## Comment vérifier

```bash
cd backend && uv run pytest -q -m "not integration" && uv run ruff check . && uv run ruff format --check . && uv run ty check
cd dashboard && npx vitest run && npm run lint && npm run build
# live : backend sur base scratch, POST /agent/run (LLM fictif appelant simulate_order),
# lire le flux SSE (approval_request), POST /agent/runs/{id}/approval {"decision":"approved"},
# vérifier GET /portfolio et GET /traces/{id}
```

## Hors périmètre

- Pas de migration vers CopilotKit/AG-UI (D57).
- Pas de page `/approbations` dédiée : le bloc vit dans le chat `/agent`.
- Pas de validation par montant seuil : tout ordre est soumis (D57).
- Pas de serveur MCP (c'est la 5.2).
- Pas de multi-utilisateur : un seul propriétaire, une seule décision possible par run.
