# Run Harbor réel — procédure VPS (jamais en CI, jamais en local ici)

Le run conteneurisé de notre agent sous Harbor est une **action propriétaire sur le
VPS** (comme le batch live 22a) : il manipule les vraies clés LLM et consomme du
budget réel. Cette procédure est documentée, pas exécutée ici.

## Pins à vérifier avant tout run

1. **Harbor** : cloner `laude-institute/harbor` et pinner le commit utilisé
   (`git checkout <commit>`), consigné dans le rapport `docs/benchmarks-*.md`.
2. **Dataset** : vérifier le sha256 pinné dans `harbor.yaml` :
   ```bash
   sha256sum evals/cases.yaml
   # doit être égal au champ dataset.source.sha256 de benchmarks/harbor/harbor.yaml
   cd backend && uv run python -m investia.evals verify --cases ../../evals/cases.yaml
   ```
3. **Agent** : builder l'image `investia-agent:latest` depuis `deploy/` (même image
   que le VPS).

## Procédure (VPS, propriétaire)

```bash
# 1. Préparer le dataset de tâches Harbor à partir de nos cas (génération VPS)
#    chaque cas -> tâche (task.toml + instruction.md + tests/verify_case.py)
# 2. Lancer Harbor avec la config pinnée :
harbor run --config benchmarks/harbor/harbor.yaml --agent investia-agent:latest
# 3. Récupérer les rewards : /logs/verifier/reward.txt par tâche -> results.json
# 4. Consigner : commit harbor, dataset_sha256, commit investia, coût total,
#    pass@1 agrégé -> append dans docs/benchmarks-<date>.md
```

## Règles absolues

- Jamais de run Harbor en CI (coût LLM réel + secrets).
- Le verifier (`tests/verify_case.py`) tourne dans son propre conteneur : il ne voit
  que la trace produite par l'agent, jamais ses variables internes (anti-reward-hacking).
- Tout dataset régénéré (`build_dataset`) doit être re-pinné (nouveau sha256 dans
  `harbor.yaml` + ligne dans `DATASET_CHANGELOG.md`) avant le run.
