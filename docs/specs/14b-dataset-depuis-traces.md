# Spec — 14b : dataset d'eval vivant exporté depuis les traces en base (read-only)

*Écrite le : 14/11/2026 | Étape roadmap : 14 (evals/observabilité) | Statut : terminée le 14/11/2026*

## Objectif

Exporter les vrais runs tracés en base (`runs`/`run_steps`, en particulier les échecs) en un **dataset versionné** (JSONL + hash SHA-256), en lecture seule, pour la revue humaine et les futures comparaisons A/B de prompts en mode live. Zéro dépendance nouvelle.

## Pourquoi

Veille 14/11/2026 (brique 8) : les plateformes d'evals (Langfuse/Phoenix) permettent d'ajouter une trace de prod à un dataset — on le fait maison, read-only, sans ClickHouse. Nos `runs` contiennent déjà question/réponse/statut/étapes (étape 2.2 + 13a redaction).

## Contraintes

- Read-only strict : uniquement `list_runs` + `get_run` du store ; aucune écriture en base.
- Format : `evals/generated/traces_dataset.jsonl` (une ligne JSON par run : id, question, answer, model, status, turns, total_cost_cents, created_at, kinds des steps) + `traces_dataset.jsonl.sha256`. Dossier `generated/` ignoré de git (le dataset est régénérable).
- CLI : `uv run python -m investia.evals.export_traces [--out PATH] [--status blocked,max_turns] [--limit 200]`.
- Déterministe : tri par created_at desc puis id ; hash = SHA-256 du contenu JSONL.
- Zéro régression : aucun changement sur le stockage des traces.

## Critères d'acceptation

- [ ] `uv run pytest tests/test_export_traces.py -q` passe : avec un FakeTraceStore contenant un run « blocked » et un run « ok », l'export ne contient que les statuts demandés, le JSONL est parsable, le hash du fichier `.sha256` correspond au contenu, et un second export identique donne le même hash.
- [ ] `uv run python -m investia.evals.export_traces --help` fonctionne sans base (pas d'import DB au niveau module).
- [ ] `uv run pytest -q -m "not integration"` passe ; ruff/ty propres sur les fichiers touchés.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/evals/export_traces.py` | nouveau : `export_dataset(store, out_path, statuses, limit)` + `main()` CLI |
| `backend/tests/test_export_traces.py` | tests TDD avec FakeTraceStore |
| `backend/.gitignore` ou racine | ignorer `evals/generated/` |

## Comment vérifier

```bash
cd backend && uv run pytest tests/test_export_traces.py -q
cd backend && uv run python -m investia.evals.export_traces --help
cd backend && uv run pytest -q -m "not integration"
```

## Hors périmètre

Rejeu automatique des traces en eval (les vraies réponses ne sont pas rejouables en mock — ce dataset sert à la revue et aux futurs A/B live) ; ingestion dans Langfuse/Phoenix ; rétention/suppression de données.
