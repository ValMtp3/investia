# Spec 20c — streaming A2A intermédiaire (P9.1 fin)

> Chantier 20 — fin de la piste P9.1. Objectif : le dashboard voit **en direct**
> ce que fait chaque agent délégué (appels LLM, outils, garde-fous), au lieu
> d'attendre l'artifact final de la délégation.

## Contexte (vérifié dans le code, 14/11/2026)

- Flux actuel : `POST /api/agents/run` (SSE) → `run_multi_agent` →
  `HttpA2ACaller.call` → `send_message` A2A → l'executor tourne `run_agent`
  **sans event_sink** → seuls `Task submitted`, `working` et l'artifact final
  sont émis. Les events internes du harness (`llm_call`, `tool_call`,
  `guardrail`, `plan`, `reflection`…) sont perdus pour le client.
- L'orchestrateur émet déjà vers son sink SSE : `start`, `a2a_route` (18a),
  `a2a_delegate` (running/ok/error), `answer`, `done`.
- Le dashboard (`Agent.tsx`) affiche les steps via `stepText(event)` pour les
  kinds connus, en mode multi il consomme `streamMultiAgentRun`.

## Objectif

Propager les events internes de chaque sous-agent jusqu'au SSE du dashboard :

```
run_agent (sous-agent) --event_sink--> EventQueue A2A (artifact "step")
  --> HttpA2ACaller (on_event) --> run_multi_agent --emit--> SSE "a2a_event"
  --> dashboard (step préfixé du nom de l'agent)
```

## Contrat détaillé

### 1. Executors (`agents/executors.py`) — émettre les steps du harness

- Chaque executor passe à `run_agent(..., event_sink=sink)` un sink qui émet
  chaque event comme **artifact nommé `"step"`** (pas `last_chunk`) :
  `Part(text=json.dumps({"kind": kind, "payload": payload}))`.
- L'artifact final garde son nom métier (`analysis` / `answer` / verdict
  risque) avec `last_chunk=True` — inchangé.
- Zéro régression protocole : un client qui ne lit que l'artifact final
  fonctionne comme avant (`_extract_artifact_text` prend le dernier texte,
  qui reste l'artifact final).

### 2. Caller (`agents/orchestrator.py`)

- `HttpA2ACaller.call(agent, text, on_event=None)` : pour chaque
  `StreamResponse`, extraire les artifacts nommés `"step"`, parser le JSON
  `{"kind", "payload"}` et appeler `on_event(kind, payload)` (erreur de parsing
  avalée, loggée). Le retour de `call` (artifact final) est inchangé.
- `_extract_artifact_text` inchangé.

### 3. Orchestrateur (`run_multi_agent(..., forward_agent_events=False)`)

- Défaut `False` = comportement strictement actuel (zéro régression, tests
  18a/6.1 inchangés).
- Si `True` : le caller est appelé avec `on_event` qui émet
  `{"kind": "a2a_event", "payload": {"agent": agent, "event_kind": kind, "payload": payload}}`
  vers l'`event_sink` (SSE uniquement, **pas** de step en base — la trace garde
  `a2a_delegate`).
- `FakeCaller` des tests accepte aussi `on_event` (param optionnel).

### 4. Câblage `main.py` `/api/agents/run`

- `forward_agent_events=True` en prod (pur SSE, zéro coût LLM).

### 5. Dashboard (`src/pages/Agent.tsx`, `src/api.ts`)

- Type `AgentEvent` gagne `{ kind: "a2a_event"; payload: { agent: string; event_kind: string; payload: any } }`.
- `stepText` : `case "a2a_event"` → réutilise `stepText` sur
  `{kind: event_kind, payload}` et préfixe `→ ${agent} · ` ; si le sous-event
  n'a pas de texte, afficher `→ ${agent} · ${event_kind}`.

### 6. Tests (TDD)

Backend (`tests/test_agents_a2a.py`, `test_agents_cards.py` ou nouveau) :
1. `run_multi_agent(forward_agent_events=True)` + FakeCaller émettant via
   `on_event` → events `a2a_event` présents dans le sink, avec agent/kind/payload.
2. Zéro régression : `forward_agent_events` omis → aucun `a2a_event`.
3. Caller : fake stream de StreamResponse (artifact "step" ×2 + artifact final)
   → `on_event` appelé 2×, retour = artifact final.
4. Executor : `AnalysteExecutor` avec FakeLlm + fake EventQueue → artifacts
   "step" émis (au moins 1) + artifact final `analysis`.

Frontend (`dashboard/src/__tests__/Agent.test.tsx`) :
5. Un event `a2a_event` (tool_call) produit une ligne de step préfixée de
   l'agent.

## Fichiers touchés

- `backend/src/investia/agents/executors.py`
- `backend/src/investia/agents/orchestrator.py`
- `backend/src/investia/main.py` (1 ligne)
- `backend/tests/test_agents_a2a.py` (+ executors)
- `dashboard/src/pages/Agent.tsx`, `dashboard/src/api.ts`, `dashboard/src/__tests__/Agent.test.tsx`
- `docs/STATUS.md`, `docs/09-decisions.md` (D89)

## Critères d'acceptation

- Backend : `uv run pytest -q -m "not integration"` vert ; ruff/format/ty propres.
- Dashboard : `pnpm test` (ou script du projet) vert ; build/tsc propres.
- En prod : pendant un run multi, le dashboard affiche les steps des 3 agents
  en direct (vérifié en local via les tests + manuellement sur le VPS après merge).

## Hors périmètre

- Forward des events en base (trace) — SSE only.
- Reprise de stream A2A (resumability) — autre sujet.
- Filtrage avancé côté serveur (le frontend filtre).
