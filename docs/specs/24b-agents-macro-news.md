# Spec — 24b : agents racine « macro » et « news » en parallèle de l'analyste

*Écrite le : 17/11/2026 | Étape roadmap : 24 (suite de 24a/D106) | Statut : validée le 17/11/2026, TERMINÉE le 17/11/2026*

## Objectif

Ajouter deux agents A2A **racine** (sans dépendance) — `macro` (contexte macroéconomique) et `news` (actualités) — qui tournent **en parallèle de l'analyste** grâce au plan topologique de 24a, quand le routeur learned (18a) les choisit. Le contexte multi-agents devient multi-champs : `analysis`, `macro`, `news` coexistent sans s'écraser.

## Pourquoi

24a a posé l'exécution parallèle par niveaux. Sans agents racine supplémentaires, ce parallélisme ne s'active jamais en pratique. macro/news répondent à la piste « équipes de subagents » de la veille D94 (opencode/crush lancent plusieurs spécialistes en parallèle sur la même question).

## Changements prévus

1. **`agents/plan.py`** : `AGENT_SPECS` += `macro` (requires `()`, produit `("macro",)`), `news` (requires `()`, produit `("news",)`) ; helper `produced_fields(name)` (fallback `("analysis",)` pour un inconnu).
2. **`agents/executors.py`** :
   - `MacroExecutor(llm, tools)` : `run_agent` avec un prompt macro (contexte éco/monétaire via `get_news`, `web_search`, `get_quote`) → artifact `{"macro": ...}`.
   - `NewsExecutor(llm, tools)` : `run_agent` avec un prompt actualités (symboles extraits de la question, `get_news`) → artifact `{"news": ...}`.
   - `RedacteurExecutor` : le prompt inclut les sections `Macro`/`Actualités` **uniquement si présentes** dans le contexte (zéro diff de prompt sinon).
3. **`agents/cards.py`** : `AGENT_NAMES` += `macro`, `news` + `DESCRIPTIONS`.
4. **`agents/orchestrator.py`** : le contexte se remplit via `produced_fields(agent)` (un agent racine écrit son propre champ ; fallback `analysis`) au lieu de `context["analysis"]` en dur. Le `risque` écrit toujours `verdict`. Le payload envoyé aux niveaux suivants = le context JSON complet (macro/news transmis au rédacteur automatiquement).
5. **`agents/router.py`** : `LearnedAgentRouter.choose` — ordre généralisé : `CANONICAL_PIPELINE` d'abord, puis les autres agents connus (`AGENT_SPECS`, ordre d'insertion) ; gate `risque` inchangée. `CANONICAL_PIPELINE` et `FixedPipelineRouter` **inchangés** (pipeline fixe = 3 agents).
6. **`main.py`** : `executors` += `"macro": MacroExecutor(llm, _tools)`, `"news": NewsExecutor(llm, _tools)` (montés automatiquement via `AGENT_NAMES`).

## Contraintes

- Zéro régression : `router=None` → pipeline fixe 3 agents, `macro`/`news` jamais appelés ; tests 6.1/18a/20c/24a inchangés et verts. Sans macro/news dans le contexte, le prompt du rédacteur est byte-identique.
- Pas de dépendance nouvelle. TDD.
- Le verdict `risque` reste la gate bloquante quand délégué.

## Critères d'acceptation

- [x] `uv run pytest backend/tests/test_agents_macro_news.py -q` passe (~8 tests TDD).
- [x] `topological_levels(["macro","news","analyste","risque","redacteur"])` == `[["macro","news","analyste"],["risque"],["redacteur"]]`.
- [x] Parallélisme réel : router fake `[analyste, macro, news, risque, redacteur]` → `max_active == 3` au niveau 0, un seul event `a2a_parallel` {agents: [analyste, macro, news], level: 0}.
- [x] Le rédacteur reçoit un context JSON contenant `analysis`, `macro` ET `news` (fake caller enregistre le payload).
- [x] `LearnedAgentRouter` avec feedbacks macro/news → `choose` les inclut, ordre = canonique d'abord puis macro/news ; < min_feedbacks → fallback fixe 3 agents.
- [x] `router=None` → `calls == ["analyste","risque","redacteur"]`, aucun appel macro/news.
- [x] Cards : `GET /api/agents/macro/.well-known/agent-card.json` et `/news/` → 200 (test via `create_app`).
- [x] Suite : `cd backend && uv run pytest -q -m "not integration"` → 777 + nouveaux tests passed / 1 skip ; `ruff check`, `ruff format --check`, `ty check` propres sur les fichiers touchés.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/agents/plan.py` | AGENT_SPECS += macro/news, `produced_fields` |
| `backend/src/investia/agents/executors.py` | `MacroExecutor`, `NewsExecutor`, prompt rédacteur conditionnel |
| `backend/src/investia/agents/cards.py` | AGENT_NAMES + DESCRIPTIONS |
| `backend/src/investia/agents/orchestrator.py` | context rempli via `produced_fields` |
| `backend/src/investia/agents/router.py` | ordre généralisé dans `LearnedAgentRouter.choose` |
| `backend/src/investia/main.py` | executors += macro/news |
| `backend/tests/test_agents_macro_news.py` | nouveau : tests TDD |
| `docs/STATUS.md`, `docs/09-decisions.md` (D107) | doc |

## Comment vérifier

```bash
cd backend && uv run pytest tests/test_agents_macro_news.py tests/test_agents_a2a.py tests/test_agents_parallel.py tests/test_agents_router.py tests/test_agents_cards.py -q -m "not integration"
cd backend && uv run pytest -q -m "not integration"
cd backend && uv run ruff check src/investia/agents tests/test_agents_macro_news.py && uv run ruff format --check src/investia/agents && uv run ty check src/investia/agents
```

## Hors périmètre

- macro/news dans le pipeline fixe (défaut) — non retenu, zéro régression.
- Un 3ᵉ agent racine (ex. technique/indicateurs) — possible plus tard, le plan l'accepte déjà.
- Métrique d'eval sur la présence de macro/news dans la réponse finale.
- Dashboard : rien (les steps a2a_event 20c affichent déjà les nouveaux agents).
