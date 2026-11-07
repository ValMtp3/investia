# Spec — 3.1 : Evals de l'agent + scores en base

*Écrite le : 2026-10-31 | Étape roadmap : 3.1 | Statut : validée*

## Objectif

Un jeu d'evals qui note la qualité de l'agent, lançable en une commande, avec les scores enregistrés en base. Une régression se voit en chiffres. C'est le critère de l'étape 3 (partie evals).

## Pourquoi

Doc 03 §6 : sans evals, on améliore à l'aveugle. D38 : DeepEval (pytest-style) + Promptfoo (red teaming). Les scores en base permettent de comparer les versions (utile pour l'étape 6 : comparaison frameworks).

## Contraintes

- **Eval runner maison** (`backend/src/investia/evals/`) : charge un jeu de cas (YAML dans `evals/cases.yaml`), exécute `run_agent` dessus (LLM mocké par défaut pour la CI, live optionnel), calcule des métriques en code, enregistre en base.
- Métriques en code (pas que LLM) : `tool_used` (l'agent a appelé le bon outil), `numbers_sourced` (garde-fous OK), `format_ok`, `cost_cents`, `turns`.
- DeepEval pour les métriques LLM (hallucination, pertinence) — en dépendance dev/group séparé, lancées via pytest dans `evals/`.
- **Tables** `eval_runs` + `eval_results` (migration 0003) : eval_run (id, started_at, model, commit), eval_results (run_id, case_id, metric, score, detail JSONB).
- Commande unique : `uv run python -m investia.evals` (lance le jeu, affiche le récap, écrit en base).
- Promptfoo en red teaming séparé (`evals/redteam.yaml`), pas dans le run principal.
- Tests : runner testé avec LLM/market mockés (zéro réseau, déterministe) ; intégration base marquée. TDD.
- Biais de regard vers l'avenir (doc 03) : les cas de test figent les données attendues, jamais d'appel réseau live dans les evals déterministes.

## Critères d'acceptation

- [ ] `cd backend && uv run pytest -q` passe (tous les tests, y compris `test_evals_*`).
- [ ] `alembic upgrade head` crée `eval_runs` + `eval_results` (test integration).
- [ ] `uv run python -m investia.evals --mock` tourne en local, affiche un récap, et écrit 1 ligne dans `eval_runs` + N dans `eval_results`.
- [ ] Un cas « prix de BTC » mocké → métrique `tool_used=get_quote` = 1 ; un cas avec chiffre inventé → `numbers_sourced` = 0.
- [ ] Une régression se voit : deux runs enregistrés, le plus récent a un score plus bas → visible en chiffres (test sur 2 runs).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/alembic/versions/0003_evals.py` | création : migration eval_runs/eval_results |
| `backend/src/investia/evals/__init__.py`, `runner.py`, `metrics.py` | création : runner + métriques en code |
| `backend/src/investia/evals/__main__.py` | création : commande `uv run python -m investia.evals` |
| `evals/cases.yaml` | création : jeu de cas (question, outil attendu, réponse attendue mockée) |
| `evals/redteam.yaml` | création : config Promptfoo (red teaming, hors run principal) |
| `backend/tests/test_evals*.py` | création |
| `backend/pyproject.toml` | `deepeval` en groupe dev |

## Comment vérifier

```bash
cd backend && uv run pytest -q
cd backend && uv run python -m investia.evals --mock
```

## Hors périmètre

Mémoire longue pgvector (3.2), batch API (-50 %), évals LLM-as-judge calibrées, dashboard des scores (étape 4).
