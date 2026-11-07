# Spec — 6.3 : Comparaison chiffrée + P7 (Go/Rust)

*Écrite le : 2026-11-07 | Étape roadmap : 6.3 | Statut : brouillon (à valider)*

## Objectif

Produire un **tableau comparatif documenté** des 4 approches (harness maison, LangGraph, Pydantic AI, OpenAI Agents SDK) sur les mêmes evals, avec **qualité (scores), coût, latence** — en mock d'abord (déterministe, gratuit), puis **~2 € max de runs LLM réels** pour valider le classement (D62). Plus **P7** : un composant (collecteur de prix ou moteur de backtest) réécrit en **Go ou Rust**, mesuré contre la version Python.

## Pourquoi

Roadmap étape 6 : « Les evals montrent un gain (ou non, documenté) pour chaque approche. » D17/D41/D62. Sans cette comparaison, on ne sait pas ce que le harness maison vaut réellement.

## Contraintes

- Mock d'abord : `comparisons/results.json` (6.2) + evals du backend rejoués sur les 4 approches, zéro appel réseau.
- Runs réels : budget **~2 € max** au total, tracés via le coût enregistré par run (LiteLLM cost tracking) ; arrêt automatique au dépassement (budget bloqué en code, comme aujourd'hui).
- Métriques : scores d'evals (métriques existantes : tool_used, numbers_sourced, format, langage, disclaimer, tours, coût), latence moyenne, coût moyen par run.
- P7 : un composant choisi (ex. `portfolio/calc.py` ou un collecteur de prix) réécrit en Go (préféré à Rust pour la simplicité de build cross-platform ici — à confirmer), buildé en binaire local, même jeu de tests ; métrique : temps d'exécution sur un dataset fixe + taille du binaire.
- Le résultat est un document **`docs/comparaison-etape-6.md`** : tableau + graphique simple (texte ou image) + conclusion honnête (gain ou non pour chaque approche).
- Zéro régression : rien ne change dans le backend de prod.

## Critères d'acceptation

- [ ] `comparisons/results.json` régénéré avec les 4 approches, métriques complètes.
- [ ] Runs réels : script `comparisons/run_evals.py --live --budget-eur 2` qui s'arrête au budget ; coûts enregistrés et résumés.
- [ ] P7 : `comparisons/go/` (ou `rust/`) avec le composant réécrit + benchmark (`comparisons/bench.py` lance les deux versions sur le même dataset, mesure le temps) → résultats dans le doc.
- [ ] `docs/comparaison-etape-6.md` écrit : tableau comparatif + conclusion documentée (gain ou non, chiffré).
- [ ] `cd backend && uv run pytest -q -m "not integration"` toujours vert.
- [ ] STATUS/roadmap mis à jour ; étape 6 cochée.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `comparisons/run_evals.py` | mode `--live --budget-eur` |
| `comparisons/results.json` | résultats mock + réels |
| `comparisons/go/` (ou `rust/`) | composant P7 + benchmark |
| `docs/comparaison-etape-6.md` | création : le rapport comparatif |
| `docs/STATUS.md`, `docs/08-roadmap.md`, `docs/09-decisions.md` | avancement 6.3, D62 (déjà noté) |

## Comment vérifier

```bash
cd comparisons && uv run python run_evals.py --mock && uv run python run_evals.py --live --budget-eur 2
cat results.json
cd backend && uv run pytest -q -m "not integration"
# lire docs/comparaison-etape-6.md
```

## Hors périmètre

- Pas de mise en prod d'une version framework.
- Pas de changement du harness maison basé sur les résultats (on documente, on ne pivote pas sans discussion).
- Budget LLM : jamais au-delà de ~2 € pour cette étape (D62).
