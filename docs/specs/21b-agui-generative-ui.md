# Spec 21b — AG-UI : generative UI (CustomEvent `ui_component`) — P9.3 fin

> Chantier 21 — suite de 21a (état partagé AG-UI, mergé). Objectif : l'agent
> pousse des **composants UI** à rendre dans le chat (generative UI), via un
> `CustomEvent` AG-UI nommé `ui_component`, avec une **whitelist stricte** côté
> frontend (sécurité : jamais de HTML/composant arbitraire, jamais de code
> exécuté depuis le flux).

## Contexte

- 15c : le flux `?protocol=agui` mappe les kinds maison vers AG-UI ; les kinds
  secondaires passent en `CustomEvent(name=kind, value=payload)`.
- 21a : l'état partagé (StateSnapshotEvent) est en place ; l'adaptateur
  frontend (`makeAguiAdapter` dans `api.ts`) traduit les blocs AG-UI en
  `AgentEvent` legacy.
- Le dashboard a déjà `PriceChart` (historique d'un symbole) et
  `useMarketHistory` (TanStack Query).

## Objectif

1. Backend : dans `to_agui_events`, un `tool_call` d'un outil **chartable**
   émet, en plus du ToolCall AG-UI, un
   `CustomEvent(name="ui_component", value={"component": "HistoryChart", "props": {"symbol", "days"}})`.
   Whitelist backend : `get_history` → `HistoryChart`. Tout autre outil →
   aucun ui_component.
2. Frontend : `AgentEvent` gagne
   `{ kind: "ui_component"; payload: { component: string; props: Record<string, unknown> } }`.
   Un **registre whitelist** `UI_COMPONENTS: Record<string, ComponentType<any>>`
   dans `Agent.tsx` (seul `HistoryChart` pour l'instant) ; un composant inconnu
   est ignoré (loggé). Le rendu a lieu dans la bulle assistant
   (`msg.components: { component, props }[]`).
3. `HistoryChart` : composant qui fetch `useMarketHistory(symbol, days)` et
   rend `Skeleton` pendant le chargement, `PriceChart` ensuite (ou une note
   si pas de points).

## Contrat détaillé

### Backend (`agent/agui.py`)

```python
# 21b : outils dont le résultat se visualise dans le chat (generative UI)
UI_COMPONENT_BY_TOOL = {
    "get_history": ("HistoryChart", lambda args: {"symbol": args.get("symbol", ""), "days": int(args.get("days", 30))}),
}
```

- Dans `to_agui_events`, branche `tool_call` : après ToolCallStart/Args, si
  `name` est dans la whitelist → ajouter
  `CustomEvent(name="ui_component", value={"component": comp, "props": props})`.
- Zéro régression : `protocol=legacy` n'émet jamais de ui_component (le mapping
  legacy `format_sse` ne change pas — le ui_component n'existe qu'en AG-UI).

### Frontend

- `api.ts` : type `ui_component` dans `AgentEvent` ; dans `makeAguiAdapter`,
  `case "CUSTOM": if (evt.name === "ui_component") → kind "ui_component"`,
  sinon kind = name comme avant.
- `Agent.tsx` :
  - `UI_COMPONENTS` whitelist ; `function renderUiComponent(component, props)`
    retourne le composant ou `null` (+ console.warn) si inconnu.
  - `ChatMessage.components?: { component: string; props: Record<string, unknown> }[]` ;
    à la réception, `patchLastAssistant` append.
  - Rendu dans la bulle assistant, après les steps.
- `components/HistoryChart.tsx` : props `{symbol: string; days: number}` ;
  `useMarketHistory(symbol, days)` → Skeleton / PriceChart / EmptyState-like note.

### Tests (TDD)

Backend (`test_agui.py`) :
1. `tool_call` get_history → events contiennent CUSTOM name="ui_component"
   avec component "HistoryChart" et props {symbol, days}.
2. `tool_call` get_quote → aucun ui_component.
3. Route agui : le flux contient un bloc CUSTOM ui_component après TOOL_CALL_ARGS.

Frontend (`Agent.test.tsx`) :
4. Flux agui avec CUSTOM ui_component HistoryChart (symbol AAPL) → le
   graphique apparaît dans la bulle (mock history existant dans Marche.test —
   réutiliser le stub) ; et un ui_component inconnu ("Xyz") → rien ne rend
   (pas de crash).

## Fichiers touchés

- `backend/src/investia/agent/agui.py`, `backend/tests/test_agui.py`
- `dashboard/src/api.ts`, `dashboard/src/pages/Agent.tsx`, `dashboard/src/components/HistoryChart.tsx`, `dashboard/src/__tests__/Agent.test.tsx`
- `docs/STATUS.md`, `docs/09-decisions.md` (D92)

## Critères d'acceptation

- Backend : suite non-integration verte, ruff/format/ty propres ; legacy inchangé.
- Dashboard : tests verts, tsc/build propres.
- Sécurité : whitelist des deux côtés ; composant inconnu ignoré des deux côtés.

## Hors périmètre

- Composants arbitraires / HTML depuis le flux (interdit).
- UI dans le chat en mode legacy (le ui_component n'existe qu'en AG-UI).
- dnd, formulaires embarqués, etc.
