# Spec 18b — métrique d'eval `routeur_agent` + cas mock (routeur d'agents 18a)

> Chantier 18b — suite de 18a (délégation A2A dynamique). Objectif : rendre le
> routeur d'agents **mesurable dans les evals**, comme le routeur LLM l'est
> depuis 12h (`routeur_choix` + `expected_model` / `mock_router_neighbors`).

## Contexte

- 18a a livré `LearnedAgentRouter` (`agents/router.py`), câblé dans
  `run_multi_agent(..., router=...)` (`agents/orchestrator.py`).
- Le runner d'evals (`evals/runner.py`) ne tourne aujourd'hui que `run_agent`
  (mono-agent). Aucun cas ne couvre la délégation multi-agents.
- `run_multi_agent` retourne un `AgentResult` qui ne porte pas la liste des
  agents délégués (elle n'existe que dans l'event SSE `a2a_route`).

## Objectif

1. Exposer les agents réellement délégués dans le résultat, pour pouvoir
   scorer le choix du routeur.
2. Ajouter la métrique `routeur_agent` dans `compute_metrics`.
3. Permettre au runner d'evals d'exécuter des **cas multi-agents** en mock
   déterministe (zéro réseau, zéro DB), avec voisins k-NN pré-remplis.
4. Ajouter 2 cas dans `evals/cases.yaml` : `a2a-learned` et `a2a-fallback`.

## Choix tranchés (avec le propriétaire, 14/11/2026)

- **Champ `agents_used: list[str]` sur `AgentResult`** (défaut `[]`), rempli
  par `run_multi_agent` — symétrique à `router_source` / `model_key` (12h).
  Zéro régression : `run_agent` ne le touche pas, la métrique ne pénalise pas
  quand `expected_agents` est absent. La métrique fonctionne en mock comme
  en live.
- **2 cas mock** (miroir du 12h) : `a2a-learned` + `a2a-fallback`.

## Contrat détaillé

### 1. `AgentResult.agents_used` (agent/loop.py)

- Nouveau champ `agents_used: list[str] = field(default_factory=list)`.
- `run_agent` ne le renseigne jamais (reste `[]`).
- `run_multi_agent` le remplit avec `used` (liste ordonnée des agents
  effectivement appelés), dans les deux retours (ok et blocked).

### 2. Métrique `routeur_agent` (evals/metrics.py)

```python
"routeur_agent": (
    1.0
    if expected_agents is None or result.agents_used == expected_agents
    else 0.0
),
```

- `compute_metrics(result, expected_tool, expected_model=None, expected_agents=None)`.
- Sans `expected_agents` : 1.0 (ne pénalise pas), même règle que `routeur_choix`.

### 3. `EvalCase` (evals/runner.py)

Nouveaux champs :

| Champ | YAML | Rôle |
|---|---|---|
| `multi_agent` | `multi_agent: true` | le cas tourne via `run_multi_agent`, pas `run_agent` |
| `expected_agents` | `expected_agents: [analyste, risque]` | liste ordonnée attendue pour `routeur_agent` |
| `mock_agent_router_neighbors` | liste de `{agent, similarity, success}` | voisins k-NN du store fake du routeur d'agents |

### 4. Runner : exécution d'un cas multi-agent

Quand `case.multi_agent` est vrai :

- Construire un `FakeAgentCaller` déterministe : `analyste` → `{"analysis": ...}`,
  `risque` → `{"ok": true, "failures": []}`, `redacteur` → `{"answer": case.mock_final}`.
- Construire le routeur : si `mock_agent_router_neighbors` est non None →
  `LearnedAgentRouter(FakeAgentFeedbackStore(neighbors))` ; sinon `None`
  (pipeline fixe, comme en prod sans router).
- Appeler `run_multi_agent(case.question, llm=MockLlm(case), tools=tools,
  caller=fake_caller, router=router, event_sink=None, trace_store=None)`.
- Métriques : `compute_metrics(result, case.expected_tool,
  expected_model=case.expected_model, expected_agents=case.expected_agents)`.

`FakeAgentFeedbackStore` (dans runner.py, pattern `FakeRouterFeedbackStore` 12h) :
implémente le protocole du store 18a (`neighbors(question, k)` → liste de
`Neighbor`-équivalents avec `agent`/`similarity`/`success`, `record(...)`
qui accumule). Adapter selon la signature exacte de `DbAgentFeedback`
(`agents/router_store.py`).

### 5. Cas dans `evals/cases.yaml`

- **`a2a-learned`** : `multi_agent: true`, 6+ voisins `analyste`/`risque` avec
  `success: true` et bonne similarité, `redacteur` absent ou `success: false`
  → `LearnedAgentRouter` choisit `["analyste", "risque"]` (gate risque incluse,
  ordre canonique). `expected_agents: [analyste, risque]` → `routeur_agent = 1.0`.
- **`a2a-fallback`** : `multi_agent: true`, `mock_agent_router_neighbors: []`
  (< min_feedbacks=5) → fallback pipeline fixe.
  `expected_agents: [analyste, risque, redacteur]` → `routeur_agent = 1.0`.

### 6. Tests (TDD, tests/test_evals.py, pattern 12h lignes 627+)

1. `test_metrics_routeur_agent` : métrique seule — match / mismatch / sans
   `expected_agents`.
2. `test_run_evals_a2a_cases` : les 2 nouveaux cas passent par le runner,
   `by_id["a2a-learned"]["metrics"]["routeur_agent"] == 1.0` et le caller fake
   a bien appelé `["analyste", "risque"]` ; idem fallback avec les 3 agents.
3. Mise à jour de `test_evals_deepeval.py` si le filtre des cas mock exclut
   aussi les cas multi-agents (même raison que `mock_router_neighbors is None`).

## Fichiers touchés

- `backend/src/investia/agent/loop.py` : champ `agents_used` sur `AgentResult`.
- `backend/src/investia/agents/orchestrator.py` : `run_multi_agent` remplit
  `agents_used=used` dans les 2 retours.
- `backend/src/investia/evals/metrics.py` : param `expected_agents` + métrique
  `routeur_agent`.
- `backend/src/investia/evals/runner.py` : 3 champs `EvalCase`, `load_cases`,
  `FakeAgentFeedbackStore`, `FakeAgentCaller`, branche `multi_agent` dans
  `run_evals`.
- `evals/cases.yaml` : 2 nouveaux cas.
- `backend/tests/test_evals.py` (+ éventuellement `test_evals_deepeval.py`).
- `docs/STATUS.md`, `docs/09-decisions.md` (décision D86).

## Critères d'acceptation

- `uv run pytest -q -m "not integration"` vert (nouveaux tests inclus).
- `ruff check`, `ruff format --check`, `ty check` propres.
- `routeur_agent` présent dans les métriques des 2 nouveaux cas, = 1.0.
- Zéro régression : tous les cas mono-agent existants inchangés
  (`agents_used == []`, métrique non pénalisante sans `expected_agents`).

## Hors périmètre

- Cas « gate risque bloque en eval » (déjà couvert unitairement en 18a).
- Eval live du multi-agent (nécessite le caller HTTP réel).
- Dashboard : affichage de la métrique (les métriques existantes sont déjà
  listées génériquement).
