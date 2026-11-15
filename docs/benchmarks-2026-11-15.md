# Rapport benchmark — 15/11/2026 (chantier 23h, D102)

Dataset pinning (sha256) dans le runner d'evals + projet autonome `benchmarks/`
type Harbor / Terminal-Bench 4.1 (arXiv 2611.08417 « benchmarks as software »).
Spec : `docs/specs/23h-benchmark-externe-harbor-tb.md`.

## 1. Dataset pinning (backend)

- Migration **0015** : `eval_runs.dataset_sha256 TEXT NULL` (rétrocompatible).
- `EvalStore.start_eval_run(model, mode, dataset_sha256=None)` ; `run_evals(..., cases_path=None)`
  calcule le sha256 du YAML et l'enregistre dans le run d'evals.
- CLI : `python -m investia.evals verify --cases PATH [--sha256 H]` → exit 0/1
  (lit `<cases>.sha256` à défaut).
- `build_dataset` écrit `<out>.yaml.sha256` + append une ligne dans
  `DATASET_CHANGELOG.md` (date UTC | sha256 YAML | nb cas | sha256 source | limit).

## 2. Résultats mock (`benchmarks/results.json`, généré le 2026-11-15)

- Dataset pinné : `evals/cases.yaml` sha256 `4c7bc516698cb6691195493f93b024ae267a7536c79266652906217d334ea107`, **20 cas**.
- **pass@1 = 0.55** (part des cas où toutes les métriques gate = 1.0 :
  tool_used, numbers_sourced, format_ok, language_ok, disclaimer_ok, plan_suivi,
  safety_llm_ok, safety_logprobs_ok).
- Moyennes : tool_used 0.85, numbers_sourced 0.85, plan_suivi 0.95, format_ok /
  language_ok / disclaimer_ok / routeur_choix / routeur_agent 1.0, consensus 0.983,
  safety 0.95, turns 2.5, cost_cents 0.029 (mock), cost_cents_total 0.0, durée 644 ms.
- Lecture : les cas qui ratent le pass@1 sont des cas négatifs volontaires
  (garde-fous qui bloquent, routeur qui choisit contre les règles, etc.) — le
  score reflète le jeu de cas, pas une régression. L'important est la
  **reproductibilité** : même dataset_sha256 + même commit → mêmes chiffres.

## 3. Procédure Harbor live (VPS, jamais en CI)

Voir `benchmarks/harbor/README.md` : pin du commit Harbor + sha256 du dataset
vérifié (`investia.evals verify`), image agent buildée depuis `deploy/`, run
`harbor run --config benchmarks/harbor/harbor.yaml`, verifier dans un conteneur
séparé écrivant `/logs/verifier/reward.txt` (reward binaire = toutes les métriques
gate à 1.0, rejouable hors de l'agent → anti-reward-hacking).

## 4. Lecture TB 4.1 / Harbor — ce qu'on retient

- **Pinning par sha256 + changelog** : adopté (partie 1 ci-dessus). C'est le cœur
  de « benchmark = logiciel » : sans hash du dataset, deux runs ne sont pas
  comparables.
- **Verifier externe à l'agent** : adopté comme principe (Harbor le fait par
  conteneur séparé ; nous avons déjà nos garde-fous en code côté harness +
  métriques rejouables via `run_evals`).
- **TB 4.1 est un benchmark d'agents *coding*** : notre agent financier n'y fera
  pas de gros scores — la valeur retenue est le **pipeline reproductible**
  (pinning + verifiers + results.json normalisé), pas le classement.

## 5. Hors périmètre (documenté, non adopté)

- Run Harbor réel en Docker ici : procédure VPS uniquement (coût LLM réel).
- garak en CI : item veille séparé (trop lourd pour la CI gratuite).
- SWE-bench : saturé/contaminé pour un agent financier — non retenu.
- LLM-as-judge externe : deepeval existe déjà en mock (14a).

## Validation

- Backend : 745 passed / 1 skip (non-integration), ruff/format/ty propres
  (5 tests TDD pinning dans `tests/test_dataset_pinning.py`).
- `benchmarks/` : `uv run pytest -q` 6 passed, ruff propre,
  `uv run python run_benchmark.py` → `results.json` avec dataset_sha256.
- Dashboard inchangé.
