# Spec — 6.1 : Multi-agents en A2A (analyste / risque / rédacteur)

*Écrite le : 2026-11-07 | Étape roadmap : 6.1 | Statut : terminée le 2026-11-07 (branche `feat/a2a-multi-agents`)*

## Objectif

Trois agents spécialisés communiquent par le **protocole A2A v1.0** (HTTP) : l'**analyste** (interroge les outils marché + portefeuille), le **gestionnaire de risque** (vérifie les garde-fous), le **rédacteur** (produit la réponse finale structurée). L'utilisateur envoie sa question à l'orchestrateur, qui délègue via A2A et renvoie la réponse combinée.

## Pourquoi

Roadmap étape 6 + `docs/03-harness.md` §10 : plusieurs agents spécialisés qui communiquent en A2A. D24 (protocoles modernes 2026), D60 (3 endpoints dans le backend, `a2a-sdk` officiel, pas de nouveau conteneur).

## Contraintes

- **Une dépendance ajoutée avec accord** : `a2a-sdk` (officiel AAIF/Google), version épinglée via `uv add`.
- 3 endpoints dans le backend existant : `/agents/analyste`, `/agents/risque`, `/agents/redacteur` — chacun sert son **agent card** (`/.well-known/agent-card.json` ou équivalent SDK) et accepte des tâches A2A. Communication en HTTP interne Docker (`investia-backend` se parle à lui-même, ou orchestrateur interne).
- Derrière Authelia comme tout le reste (même préfixe, EDGE_SECRET) : zéro surface réseau nouvelle. Le nginx du dashboard aiguille déjà `/api/` ; ajouter `/agents/` si exposé en dehors de `/api` — préférer `/api/agents/...` pour ne rien changer au proxy.
- Chaque agent réutilise les briques existantes : outils (`build_tools`), garde-fous (`run_all_checks`), prompt système. Pas de réécriture.
- Le flux : question → analyste (appelle les outils, produit une analyse brute) → risque (garde-fous sur l'analyse) → rédacteur (réponse finale formatée + disclaimer) → réponse à l'utilisateur. Chaque délégation est tracée (run_steps, nouveaux kinds `a2a_delegate`).
- Zéro régression : la boucle `run_agent` actuelle (étape 1-5) continue de marcher telle quelle ; le mode multi-agents est un endpoint/chemin à part (`POST /agent/run-multi` ou flag).
- Pas de secret exposé dans les agent cards ; erreurs A2A lisibles (pas de stack trace côté client).

## Critères d'acceptation

- [x] `uv add a2a-sdk==<version>` ; `pyproject.toml`/`uv.lock` à jour.
- [x] `backend/src/investia/agents/` : `analyste.py`, `risque.py`, `redacteur.py` + agent cards servies sur `/api/agents/{nom}/.well-known/agent-card.json`.
- [x] `POST /api/agents/run` (orchestrateur) : question → délégation A2A analyste → risque → rédacteur → réponse finale ; chaque étape tracée en base (kind `a2a_delegate` avec agent + statut).
- [x] Test avec LLM fake : le flux complet produit une réponse au format garde-fous (4 sections + disclaimer) ; un refus du risque bloque la réponse (comme aujourd'hui).
- [x] Les 3 agent cards listent les bons outils/capacités.
- [x] `cd backend && uv run pytest -q -m "not integration" && uv run ruff check . && uv run ruff format --check . && uv run ty check` passent (nouveau `test_agents_a2a.py`).
- [x] Dashboard : la page `/agent` peut envoyer vers le mode multi-agents (sélecteur ou URL) et affiche les délégations en direct (événements SSE `a2a_delegate`) ; `npx vitest run && npm run lint && npm run build` passent.
- [x] Vérification réelle : lancer le backend (base scratch), appeler l'orchestrateur avec LLM fictif, voir les 3 délégations dans la trace (`GET /traces/{id}`).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/pyproject.toml` / `uv.lock` | ajout `a2a-sdk` |
| `backend/src/investia/agents/` | création : 3 agents + cards + orchestrateur |
| `backend/src/investia/main.py` | routes `/api/agents/...` |
| `backend/src/investia/agent/loop.py` | (si réutilisé) inchangé ou mode multi |
| `backend/tests/test_agents_a2a.py` | création |
| `dashboard/src/pages/Agent.tsx` + `api.ts` | mode multi + événements `a2a_delegate` |
| `dashboard/nginx.conf` | (si besoin) location `/api/agents/` — normalement déjà couvert par `/api/` |
| `docs/STATUS.md`, `docs/08-roadmap.md`, `docs/09-decisions.md` | avancement 6.1, D60 (déjà noté) |

## Comment vérifier

```bash
cd backend && uv sync && uv run pytest -q -m "not integration" && uv run ruff check . && uv run ruff format --check . && uv run ty check
cd dashboard && npx vitest run && npm run lint && npm run build
# live : backend sur base scratch, POST /api/agents/run {"question": ...} (LLM fictif),
# GET /api/agents/analyste/.well-known/agent-card.json, trace du run
```

## Hors périmètre

- Pas de nouveau conteneur Docker (D60).
- Pas de paiement x402 / AP2 (extensions A2A, hors sujet).
- Pas de découverte d'agents externe (pas d'annuaire public) : les 3 agents sont connus en dur.
- La comparaison frameworks est la 6.2, pas ici.
