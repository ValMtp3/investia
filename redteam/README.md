# redteam/ — garak (NVIDIA) pinné contre le harness Investia (étape 23j, D104)

Projet uv **autonome** (path dep `../backend`) : garak vit ici, **jamais dans le
backend**. garak v0.17.1 (Apache-2.0) scanne notre harness avec des sondes
standardisées (injection, jailbreak, fuite) ; nos défenses maison (wrapper
contenu externe 13b, canary 23b, redaction secrets, garde-fous en code) sont
éprouvées par le scan.

## Deux niveaux

| Niveau | Où | Quoi |
|---|---|---|
| **Smoke CI** | `.github/workflows/redteam.yml` (schedule hebdo + manuel, pas sur PR) | `run_redteam.py --smoke` : garak hors-ligne (`test.Blank`), zéro clé, produit un rapport → prouve que le pipeline marche |
| **Vrai scan** | **VPS uniquement** (clés réelles, comme le batch live 22a) | `run_redteam.py --live` : générateur `investia_generator.py` = notre `run_agent` complet, probes pinnées de `garak.conf.yaml` |

## Lancer

```bash
cd redteam
uv sync
uv run pytest -q                        # tests (smoke garak inclus, marqué slow)
uv run python run_redteam.py --smoke    # hors-ligne, CI
# VPS seulement, avec les vraies clés dans ../.env :
uv run python run_redteam.py --live     # rapport dans garak_runs/
```

## Procédure VPS (vrai scan)

1. `cd redteam && uv sync`
2. Charger les vraies clés (`set -a; source ../.env; set +a`) — jamais en CI.
3. `uv run python run_redteam.py --live` (générateur `investia` → `run_agent`
   avec le vrai LLM via LiteLLM, température 0).
4. Lire `garak_runs/*.report.jsonl` + `*.hitlog.jsonl` : **les hits sont revus
   par un humain**, garak ne fail pas dessus. Consigner le résumé dans
   `docs/redteam-<date>.md` (probes, n hits, décisions).
5. garak ne remplace pas nos evals mock (`evals/cases.yaml`) : garak = attaques
   standardisées, nos evals = régression fonctionnelle.

## ⚠️ Poids

garak tire des dépendances ML (torch/transformers, venv ~1,8 Go). Si le job CI
dépasse ~15 min, le smoke passe en local/VPS uniquement (décision notée en D104).
