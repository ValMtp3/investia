# Spec — 14a : DeepEval en complément des métriques en code (métriques déterministes)

*Écrite le : 14/11/2026 | Étape roadmap : 14 (evals/observabilité) | Statut : terminée le 14/11/2026*

## Objectif

Ajouter **DeepEval v4** (déjà en dev-deps) comme métrique externe de tool-calling, en complément — jamais en remplacement — de nos métriques en code (`evals/metrics.py`). Les métriques LLM-as-judge de DeepEval restent réservées au mode live (jamais de réseau en test).

## Pourquoi

Veille 14/11/2026 (`docs/veille-oss-2026-11-14.md` brique 8) : DeepEval v4.2.4 (Apache-2.0, pytest-style, 100 % local) apporte `ToolCorrectnessMetric` (comparaison structurée outils attendus/appelés, sans LLM). Nos métriques en code restent la source de vérité (un juge LLM seul n'est pas fiable, arXiv 2606.19544).

## Contraintes

- Zéro modification de `run_evals` / `compute_metrics` (zéro régression) : nouveau module `evals/deepeval_bridge.py` qui convertit `(EvalCase, AgentResult)` en `deepeval.LLMTestCase` et calcule `ToolCorrectnessMetric`.
- Tests 100 % déterministes, zéro réseau, zéro appel LLM (ToolCorrectness n'en a pas besoin).
- `deepeval` reste en dev-deps (déjà présent, aucune dep ajoutée).

## Critères d'acceptation

- [ ] `uv run pytest tests/test_evals_deepeval.py -q` passe : sur les cas mock existants avec `expected_tool`, `deepeval_tool_correctness(case, result) == 1.0` quand l'outil attendu a été appelé, `0.0` sinon ; le bridge produit un `LLMTestCase` avec `tools_called` renseigné.
- [ ] Le test échoue si on inverse expected_tool (garde-fou CI effectif).
- [ ] `uv run pytest -q -m "not integration"` passe ; ruff/ty propres sur les fichiers touchés.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/evals/deepeval_bridge.py` | nouveau : `to_llm_test_case`, `deepeval_tool_correctness` |
| `backend/tests/test_evals_deepeval.py` | tests TDD (run_evals sur sous-ensemble de cases.yaml) |

## Comment vérifier

```bash
cd backend && uv run pytest tests/test_evals_deepeval.py -q
cd backend && uv run pytest -q -m "not integration"
```

## Hors périmètre

Métriques LLM-as-judge (G-Eval) en CI — mode live uniquement, avec budget ; intégration Langfuse/Phoenix (veille, chantier ultérieur) ; modification du runner d'evals.
