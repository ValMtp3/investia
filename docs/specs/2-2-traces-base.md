# Spec — 2.2 : Traces des exécutions en PostgreSQL

*Écrite le : 2026-10-31 | Étape roadmap : 2.2 | Statut : validée*

## Objectif

Chaque exécution de l'agent (un *run*) est enregistrée en base : question, réponse, modèle, tours, coût, étapes (appels LLM, appels d'outils, décisions des garde-fous). Toute exécution devient inspectable et rejouable. C'est la moitié « traces » du critère de fin de l'étape 2.

## Pourquoi

Doc 03 §7 : comme la boîte noire d'un avion — en cas d'erreur, on rejoue. Doc 02 : tables `runs` / `run_steps`. D38 : export OTel GenAI vers PostgreSQL d'abord (les spans OTel viendront en 2.3, ici on pose le schéma et le store).

## Contraintes

- Migration Alembic `0002_runs.py` : table `runs` (id UUID PK, question, answer, model, turns, total_cost_cents, status `ok|blocked|max_turns`, created_at) et `run_steps` (id, run_id FK cascade, turn, kind `llm_call|tool_call|guardrail`, payload JSONB, created_at). Alembic reste la seule source du schéma.
- `tracing/store.py` : `TraceStore` async (SQLAlchemy) avec `start_run(question) -> run_id`, `log_step(run_id, turn, kind, payload)`, `finish_run(run_id, result)`, `get_run(run_id) -> (run, steps)`.
- Intégration boucle : `run_agent(..., trace_store=None)` — si présent, loggue chaque tour (modèle, tokens, coût, tool_calls), chaque outil (nom, args, résultat tronqué à 4 Ko), chaque décision garde-fou, et le statut final.
- **Aucun secret dans les traces** : jamais la master key, jamais les clés API. Test dédié.
- Payloads en JSONB ; tailles tronquées (réponse/outils à 4 Ko).
- Tests : unitaires avec un store fake + integration contre la vraie base (marquée). TDD.

## Critères d'acceptation

- [ ] `cd backend && uv run pytest -q` passe (tous les tests, y compris `test_tracing_*`).
- [ ] `alembic upgrade head` applique `runs` + `run_steps` (test integration sur base vide).
- [ ] Un run mocké (boucle fake) avec store réel → `runs` a 1 ligne (status ok), `run_steps` contient les kinds llm_call, tool_call, guardrail dans l'ordre.
- [ ] `get_run(run_id)` renvoie le run + ses steps (base du rejeu).
- [ ] Aucun payload ne contient la master key (test de fuite).
- [ ] Run bloqué par garde-fous → status `blocked` en base.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/alembic/versions/0002_runs.py` | création : migration runs + run_steps |
| `backend/src/investia/tracing/__init__.py`, `store.py` | création : TraceStore |
| `backend/src/investia/agent/loop.py` | modification : branche le trace_store optionnel |
| `backend/src/investia/cli.py` | modification : instancie le TraceStore |
| `backend/tests/test_tracing.py` | création : unitaire (fake) + integration (vraie base) |

## Comment vérifier

```bash
cd backend && uv run pytest -q
TEST_DATABASE_URL=... uv run pytest -q -m integration -k tracing
TEST_DATABASE_URL=... uv run alembic upgrade head   # applique le schéma
```

## Hors périmètre

Spans OTel GenAI (2.3), evals (étape 3), API de lecture des traces (étape 4), Langfuse.
