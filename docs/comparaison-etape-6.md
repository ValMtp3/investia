# Rapport comparatif — étape 6 (2026-11-07)

Même harness (boucle agent + outils + evals) construit 4 fois : à la main, avec **LangGraph**, **Pydantic AI**, **OpenAI Agents SDK**. Résultats mock (déterministes, gratuits) dans `comparisons/results.json` ; P7 (Go vs Python) dans `comparisons/bench_results.json`.

## 1. Qualité sur les evals mock (3 cas, `evals/cases.yaml`)

| Approche | Bon outil appelé | Garde-fous appliqués (format/langage/disclaimer/sourcé) | Durée moy. par run |
|---|---|---|---|
| **Maison** | 1.0 | **1.0** (garde-fous en code, D41) | 0,4 ms |
| LangGraph 1.2.20 | 1.0 | 0,0 (non câblés ici) | 3,7 ms |
| Pydantic AI 2.66.0 | 1.0 | 0,0 (non câblés ici) | 7,4 ms |
| OpenAI Agents SDK 0.24.0 | 1.0 | 0,0 (non câblés ici) | 4,9 ms |

**Lecture** : sur la tâche jouet (appeler le bon outil), les 4 se valent. La différence réelle est ailleurs : seul le harness maison applique les garde-fous en code (chiffres sourcés, format, langage interdit, disclaimer). Les frameworks ont leurs propres mécanismes de guardrails, mais il faut les configurer soi-même — rien n'est gratuit. En mock, le maison est aussi le plus rapide (mais la marge est du bruit de mesure à cette échelle).

## 2. Runs LLM réels (~2 € prévus, D62)

⚠️ **Non exécutés ici** : les clés LLM du `.env` local sont fictives (voir STATUS étape 1). À refaire avec les vraies clés (`OPENAI_API_KEY`, `MISTRAL_API_KEY`) via `comparisons/run_evals.py --live --budget-eur 2` (le flag existe, le mode live reste à brancher sur le vrai client LiteLLM dans la 6.3). Budget bloqué en code, arrêt au dépassement.

## 3. P7 — même composant en Go vs Python

Composant : `portfolio.calc.apply_order` (calcul d'ordre simulé, cœur du portefeuille). Réécriture fidèle en Go (`comparisons/go/portfolio/`), mêmes 6 vecteurs de test (verts des deux côtés). Benchmark : 1 000 000 itérations identiques.

| Implémentation | ns/op | total 1M |
|---|---|---|
| Python (dataclass + apply_order) | 559,6 ns | 560 ms |
| Go (struct + ApplyOrder) | 10,3 ns | 10 ms |

**Go est ~54x plus rapide** sur ce calcul pur. Leçon : le cœur du harness reste en Python (D41, lisibilité/apprentissage), mais un composant chaud (collecteur de prix haute fréquence, moteur de backtest) se réécrirait en Go sans changer le contrat — les tests vecteurs garantissent la même sémantique.

## 4. Conclusion honnête

- **Ce que le harness maison apporte** : garde-fous en code (vérifiés, testés), traces en base, validation humaine (5.1), coût suivi — tout est explicite et testé. Les frameworks demandent de tout recâbler soi-même pour arriver au même niveau.
- **Ce que les frameworks apportent** : de l'outillage (tracing, handoffs, reprise) prêt à l'emploi, au prix d'une dépendance et d'une courbe d'apprentissage. Sur une tâche jouet, aucun gain de qualité mesurable.
- **Ce qui a été décidé** : le cœur reste maison (D41 confirmé par les chiffres) ; Go pour un composant chaud si le besoin se présente (P7 prouvé).
