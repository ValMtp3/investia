# Spec — 24a : subagents A2A async par défaut (exécution parallèle par niveaux)

*Écrite le : 17/11/2026 | Étape roadmap : 24 (veille D94, piste « équipes de subagents async par défaut » : opencode v2.3.0, crush teams, DSH AgentTeam) | Statut : validée le 17/11/2026, TERMINÉE le 17/11/2026*

## Objectif

`run_multi_agent` enchaîne aujourd'hui les agents A2A en **boucle séquentielle stricte** (`orchestrator.py`), même quand ils sont indépendants. On passe à une exécution **par niveaux topologiques** : les agents dont toutes les dépendances sont satisfaites tournent en parallèle (`asyncio.gather`), comme les « teams » de subagents d'opencode/crush.

## Pourquoi

La veille du 15/11 (D94) note : « rendre le retour des sous-agents A2A async par défaut » est la prochaine étape validée. Aujourd'hui, si le routeur 18a choisit plusieurs agents indépendants, on paie leurs latences en série. Le pipeline canonique (analyste → risque → rédacteur) est une chaîne de dépendances : il reste sémantiquement identique, donc zéro régression.

## Changements prévus

1. **Nouveau `backend/src/investia/agents/plan.py`** :
   - `AgentSpec(name, requires: list[str])` — `requires` = champs du contexte produits par d'autres agents (ex. `["analysis"]`).
   - `AGENT_SPECS` pour les 3 agents existants : `analyste` requires `[]`, `risque` requires `["analysis"]`, `redacteur` requires `["analysis", "verdict"]`.
   - `topological_levels(agents: list[str]) -> list[list[str]]` : niveau 0 = agents dont `requires` ne contient aucun champ produit par un agent de la sélection ; niveau N+1 = agents dont toutes les deps sont dans les niveaux < N. Cycle ou dep inconnue → `ValueError`.
2. **`orchestrator.py` — `run_multi_agent(..., parallel: bool = True)`** :
   - Chaque niveau est exécuté via `asyncio.gather(*(delegate(...) ...), return_exceptions=True)` ; on attend tout le niveau, puis si un agent a échoué → `RuntimeError("agent X indisponible")` (comportement actuel : run bloqué).
   - Les agents d'un niveau reçoivent le même payload d'entrée : la question brute au niveau 0, sinon le `context` JSON sérialisé (comme aujourd'hui).
   - Le `context` se remplit après chaque niveau : champ `analysis` (sortie `analysis`/`answer`/`text`), champ `verdict` (sortie du `risque`). La réponse finale = sortie du dernier agent du dernier niveau (inchangé).
   - Events : `a2a_delegate` gagne un champ `level` ; si un niveau comporte > 1 agent, event `a2a_parallel` {agents, level} émis avant le niveau (et step tracé). Pipeline canonique = 3 niveaux de 1 → aucun `a2a_parallel`, flux identique.
   - Gate risque inchangée : si `risque` est délégué et pas `ok` → status `blocked` (il dépend de `analysis`, donc jamais exécuté avant l'analyste).
3. **Routeur 18a inchangé** : `choose()` renvoie toujours une liste ; c'est l'orchestrateur qui la topologie-sorte. Ordre canonique conservé pour le fallback.

## Contraintes

- Zéro régression : pipeline canonique = chaîne linéaire → ordre, events et steps strictement identiques ; `test_agents_a2a.py` et `test_agents_router.py` **inchangés et verts**.
- `parallel=False` = boucle séquentielle d'aujourd'hui (opt-out testable).
- Pas de dépendance nouvelle. Pas de changement de `main.py` (défaut `True` en dur, pas exposé dans l'API en v1).
- TDD : tests d'abord.

## Critères d'acceptation

- [x] `uv run pytest backend/tests/test_agents_parallel.py -q` passe (TDD, ~7 tests).
- [x] `topological_levels(["analyste","risque","redacteur"])` == `[["analyste"],["risque"],["redacteur"]]` ; cycle → `ValueError`.
- [x] Preuve de parallélisme : fake caller avec 2 agents racine (`["analyste","macro"]`) qui bloque sur `asyncio.Event` tant que les 2 appels n'ont pas démarré → le run termine (deadlock impossible en séquentiel) + event `a2a_parallel` émis avec les 2 agents.
- [x] Pipeline canonique : aucun event `a2a_parallel`, `a2a_delegate` dans le même ordre qu'avant, `test_agents_a2a.py` vert sans modification.
- [x] Erreur d'un agent dans un niveau parallèle → run échoue (`RuntimeError`), status `error`, comme en séquentiel.
- [x] `parallel=False` → ordre strictement séquentiel même avec 2 agents racine.
- [x] Suite : `cd backend && uv run pytest -q -m "not integration"` → 768 + nouveaux tests passed / 1 skip ; `ruff check`, `ruff format --check`, `ty check` propres sur les fichiers touchés.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/agents/plan.py` | nouveau : `AgentSpec`, `AGENT_SPECS`, `topological_levels` |
| `backend/src/investia/agents/orchestrator.py` | niveaux topologiques + `asyncio.gather` + events `a2a_parallel`/`level` |
| `backend/tests/test_agents_parallel.py` | nouveau : tests TDD |
| `docs/STATUS.md`, `docs/09-decisions.md` (D106) | doc |

## Comment vérifier

```bash
cd backend && uv run pytest tests/test_agents_parallel.py tests/test_agents_a2a.py tests/test_agents_router.py -q
cd backend && uv run pytest -q -m "not integration"
cd backend && uv run ruff check src/investia/agents tests/test_agents_parallel.py && uv run ruff format --check src/investia/agents && uv run ty check src/investia/agents
```

## Hors périmètre

- Soumission A2A non-bloquante (submit → task_id → poll `GetTask`) : le parallélisme se fait côté orchestrateur, pas côté protocole.
- Nouveaux agents « racine » (macro, news…) : l'infra est prête, les agents viendront plus tard.
- Exposition du param `parallel` dans `POST /api/agents/run` (défaut True en dur en v1).
- Métrique d'eval `parallelisme` dans le runner (18b like) — plus tard.
- Changement du dashboard (les steps `a2a_event` 20c s'affichent déjà au fur et à mesure).
