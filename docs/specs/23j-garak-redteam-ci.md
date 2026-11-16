# Spec 23j — garak (NVIDIA) en redteam : smoke CI + vrai scan en procédure VPS

*Écrite le : 15/11/2026 | Étape veille D94 (item 7 « Evals externes », sous-item garak) | Statut : validée le 15/11/2026 (option « Oui, tel quel »)*

## Objectif

Brancher **garak v0.17.1** (NVIDIA, Apache-2.0, scanner de vulnérabilités LLM) sur
notre harness, en deux niveaux :

1. **Smoke CI** (gratuit, déterministe, sans clés) : garak tourne en mode
   hors-ligne (`-m test.Blank`) avec une config pinnée et produit un rapport —
   ça prouve que le pipeline redteam fonctionne, pas que le modèle est sûr.
2. **Vrai scan** (procédure VPS, clés réelles, jamais en CI) : garak cible notre
   harness via un **générateur custom** branché sur `run_agent`, probes
   d'injection/jailbreak/fuite, rapport commité en doc.

## Pourquoi

La veille D94 : garak en job CI sécurité isolée. Nous avons des défenses maison
à éprouver (wrapper contenu externe 13b, canary 23b, redaction secrets,
garde-fous en code) : garak apporte les sondes d'attaque standardisées
(promptinject, latentinjection — le cas « contenu d'outil piégé », dan,
encoding, packagehallucination — pertinent pour run_python).

## Contrat détaillé

### 1. `redteam/` — projet uv autonome (comme `benchmarks/`)

```
redteam/
├── pyproject.toml            # garak==0.17.1 pinné + investia (path ../backend)
├── garak.conf.yaml           # config pinnée : probes subset, seed fixe, report_dir
├── investia_generator.py     # plugin garak Generator -> run_agent (LLM réel en VPS)
├── run_redteam.py            # lance garak, parse le rapport, exit 0/1
├── tests/test_redteam.py     # smoke + parse + générateur custom (mock)
└── README.md                 # procédure VPS du vrai scan (jamais en CI)
```

- `garak.conf.yaml` : probes = `promptinject, latentinjection, dan, encoding,
  packagehallucination` ; `seed` fixe (reproductibilité) ; rapport JSONL + résumé.
- `investia_generator.py` : hérite `garak.generators.base.Generator`, appelle
  `run_agent(prompt, llm=<client LiteLLM>, tools=build_tools(MockMarket()))` —
  en VPS le LLM est réel (clés dans .env), jamais commité.
- `run_redteam.py --smoke` : lance `python -m garak -m test.Blank -p test.Blank`
  (hors-ligne), vérifie le rapport ; `run_redteam.py --live` : config pinnée +
  générateur investia (VPS seulement).

### 2. CI — workflow dédié `.github/workflows/redteam.yml`

- **Pas sur PR** : `schedule` (hebdo) + `workflow_dispatch` uniquement.
- Job unique : `cd redteam && uv sync && uv run python run_redteam.py --smoke`,
  rapport en artifact. ⚠️ garak tire des deps ML (torch/transformers) : si le
  job CI dépasse ~15 min ou échoue pour taille, on documente et on garde le
  smoke en local/VPS uniquement (décision notée).

### 3. Rapport

`docs/redteam-2026-11-15.md` : ce qui est couvert (probes), ce qui est hors
périmètre (vrai scan LLM = VPS, SaaS de redteam type Braintrust non retenus —
veille D94), lecture des résultats du smoke.

## Critères d'acceptation

- [ ] `cd redteam && uv sync && uv run pytest -q` vert (smoke garak hors-ligne,
  parse du rapport, générateur custom avec MockLlm).
- [ ] `uv run python run_redteam.py --smoke` exit 0 + rapport garak produit.
- [ ] `redteam.yml` : job déclenché en manuel/schedule uniquement (pas sur PR).
- [ ] Backend/dashboard inchangés ; `uv run pytest -q -m "not integration"` toujours vert.
- [ ] Zéro dépendance ajoutée à `backend/` (garak vit dans `redteam/`).

## Hors périmètre

- Vrai scan LLM en CI (clés réelles) — procédure VPS documentée uniquement.
- promptfoo (déjà en `evals/redteam.yaml`, providers à brancher = chantier séparé).
- SaaS de redteam (Braintrust/LangSmith/Opik) — non retenus (veille D94, D38).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `redteam/` (nouveau) | pyproject, garak.conf.yaml, investia_generator.py, run_redteam.py, tests, README |
| `.github/workflows/redteam.yml` | création (schedule + dispatch, smoke) |
| `docs/redteam-2026-11-15.md`, STATUS, 09-decisions (D104) | rapport + suivi |

## Comment vérifier

```bash
cd redteam && uv sync && uv run pytest -q && uv run python run_redteam.py --smoke
cd backend && uv run pytest -q -m "not integration"
```
