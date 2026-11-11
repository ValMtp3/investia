# Spec — 12c : Raisonnement structuré, brique 3 — self-consistency (vote majoritaire)

*Écrite le : 08/11/2026 | Étape roadmap : 12 (approfondir le harness) | Statut : validée le 08/11/2026*

## Objectif

Ajouter `consistency_k: int = 1` à `run_agent` : si `k > 1`, la boucle est exécutée **k fois en parallèle** (modes `plan`/`reflect` appliqués à chaque sous-run), puis on **vote** pour la réponse majoritaire (texte normalisé ; ex-aequo → confiance déclarée la plus haute, puis la première). Le gagnant est retourné avec `consensus` (part des runs d'accord) et la liste des k réponses, tracée (SSE `consensus` + step base).

## Pourquoi

Une seule chaîne de raisonnement peut emprunter un mauvais chemin. K chaînes indépendantes + vote majoritaire réduisent les erreurs de raisonnement (self-consistency, papier 2022). C'est mesurable : la métrique `consensus` dit à quel point les k runs étaient d'accord — un consensus faible = question incertaine, à signaler à l'utilisateur.

## Contraintes

- Zéro dépendance nouvelle. `asyncio.gather` pour le parallélisme.
- Rétrocompatible : `consistency_k=1` (défaut) = un seul run, aucun changement de comportement ni de coût.
- Coût : k runs = k fois le coût (en live, à n'activer que sur les grosses analyses) ; `total_cost_cents` = somme des k runs.
- `llm_factory: Callable[[int], LlmChat] | None = None` : si fourni et k>1, le sous-run i utilise `llm_factory(i)` (utile en mock pour des réponses différentes par run ; en prod, laisser None → même client pour tous).
- Vote déterministe : normalisation (minuscules, espaces compacts) ; ex-aequo → section « Confiance » la plus haute ; encore ex-aequo → premier run.
- Métrique `consensus` : 1.0 si k=1, sinon count_gagnant / k.

## Critères d'acceptation

- [ ] `uv run pytest tests/test_reasoning_consistency.py -q` passe (tests écrits avant, TDD).
- [ ] `consistency_k=3` : 3 sous-runs exécutés, event SSE `consensus` émis + step `consensus` loggé (k, index gagnant, scores), `AgentResult.consensus` et `AgentResult.answers` remplis, coût = somme des 3 runs.
- [ ] Vote : A,A,B → gagnant A, consensus ≈ 0.667 ; A,B,C (ex-aequo) → confiance la plus haute gagne ; k=1 → consensus 1.0, answers vide.
- [ ] Métrique `consensus` dans `compute_metrics`.
- [ ] 2 nouveaux cas dans `evals/cases.yaml` (`consensus-fort` k=3 A,A,B → 0.667 ; `consensus-unanime` k=3 A,A,A → 1.0) via `mock_variants` (k séquences de réponses).
- [ ] `uv run python -m investia.evals` (mock) affiche `consensus`.
- [ ] Rétrocompat : `consistency_k=1` inchangé, tous les tests existants verts ; `uv run ruff check .`, `uv run ty check`, `uv run pytest -q -m "not integration"` verts.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/agent/loop.py` | corps actuel extrait en `_run_once(...)` ; `run_agent` gère `consistency_k` + vote + event/step `consensus` ; `AgentResult.consensus` / `.answers` |
| `backend/src/investia/agent/reasoning.py` | + `normalize_answer()`, `extract_confidence()`, `vote(answers) -> (index, consensus)` |
| `backend/src/investia/evals/metrics.py` | + `consensus` |
| `backend/src/investia/evals/runner.py` | `EvalCase.consistency_k`, `EvalCase.mock_variants` ; `run_evals` passe une `llm_factory` par variante |
| `evals/cases.yaml` | + 2 cas (`consensus-fort`, `consensus-unanime`) |
| `backend/tests/test_reasoning_consistency.py` | tests TDD |

## Comment vérifier

```bash
cd backend
uv run pytest tests/test_reasoning_consistency.py -q
uv run pytest -q -m "not integration"
uv run ruff check . && uv run ty check
uv run python -m investia.evals   # métrique consensus visible
```

## Hors périmètre

Vote pondéré par confiance du modèle (logprobs), chaîne de vérification externe (verifier LLM séparé), parallélisme au niveau des outils. Pas de changement de modèle. Le vote ne s'applique pas aux tool_calls intermédiaires (seulement à la réponse finale).
