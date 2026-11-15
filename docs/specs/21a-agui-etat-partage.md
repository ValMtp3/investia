# Spec 21a — AG-UI : état partagé du run (StateSnapshotEvent) — P9.3

> Chantier 21 — piste P9.3 (AG-UI avancé), sans CopilotKit (D57 : on garde
> notre client SSE maison, zéro dépendance ajoutée). Le backend sait déjà
> émettre le flux en protocole AG-UI 1.0 (`?protocol=agui`, étape 15c) ;
> 21a ajoute l'**état partagé** : le serveur publie l'état structuré du run
> (`StateSnapshotEvent`), le frontend le maintient et l'affiche.

## Veille factuelle (14/11/2026)

- Spec AG-UI 1.0 : `StateSnapshotEvent` (snapshot = JSON libre, remplace
  l'état) et `StateDeltaEvent` (JSON Patch RFC 6902). Package embarqué
  `ag-ui-protocol 1.0.0` expose les deux (vérifié en local).
- D57 : pas de migration vers CopilotKit — le client SSE maison reste le
  transport ; on décode juste les blocs `data: {"type": ...}` AG-UI côté front.

## Objectif

1. Backend : un accumulateur d'état de run émet un `StateSnapshotEvent` après
   chaque event du flux (protocol=agui), sur `/agent/run` **et**
   `/api/agents/run`. La boucle `run_agent` / `run_multi_agent` ne sont pas
   modifiées (accumulateur côté sink, comme le mapping 15c).
2. Frontend : `streamAgentRun` / `streamMultiAgentRun` acceptent
   `protocol: "agui"` ; un store React reçoit les snapshots ; la page Agent
   affiche un panneau « État du run » (question, mode, statut, agents, steps
   structurés) alimenté en direct.

## Choix tranchés (avec le propriétaire)

- **Snapshot à chaque event** plutôt que deltas JSON Patch : volume faible
  (mono-utilisateur perso), zéro risque de patch mal formé, plus simple à
  tester. Les deltas restent possibles plus tard.
- Le mode **legacy reste le défaut** des endpoints (zéro régression 15c) ;
  le frontend bascule en `agui` pour bénéficier du panneau d'état.

## Contrat détaillé

### 1. Backend — `agent/agui.py` + routes

- Nouveau `RunStateAccumulator` (dans `agui.py`) :
  ```python
  class RunStateAccumulator:
      def snapshot(self) -> dict: ...          # état courant
      def apply(self, kind, payload) -> None: ...  # met à jour l'état
      def event(self, kind, payload) -> StateSnapshotEvent | None
  ```
  État : `{"question", "mode", "run_id", "status": "running|ok|blocked|error",
  "agents": [...], "steps": [{"kind", "at", "summary"}…]}`.
  - `start` → question/mode/run_id, status=running, steps=[]
  - `a2a_route` → agents = payload.agents
  - `a2a_delegate`/`tool_call`/`llm_call`/`guardrail`/`a2a_event` → append step
    (summary court : ex. tool_call → `"tool get_quote"`)
  - `done`/`error` → status final
- `to_agui_events` inchangé ; c'est la **route** qui, en protocol=agui,
  insère le `StateSnapshotEvent` après les events AG-UI de chaque kind :
  `format_agui_sse` gagne un param optionnel `state_event: BaseEvent | None`.
- Routes `/agent/run` et `/api/agents/run` : en mode agui, instancier un
  accumulateur par requête, appeler `acc.apply(kind, payload)` puis émettre
  `acc.event(...)`.

### 2. Frontend — `lib/sse.ts` / `api.ts` / `pages/Agent.tsx`

- `streamAgentRun(question, onEvent, signal, protocol?)` et idem multi :
  URL += `?protocol=agui` si demandé. Le parser lit `data.type` (AG-UI) au
  lieu de la ligne `event:` ; on garde la rétrocompat legacy (détection :
  présence de `event:` → legacy, sinon `type` AG-UI).
- `AgentEvent` gagne `{ kind: "state_snapshot"; payload: RunState }`.
- Page Agent : panneau « État du run » (Module) affiché pendant le run :
  statut, mode, agents délégués (badges), liste des steps structurés.
  Le rendu texte des steps (stepText) reste tel quel.

### 3. Tests (TDD)

Backend (`test_agui.py`) :
1. `RunStateAccumulator` : start → snapshot initial ; tool_call → step ajouté ;
   a2a_route → agents ; done → status final.
2. `format_agui_sse` avec state_event → le bloc contient STATE_SNAPSHOT.
3. Route `/agent/run?protocol=agui` : le flux contient RUN_STARTED + STATE_SNAPSHOT
   + TEXT_MESSAGE_* + RUN_FINISHED (test existant 15c à compléter).
4. Zéro régression : `protocol=legacy` → aucun bloc STATE_SNAPSHOT (test 15c inchangé).

Frontend (`Agent.test.tsx`) :
5. Flux agui mocké (blocs `data: {"type":"STATE_SNAPSHOT",...}`) → le panneau
   « État du run » affiche le statut et les steps.

## Fichiers touchés

- `backend/src/investia/agent/agui.py` (accumulateur + format_agui_sse)
- `backend/src/investia/main.py` (2 routes, protocol=agui)
- `backend/tests/test_agui.py`
- `dashboard/src/api.ts`, `dashboard/src/lib/sse.ts`, `dashboard/src/pages/Agent.tsx`, `dashboard/src/__tests__/Agent.test.tsx`
- `docs/STATUS.md`, `docs/09-decisions.md` (D91)

## Critères d'acceptation

- Backend : suite non-integration verte, ruff/format/ty propres.
- Dashboard : 111+ tests verts, tsc/build propres.
- `protocol=legacy` : octets identiques à avant (test 15c).
- En mode agui, le panneau « État du run » se met à jour en direct.

## Hors périmètre (21b, plus tard)

- Generative UI (CustomEvent `ui_component` rendu dans le chat).
- StateDeltaEvent (JSON Patch).
- CopilotKit (exclu, D57).
