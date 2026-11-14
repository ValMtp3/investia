# Spec — 15a : MCP spec 2026-07-28 + elicitation MRTR sur simulate_order

*Écrite le : 14/11/2026 | Étape roadmap : 15 (P9 protocoles) | Statut : terminée le 14/11/2026*

## Objectif

Monter le serveur MCP sur la spec 2026-07-28 (mcp 2.3.0 déjà présent, bump fastmcp 4.1.6 → ≥4.2) et utiliser l'**elicitation MRTR** (form mode) pour demander une confirmation humaine avant tout `simulate_order` exposé en MCP — deny-by-default, comme le HITL du dashboard (D57).

## Pourquoi

Veille 14/11/2026 (brique 9) : la spec MCP 2026-07-28 rend le serveur stateless et remplace l'elicitation server-initiated par MRTR (`input_required` + re-soumission client) ; le form mode convient exactement à une confirmation d'ordre. Sampling/roots sont dépréciés (retrait au plus tôt 2027-07-28) → on ne construit rien dessus. Deps validées : bump `fastmcp>=4.2` (mcp 2.3.0 déjà installé).

## Contraintes

- `simulate_order` (wrapper MCP) gagne `ctx: Context` et appelle `await ctx.elicit(message, response_type=OrderConfirmation)` avec `OrderConfirmation(BaseModel) : confirm: bool, note: str = ""`.
- `AcceptedElicitation` + `confirm=True` → exécution. `Declined` / `Cancelled` / `confirm=False` → `ValueError("simulate_order: ordre non confirmé — aucun ordre exécuté")` (masqué côté client comme les autres erreurs internes, comportement 5.2).
- Le message d'elicitation contient symbol/side/quantity. Aucun ordre n'est jamais exécuté sans confirmation explicite.
- Les 5 autres outils MCP restent inchangés (pas de ctx).
- Zéro régression : `test_mcp_server.py` mis à jour pour le nouveau contrat (client avec `elicitation_handler` qui accepte) + nouveaux tests ; le reste de la suite inchangé.

## Critères d'acceptation

- [ ] `uv run pytest tests/test_mcp_elicitation.py -q` passe : confirm=True → ordre exécuté ; declined → erreur lisible + aucun ordre ; confirm=False → idem ; client sans `elicitation_handler` → refus + aucun ordre ; le message d'elicitation contient les paramètres de l'ordre.
- [ ] `uv run pytest tests/test_mcp_server.py -q` passe (test simulate_order mis à jour avec handler acceptant).
- [ ] `uv run pytest -q -m "not integration"` passe ; ruff/ty/format propres sur les fichiers touchés.
- [ ] `uv run python -c "import importlib.metadata as md; print(md.version('fastmcp'))"` → ≥ 4.2.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/mcp_server.py` | `OrderConfirmation`, `ctx: Context` + `ctx.elicit` dans `simulate_order` |
| `backend/tests/test_mcp_elicitation.py` | tests TDD |
| `backend/tests/test_mcp_server.py` | test simulate_order mis à jour (handler acceptant) |
| `backend/pyproject.toml` / `uv.lock` | bump fastmcp>=4.2 (validé) |

## Comment vérifier

```bash
cd backend && uv run pytest tests/test_mcp_elicitation.py tests/test_mcp_server.py -q
cd backend && uv run pytest -q -m "not integration"
```

## Hors périmètre

URL mode de l'elicitation (OAuth/paiement hors chat), migration stateless complète du transport (déjà streamable HTTP), sampling/roots (dépréciés), 15b (A2A v1.0) et 15c (AG-UI).
