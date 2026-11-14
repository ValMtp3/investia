# Spec — 17e : tool policy pré-schéma + double dial approval × sandbox (fail-closed)

*Écrite le : 14/11/2026 | Étape roadmap : 17 | Statut : validée le 14/11/2026, TERMINÉE le 14/11/2026*

## Objectif

Deux patterns de la veille 14/11/2026 (`docs/veille-oss-2026-11-14-approfondie.md` §4.5–4.6, sources OpenClaw + Codex) :

**A. Tool policy AVANT l'appel modèle** : un outil retiré par une policy n'est **pas envoyé au modèle** — pas de schéma, le modèle ne peut pas l'appeler. Aujourd'hui nos outils sont tous envoyés (`tool_specs = [t.to_openai_tool() for t in tools.values()]` dans `loop.py`) et les garde-fous agissent après coup.

**B. Double dial approval × sandbox** : séparer « quoi » (approval policy) de « où » (sandbox mode) en **deux réglages indépendants**, tous deux fail-closed par défaut. Aujourd'hui : approval = présence d'un `ApprovalRegistry` (D57, ordres), sandbox = fail-closed 17c au runtime seulement.

## Changements prévus

1. **`tool_policy` pré-schéma dans la boucle** : nouveau param `tool_policy: set[str] | Callable[[str], bool] | None` sur `run_agent` / `_run_once`. Appliqué **avant** `tool_specs` : `tools = {n: t for n, t in tools.items() if policy(n)}`. Défaut `None` = tous les outils (zéro régression). Event + step `tool_policy` avec `withheld: [...]` (outils retirés) au démarrage du run.
2. **Config** : `DISABLED_TOOLS` (csv, ex. `DISABLED_TOOLS=run_python,web_search`, défaut vide) + helper `tool_policy_from_settings(settings) -> Callable[[str], bool] | None` dans un petit module `tools/policy.py` ; câblé dans `main.py` (2 appels à `run_agent`) et `cli.py`.
3. **Double dial** : deux env indépendants —
   - `APPROVAL_MODE` = `order` (défaut = comportement actuel D57 : validation humaine des ordres) | `off`. `main.py` ne passe `approval_registry` que si `order`.
   - `SANDBOX_MODE` = `os` (défaut, fail-closed 17c) | `off` (opt-in dev explicite, documenté). Si `os` et **aucun** backend d'isolation dispo (`check_backend_available` échoue partout) et fail-closed actif → `run_python` est ajouté aux outils désactivés (retiré pré-schéma via la policy) + warning log au démarrage. Le fail-closed runtime 17c reste en dernier recours.
   - Valeurs invalides → erreur claire au chargement (Field pydantic avec pattern/literal).
4. `.env.example` à jour.

## Pourquoi

Envoyer le schéma d'un outil interdit au modèle, c'est lui donner l'occasion de l'appeler (et de gaspiller des tokens) avant que le garde-fou ne bloque — la policy pré-schéma élimine la classe entière. Séparer les deux dials évite le faux choix « approuver = exécuter sans sandbox » : chaque axe a son propre réglage, fail-closed par défaut des deux côtés.

## Contraintes

- Zéro régression : défauts = comportement actuel (`tool_policy=None`, `APPROVAL_MODE=order`, `SANDBOX_MODE=os` avec fail-closed runtime 17c inchangé).
- Aucun outil n'est retiré pré-schéma sans trace : event/step `tool_policy` + warning log listent les outils retirés et pourquoi.
- Pas de dépendance nouvelle.

## Critères d'acceptation (TDD : tests d'abord)

- [x] `run_agent(..., tool_policy={"get_quote"})` : les schémas envoyés au LLM ne contiennent que `get_quote` à chaque appel ; event/step `tool_policy` émis avec `kept`/`withheld` ; run OK.
- [x] `tool_policy` set ou callable sync/async accepté ; `None` → tous les outils, `withheld == []`.
- [x] `tool_policy_from_settings` (nouveau `tools/policy.py`) : `DISABLED_TOOLS` parsé en csv ; vide → None.
- [x] `SANDBOX_MODE=os` + `sandbox_available=False` + fail-closed → `run_python` désactivé ; backend dispo ou `SANDBOX_MODE=off` → non retiré. `any_sandbox_backend_available()` (which + X_OK via `check_backend_available`).
- [x] Config : `disabled_tools`, `approval_mode` (order|off), `sandbox_mode` (os|off) — valeurs invalides → ValidationError. Câblage main.py (run SSE : policy + `approval_registry` si `order` + warning démarrage si sandbox os indisponible) et cli.py. `.env.example` à jour.
- [x] `uv run pytest -q -m "not integration"` : 588 passed / 1 skip ; ruff / format / ty propres.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/tools/policy.py` | nouveau : `tool_policy_from_settings`, composition sandbox |
| `backend/src/investia/agent/loop.py` | param `tool_policy` sur `run_agent`/`_run_once`, filtre pré-schéma, event `tool_policy` |
| `backend/src/investia/config.py` | `disabled_tools`, `approval_mode`, `sandbox_mode` |
| `backend/src/investia/main.py`, `cli.py` | câblage policy + dials |
| `backend/tests/test_tool_policy.py` | nouveaux tests (TDD) |
| `backend/.env.example` (ou racine), `docs/STATUS.md` | doc |

## Comment vérifier

```bash
cd backend && uv run pytest tests/test_tool_policy.py -q
cd backend && uv run pytest -q -m "not integration"
DISABLED_TOOLS=run_python uv run pytest tests/test_agent_loop.py -q  # sanity câblage
```

## Hors périmètre

- Approval per-tool « always ask » au niveau boucle (l'elicitation MCP 15a couvre déjà le HITL par outil côté MCP) ; ici `APPROVAL_MODE` = `order` | `off`.
- Sandbox mode « workspace-write » intermédiaire (Codex) — plus tard.
- Retirer des outils du serveur MCP (`mcp_server.py`) — non, la policy s'applique à la boucle agent.
