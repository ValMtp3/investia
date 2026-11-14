# Spec — 12a : Raisonnement structuré, brique 1 — plan-and-execute

*Écrite le : 08/11/2026 | Étape roadmap : 12 (approfondir le harness, famille B) | Statut : validée le 08/11/2026*

## Objectif

Avant d'agir, l'agent produit un **plan explicite** (étapes numérotées avec les outils prévus). La boucle enregistre ce plan dans les traces et émet un événement SSE `plan`. Une métrique d'eval `plan_suivi` mesure si les outils réellement appelés suivent le plan.

## Pourquoi

Un agent qui agit sans plan enchaîne des appels d'outils inutiles ou incohérents. Rendre le plan explicite le rend visible dans `/traces` (rejeu d'erreurs facilité) et mesurable dans les evals — on peut enfin chiffrer « l'agent réfléchit avant d'agir ». Brique 1 du chantier « raisonnement structuré + auto-critique » (les suivantes : 12b réflexion, 12c self-consistency).

## Contraintes

- Zéro dépendance nouvelle.
- Rétrocompatible : `run_agent(..., reasoning="none"|"plan")`, défaut `"none"` → comportement actuel intact (CLI, API, A2A, evals existants).
- Le plan est un **appel LLM dédié en début de run** (1 appel de plus, gratuit en mock ; en live, activable seulement sur les grosses analyses). Le plan est parsé en JSON ; si le parsing échoue, on continue sans plan (dégradé propre, jamais de crash).
- Garde-fous en code inchangés : le plan ne remplace aucune vérification.
- Pas de changement de modèle, pas de multi-agents.

## Critères d'acceptation

- [ ] `uv run pytest tests/test_reasoning_plan.py -q` passe (tests écrits avant le code, TDD).
- [ ] En mode `reasoning="plan"` : le run émet un événement SSE `plan` avec la liste des étapes et enregistre un step `plan` en base.
- [ ] `compute_metrics` retourne une métrique `plan_suivi` : 1.0 si chaque outil appelé était prévu dans le plan (plan vide → 1.0), 0.0 sinon.
- [ ] 2 nouveaux cas dans `evals/cases.yaml` : un cas « plan suivi » (plan_suivi = 1.0) et un cas « plan non suivi » (0.0), avec `mock_plan` scripté.
- [ ] `uv run python -m investia.evals` (mode mock) affiche la métrique `plan_suivi`.
- [ ] Rétrocompat : avec `reasoning="none"` (défaut), aucun appel LLM de plan, tous les tests existants restent verts.
- [ ] `uv run ruff check .`, `uv run ty check`, `uv run pytest -q` (global) verts.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/agent/reasoning.py` | création : `make_plan()` + parsing JSON du plan |
| `backend/src/investia/agent/loop.py` | paramètre `reasoning`, appel du plan, event SSE `plan`, step `plan`, plan passé dans `AgentResult` |
| `backend/src/investia/agent/prompts.py` | `PLAN_PROMPT` (format JSON attendu) |
| `backend/src/investia/evals/metrics.py` | métrique `plan_suivi` |
| `backend/src/investia/evals/runner.py` | `EvalCase.mock_plan` + `MockLlm` rejue le plan avant le tool_call |
| `evals/cases.yaml` | 2 nouveaux cas (plan suivi / non suivi) |
| `backend/tests/test_reasoning_plan.py` | tests TDD |

## Comment vérifier

```bash
cd backend
uv run pytest tests/test_reasoning_plan.py -q   # nouveaux tests
uv run pytest -q                                 # non-régression globale
uv run ruff check . && uv run ty check
uv run python -m investia.evals                  # métrique plan_suivi visible en mock
```

## Hors périmètre

12b (réflexion/auto-critique avant la réponse finale), 12c (self-consistency, vote majoritaire), cache sémantique, routeur appris, outils avancés. Aucun changement de modèle ni de prompt système métier.
