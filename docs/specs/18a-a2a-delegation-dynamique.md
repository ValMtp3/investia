# Spec — 18a : délégation A2A dynamique pilotée par les evals (P9, piste 1)

*Écrite le : 14/11/2026 | Étape roadmap : 18 (P9 protocoles/multi-agents avancés) | Statut : validée le 14/11/2026, TERMINÉE le 14/11/2026 (périmètre réduit : métrique eval `routeur_agent` reportée en 18b)*

## Objectif

P9 note dans `docs/09-decisions.md` : « A2A avancé — délégation dynamique pilotée par les evals (l'orchestrateur choisit l'agent selon la tâche et son score passé, pas un pipeline fixe) ». Aujourd'hui `run_multi_agent` (6.1, D60) enchaîne toujours **analyste → risque → rédacteur** en dur dans `agents/orchestrator.py`.

On ajoute un **routeur d'agents** appris, sur le même pattern que le routeur de modèles (12h, D76) : l'orchestrateur choisit quels agents déléguer selon la question et leurs succès passés, avec **fallback sur le pipeline fixe** quand il n'y a pas assez de preuves. Le verdict « risque » reste la porte bloquante quand l'agent risque est choisi.

## Pourquoi

Un pipeline fixe paie toujours les 3 agents même pour « prix de AAPL ? ». Un routage appris sur des cas réels (comme 12h pour small/large) choisit les bons spécialistes — et reste explicable/testable en mock (k-NN, pas de modèle entraîné).

## Changements prévus

1. **Nouveau `backend/src/investia/agents/router.py`** :
   - `AgentRouter` protocol : `choose(question) -> tuple[list[str], str]` (liste d'agents + source « learned »/"fixed") et `record(question, agents, success)` ;
   - `FixedPipelineRouter` : toujours `["analyste", "risque", "redacteur"]`, source "fixed" (comportement actuel, défaut) ;
   - `LearnedAgentRouter(store, fallback=FixedPipelineRouter, k=7, min_feedbacks=5)` : k-NN pondéré sur les feedbacks passés (même formule que `LearnedRouter`) ; score par agent = Σ(sim×succès)/Σ(sim) ; agents retenus = ceux avec score ≥ `min_score` (défaut 0.5), **toujours au moins le pipeline fixe si aucun** ; l'agent `risque` reste toujours inclus s'il a un score > 0 (porte bloquante) — à affiner en spec si besoin.
2. **Store pgvector** : migration `0010_agent_feedback` (table `agent_feedback` : id, question, embedding 1536, agent, success, created_at + index HNSW cosinus — même pattern que migration `0008_router_feedback`) + `DbAgentFeedback` (record/neighbors, pattern `DbRouterFeedback`).
3. **`run_multi_agent(..., router: AgentRouter | None = None)`** : `router=None` → pipeline fixe (zéro régression) ; sinon `agents, source = await router.choose(question)`, délégation dans l'ordre choisi, event SSE `a2a_route` {agents, source} + step tracé, feedback `record(question, agents, status=="ok")` en fin de run (erreur avalée). Le verdict risque bloque toujours si « risque » est délégué.
4. **Câblage** `main.py` (`/api/agents/run`) : `LearnedAgentRouter` construit si `DbAgentFeedback` dispo (comme `DbRouterFeedback` en 12h), sinon `None` (pipeline fixe). Le feedback est enregistré après chaque run multi-agent (succès = status ok).

## Contraintes

- Zéro régression : `router=None` = comportement 6.1 identique ; tests `test_agents_a2a.py` existants inchangés et verts.
- Le verdict risque reste bloquant quand l'agent risque tourne (jamais de réponse sans gate risque quand il est choisi).
- Pas de dépendance nouvelle (pgvector + embeddings existants, comme 0008).
- TDD : tests d'abord (router appris avec store fake, orchestrateur avec router fake, métrique eval).

## Critères d'acceptation

- [x] `FixedPipelineRouter.choose` → 3 agents, source "fixed" ; `LearnedAgentRouter` avec < min_feedbacks → fallback fixed ; avec feedbacks → agents scorés (score ≥ 0.5), ordre canonique, gate `risque` toujours incluse, source "learned" ; 6 tests déterministes (store fake).
- [x] `run_multi_agent(router=...)` : délégation selon le choix, event `a2a_route` (émis seulement si router fourni — zéro changement de flux sinon), feedback `record` succès/échec, verdict risque toujours bloquant (status "blocked" remonté) ; `router=None` → pipeline fixe, tests existants inchangés. 3 tests orchestrateur.
- [x] Migration `0010_agent_feedback` + `DbAgentFeedback` (neighbors aplati 1 ligne = 1 voisin par agent) + test d'intégration pgvector ; `alembic heads` = 0010.
- [x] Câblage `main.py` (`/api/agents/run`) : `LearnedAgentRouter(DbAgentFeedback(get_session(), embeddings))` construit au démarrage, fallback `None` (pipeline fixe) si indisponible.
- [x] `uv run pytest -q -m "not integration"` : 631 passed / 1 skip ; ruff / format / ty propres sur les fichiers touchés.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/agents/router.py` | nouveau : protocol + Fixed + Learned |
| `backend/src/investia/agents/router_store.py` | nouveau : `DbAgentFeedback` |
| `backend/src/investia/agents/orchestrator.py` | param `router`, event `a2a_route`, feedback |
| `backend/alembic/versions/0010_agent_feedback.py` | migration |
| `backend/src/investia/main.py` | câblage |
| `backend/tests/test_agents_router.py`, `test_agents_a2a.py` | tests TDD |
| `docs/STATUS.md`, `docs/09-decisions.md` (P9 → D85) | doc |

## Comment vérifier

```bash
cd backend && uv run pytest tests/test_agents_router.py tests/test_agents_a2a.py -q
cd backend && uv run pytest -q -m "not integration"
cd backend && uv run alembic heads   # 0010
```

## Hors périmètre (18b et P9, plus tard)

- Métrique d'eval `routeur_agent` + cas mock dans le runner d'evals (le runner ne tourne que `run_agent` aujourd'hui — 18b).
- Streaming A2A, agent cards enrichies (capacités + métriques), auth inter-agents renforcée.
- MCP sampling / OAuth 2.1 dynamic client registration ; AG-UI avancé (état partagé, generative UI).
- Le routeur d'agents ne *crée* pas de nouveaux agents — il choisit parmi les 3 existants.
