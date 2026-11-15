# benchmarks/ — Benchmark externe pinné type Harbor/TB 4.1 (étape 23h, D102)

Projet uv **autonome** (comme `comparisons/`) : dépend du backend par chemin
(`../backend`), le backend ne dépend jamais de lui. Zéro dépendance ajoutée au backend.

## Pourquoi

Nos evals (`evals/cases.yaml`) doivent être **reproductibles** : un run doit pouvoir
être rejoué sur exactement le même dataset, prouvé par un sha256 (pattern Harbor +
Terminal-Bench 4.1, arXiv 2611.08417 « benchmarks as software »). Le runner mock 22a
reste la source de vérité produit ; Harbor sert de harness externe reproductible.

## Organisation

```
benchmarks/
├── pyproject.toml          # projet uv autonome (path dep ../backend)
├── run_benchmark.py        # runner mock sur dataset pinné -> results.json
├── harbor/
│   ├── harbor.yaml         # config Harbor pinnée (sha256 dataset + verifier externe)
│   └── README.md           # procédure du run réel conteneurisé (VPS, jamais en CI)
├── tests/test_results.py   # schéma results.json + vérification du pin
└── results.json            # généré (mock)
```

## Lancer

```bash
cd benchmarks
uv sync
uv run pytest -q                      # schéma + pin
uv run python run_benchmark.py        # produit results.json (mock, gratuit, déterministe)
```

`results.json` : `{agent, commit, dataset_sha256, n_cases, pass1, metrics, cost_cents_total, duration_ms, generated_at}`.
pass@1 = part des cas où toutes les métriques gate valent 1.0.

## Run Harbor réel

Voir `harbor/README.md` : procédure **VPS propriétaire** (clés LLM réelles, budget
réel), jamais en CI. Le verifier tourne dans un conteneur séparé de l'agent
(anti-reward-hacking) et ne lit que la trace produite.
