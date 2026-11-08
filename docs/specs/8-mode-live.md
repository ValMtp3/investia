# Spec — 8 : Mode live (vraies clés API + live check + evals réelles)

*Écrite le : 2026-11-07 | Étape roadmap : 8 | Statut : code livré le 2026-11-07 (branche `feat/mode-live`) — clés à renseigner sur le VPS pour activer le live*

## Objectif

Passer le projet en **mode live** : le propriétaire renseigne les vraies clés API dans le `.env` du VPS (LLM + marché), un endpoint `GET /api/live/llm` permet de vérifier qu'un appel LLM réel fonctionne (ok/ko + coût + durée), et les evals réelles de la comparaison 6.3 peuvent tourner avec un budget bloqué en code (~2 €).

## Pourquoi

Toutes les clés étaient fictives jusqu'ici (STATUS étape 1). Sans mode live, l'agent ne répond jamais vraiment. D62 prévoit les runs réels de la 6.3 avec ~2 € max. Le live check évite de découvrir un souci de clé en plein chat.

## Contraintes

- **Aucune clé dans le repo** (D42) : uniquement dans `.env` sur le VPS, jamais affiché dans les logs/commandes. Le guide donne les commandes sans `echo` des valeurs.
- `GET /api/live/llm` **exige `X-Admin-Token`** (D51, comparaison en temps constant) : personne ne déclenche d'appels payants sans le jeton. Sans jeton → 401.
- L'appel live utilise le modèle `small` (gpt-6-luna, le moins cher) avec un prompt minimal fixe. Réponse : `{ok, model, cost_cents, duration_ms, error?}`. Jamais de contenu LLM dans la réponse (juste ok/ko).
- `comparisons/run_evals.py --live --budget-eur 2` : lance les 4 approches sur les cas d'evals avec le **vrai LLM** (client investia), **arrêt automatique au dépassement du budget** (cumul des coûts en centimes), résultats dans `results-live.json`.
- Zéro régression : sans clés renseignées, tout continue de fonctionner en mock (les endpoints live renvoient ok:false avec une erreur claire « clé manquante »).
- Tests d'abord ; `uv run pytest -q -m "not integration"` + ruff + ty verts ; dashboard inchangé (cet étape est backend + comparisons).

## Critères d'acceptation

- [x] `GET /api/live/llm` sans `X-Admin-Token` → 401 ; avec mauvais token → 401 ; avec bon token + LLM fake → 200 `{ok: true, model, cost_cents, duration_ms}` ; avec LLM fake en erreur → 200 `{ok: false, error}` (pas de 500).
- [x] Sans clé LLM configurée (settings sans clé), le live check renvoie `ok: false` avec « clé manquante » (pas d'exception).
- [x] `comparisons/run_evals.py --live --budget-eur 2` : stoppe au budget, écrit `results-live.json` ; test avec fake LLM qui dépasse → arrêt + budget atteint noté.
- [x] `docs/mode-live.md` : quelles clés créer (fournisseur + lien + gratuit/payant), où les mettre sur le VPS (commandes `nano .env` sans affichage), comment lancer le live check et les evals réelles.
- [x] `uv run pytest -q -m "not integration"`, ruff, ty, `cd comparisons && uv run pytest -q` verts.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/main.py` | route `GET /api/live/llm` (admin token) |
| `backend/tests/test_live_llm.py` | création : 401/200 ok/200 ko/clé manquante |
| `comparisons/run_evals.py` | mode `--live --budget-eur` |
| `comparisons/tests/test_live_evals.py` | budget bloqué en code |
| `docs/mode-live.md` | guide des clés + procédure VPS |
| `docs/STATUS.md`, `docs/08-roadmap.md`, `docs/09-decisions.md` | avancement 8, roadmap, décision (D65) |

## Comment vérifier

```bash
cd backend && uv run pytest -q -m "not integration" && uv run ruff check . && uv run ty check
cd comparisons && uv run pytest -q && uv run python run_evals.py --live --budget-eur 2   # avec vraies clés
# Sur le VPS (clés en place) :
curl -s -H "X-Admin-Token: $APP_SECRET_KEY" https://investia.valentin-fiess.fr/api/live/llm
```

## Hors périmètre

- Pas de changement de modèle par défaut (D26) ; pas de nouveau fournisseur.
- Pas de stockage des clés côté client ; pas de logs de contenu LLM.
- Le déploiement VPS reste manuel (`deploy/update.sh`) ; les clés restent sur le VPS uniquement.
