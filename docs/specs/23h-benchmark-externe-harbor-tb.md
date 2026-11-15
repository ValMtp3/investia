# Spec 23h — Dataset pinning (runner 22a) + benchmark externe type Harbor/TB 4.1 pinné

*Écrite le : 15/11/2026 | Étape veille D94 (item 7 « Evals externes ») | Statut : brouillon*

## Objectif

Rendre nos evals **reproductibles et pinnées** comme un benchmark externe (pattern
Harbor + Terminal-Bench 4.1 : datasets pinnés par version, verifiers anti-reward-hacking,
arXiv 2611.08417 « benchmarks as software ») :

1. **Dataset pinning** dans le runner 22a : chaque run d'evals enregistre le **sha256 du
   fichier de cas** utilisé ; `build_dataset` écrit le hash + un **changelog** ; une
   commande `verify` vérifie l'intégrité.
2. Un projet **`benchmarks/`** autonome (comme `comparisons/`, zéro dépendance dans le
   backend) qui produit un `results.json` au format métriques type benchmark
   (pass@1, moyennes par métrique, coût, durée, dataset_sha256, commit) + la config
   Harbor pinnée et la procédure pour lancer notre agent conteneurisé sous Harbor avec
   verifiers (run réel = procédure documentée, exécutée sur le VPS comme le batch live 22a).

## Pourquoi

Aujourd'hui `evals/generated/cases-live.yaml` est régénérable et non signé : deux runs
peuvent porter sur des cas différents sans que personne le remarque. La veille recommande
explicitement le dataset pinning + changelog (pattern Langfuse `dataset_version`) dans
notre runner 22a, et Harbor/TB 4.1 comme référence de benchmark externe pinné. Notre
runner mock/live 22a **reste la source de vérité produit** — Harbor sert de harness
externe reproductible, pas de remplacement.

## Contraintes

- Zéro régression : `start_eval_run(model, mode)` reste appelable sans hash (param
  optionnel, défaut None) ; `run_evals` inchangé si pas de `cases_path`.
- Zéro dépendance ajoutée dans `backend/` ; `benchmarks/` est un projet uv autonome
  (path dep sur `../backend`, comme `comparisons/`).
- Le run Harbor réel (Docker + dataset TB/22a pinné) = **procédure documentée**, exécuté
  sur le VPS par le propriétaire — jamais en CI, pas en local ici.
- TB 4.1 est un benchmark d'agents *coding* : notre agent financier n'y fera pas de
  gros scores — la valeur est le pipeline reproductible (pinning + verifiers), documentée
  comme telle dans le rapport.

## Contrat détaillé

### 1. Dataset pinning — backend

- Migration **0015** : `eval_runs.dataset_sha256 TEXT NULL` (rétrocompatible).
- `EvalStore.start_eval_run(model, mode, dataset_sha256: str | None = None)`.
- `run_evals(..., cases_path: Path | None = None)` : si fourni, sha256 du fichier YAML
  passé à `start_eval_run`. CLI `__main__.py` : `--cases` déjà existe → passé à
  `run_evals` ; nouveau sous-commandes `verify --cases PATH [--sha256 H]` → exit 0 si
  hash ok, 1 sinon (message clair).
- `build_dataset.py` : en plus du JSONL+sha256 (14b), écrit `<out>.yaml.sha256` et
  append dans `evals/generated/DATASET_CHANGELOG.md` :
  `| 2026-11-15T12:00:00Z | <sha256 yaml> | <count> cas | source <sha256 jsonl> | limit N |`.

### 2. `benchmarks/` — projet autonome

```
benchmarks/
├── pyproject.toml            # uv autonome, dep investia via path ../backend
├── README.md                 # procédure Harbor pinnée (versions/digests exacts)
├── run_benchmark.py          # lance le runner mock sur le dataset pinné -> results.json
├── harbor/
│   ├── harbor.yaml           # config Harbor pinnée (version harbor + dataset sha256)
│   └── README.md             # run réel conteneurisé (procédure VPS, jamais en CI)
├── tests/test_results.py     # schéma results.json + vérification du pin
└── results.json              # généré (mock)
```

- `run_benchmark.py` : vérifie le sha256 du dataset (`evals/cases.yaml` pinné par défaut,
  `--cases` pour un cases-live), lance `run_evals` en mock, écrit `results.json` :
  `{agent, commit, dataset_sha256, n_cases, pass1, metrics: {métrique: moyenne}, cost_cents_total, duration_ms, generated_at}`.
- `harbor/harbor.yaml` : version Harbor pinnée + dataset pinné par sha256 + verifier
  (notre métrique `tool_used`/`format_ok` comme reward binaire, anti-reward-hacking :
  verifier externe au agent, rejouable).

### 3. Rapport

- `docs/benchmarks-2026-11-15.md` : résultats mock, procédure Harbor live, lecture
  TB 4.1 (pinning, verifiers), ce qui est hors périmètre (SWE-bench saturé, non adopté).

## Critères d'acceptation

- [ ] Backend : `uv run pytest -q -m "not integration"` vert (nouveaux tests TDD :
  sha256 enregistré dans eval_runs via run_evals(cases_path=...), `verify` exit 0/1,
  changelog append + `<out>.yaml.sha256`, rétrocompat start_eval_run sans hash).
- [ ] `ruff`/`format`/`ty` propres ; dashboard inchangé.
- [ ] `cd benchmarks && uv run pytest -q` vert (schéma results.json, pin vérifié) ;
  `uv run python run_benchmark.py` produit `results.json` avec dataset_sha256.
- [ ] `docs/benchmarks-2026-11-15.md` écrit ; `alembic upgrade head` applique 0015.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/alembic/versions/0015_eval_runs_dataset_sha256.py` | création |
| `backend/src/investia/evals/store.py` | `start_eval_run(..., dataset_sha256=None)` + lecture |
| `backend/src/investia/evals/runner.py` | `run_evals(..., cases_path=None)` |
| `backend/src/investia/evals/__main__.py` | `--cases` transmis + sous-commande `verify` |
| `backend/src/investia/evals/build_dataset.py` | `.sha256` YAML + changelog |
| `backend/tests/...` | tests TDD pinning/verify/changelog |
| `benchmarks/` (nouveau) | pyproject, run_benchmark.py, harbor/, tests, results.json |
| `docs/benchmarks-2026-11-15.md`, STATUS, 09-decisions (D102) | rapport + docs |

## Comment vérifier

```bash
cd backend && uv run pytest -q -m "not integration" && uv run ruff check . && uv run ty check
cd benchmarks && uv sync && uv run pytest -q && uv run python run_benchmark.py
```

## Hors périmètre

- Run Harbor réel en Docker/TB 4.1 ici (procédure VPS documentée uniquement).
- garak en CI (item veille séparé), SWE-bench (saturé/contaminé — non adopté, documenté).
- LLM-as-judge externe (deepeval existe déjà en mock, 14a).
