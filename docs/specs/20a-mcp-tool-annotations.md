# Spec 20a — MCP 2026 : tool annotations (P9.2) + décision sampling

> Chantier 20 — piste P9.2 (MCP spec 2026-07-28). Contexte : elicitation
> form-only déjà livré en 17g. Reste : tool annotations + sampling.

## Veille factuelle (vérifiée le 14/11/2026, sources primaires + local)

- **Spec MCP 2026-07-28 (GA)** : `sampling/createMessage`, `elicitation/create`
  et `roots/list` initiés par le serveur sont **dépréciés** (SEP-2577), remplacés
  par **MRTR** (Multi Round-Trip Requests, SEP-2322) : le tool retourne
  `resultType: "input_required"` et le client re-essaie avec les réponses.
- **FastMCP 4.2.0** (notre version, `pyproject.toml` `fastmcp>=4.2`) implémente
  les révisions legacy : `Context.sample` / `sample_step` **n'existent plus**
  (vérifié en local : `hasattr(Context, "sample") == False`), `elicit` oui.
- **Tool annotations** : toujours dans le schéma Tool 2026-07-28 —
  `ToolAnnotations(title, readOnlyHint, destructiveHint, idempotentHint,
  openWorldHint)`. FastMCP 4.2 les accepte via `annotations=` sur
  `@mcp.tool(...)` (dict camelCase ou `ToolAnnotations`), sérialisées en
  camelCase dans `tools/list` (vérifié en local avec un `Client` in-memory).

## Décision sampling : NON RETENU (à consigner en D87)

Le sampling serveur→client ne sera **pas** implémenté :

1. Déprécié dans la spec 2026-07-28 (SEP-2577) — replaced by MRTR.
2. Retiré de FastMCP 4.x — pas de `ctx.sample` en 4.2.0.
3. Notre serveur appelle déjà ses propres LLM via LiteLLM avec double plafond
   de budget (17f) : déléguer la génération au LLM du client ferait sortir des
   appels du budget contrôlé. C'est un contre-sens pour ce projet.

MRTR (elicitation moderne) à réévaluer quand le SDK le supportera.

## Objectif 20a : tool annotations sur les 6 outils MCP

Dans `build_mcp_server` (`backend/src/investia/mcp_server.py`), ajouter
`annotations=` à chaque `@mcp.tool(...)` :

| Outil | readOnlyHint | destructiveHint | idempotentHint | openWorldHint | title |
|---|---|---|---|---|---|
| `get_quote` | true | false | true | true (API marché) | « Cours » |
| `get_history` | true | false | true | true | « Historique » |
| `get_indicators` | true | false | true | true | « Indicateurs » |
| `get_news` | true | false | true | true | « Actualités » |
| `get_portfolio` | true | false | true | false (DB interne) | « Portefeuille » |
| `simulate_order` | false (écrit en DB) | false | false (chaque appel = 1 simulation) | false | « Simuler un ordre » |

Implémentation : un dict d'annotations par outil, passé via
`annotations=ToolAnnotations(**...)` (import `mcp.types`) ou dict camelCase —
les deux marchent en 4.2.0. Préférer `ToolAnnotations` (typé, ty propre).

## Tests (TDD, `backend/tests/test_mcp_server.py`)

1. `test_tools_list_annotations` : `Client(mcp)` in-memory → `list_tools()`,
   assert les 5 hints de chaque outil selon le tableau ci-dessus (champ par
   champ, pas juste readOnlyHint).
2. Zéro régression : les noms/descriptions/schemas des outils inchangés
   (les tests existants de `tools/list` et `tools/call` doivent passer tels quels).

## Fichiers touchés

- `backend/src/investia/mcp_server.py` : 6 décorateurs annotés.
- `backend/tests/test_mcp_server.py` : nouveau test.
- `docs/STATUS.md` (entrée 20a), `docs/09-decisions.md` (D87 : annotations +
  décision sampling non retenu, avec les 3 raisons).

## Critères d'acceptation

- `uv run pytest -q -m "not integration"` vert.
- `ruff check` / `ruff format --check` / `ty check` propres.
- `tools/list` retourne bien les annotations en camelCase pour les 6 outils.

## Hors périmètre

- MRTR / elicitation 2026 (pas supporté par FastMCP 4.2).
- Sampling (non retenu, voir D87).
- OAuth 2.1 dynamic client registration (déjà derrière Authelia, pas de DCR).
- Changement de comportement des outils (annotations = métadonnées seulement).
