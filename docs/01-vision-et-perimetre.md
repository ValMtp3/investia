# 01 — Vision et périmètre

## Pourquoi ce projet

Tu veux comprendre en profondeur comment on construit un harness d'agent IA, tester de nouvelles technologies et renforcer tes connaissances pour ton travail chez Shaarp. Le conseil en investissement est un bon terrain : les données changent en continu, une erreur de chiffre se voit tout de suite, et on peut mesurer la qualité des réponses (le portefeuille gagne ou perd).

## Objectifs

1. **Apprendre** chaque brique d'un harness en la construisant à la main : boucle d'agent, outils, garde-fous, mémoire, évaluations, observabilité, validation humaine, MCP, multi-agents.
2. **Prototyper et tester** des outils nouveaux, sans pression de produit.
3. **Mesurer** : pouvoir dire si l'agent s'améliore ou régresse d'une version à l'autre.
4. **Documenter** ce qu'on apprend (chaque décision a son pourquoi, voir `09-decisions.md`).

## Ce que fait le système

- Lit des prix et des actualités (actions, ETF, crypto) via des API gratuites.
- Répond à des questions (« Que penser de cet ETF ? ») avec des **sources et un niveau de confiance**.
- Gère un **portefeuille simulé** avec de l'argent fictif.
- Enregistre chaque étape de l'agent (outils appelés, coût, durée).
- Affiche tout dans 4 pages de dashboard.

## Non-objectifs (on ne le fait pas)

- Aucun ordre réel, aucune connexion à un courtier.
- Aucun multi-utilisateur, aucune inscription publique.
- Pas de trading haute fréquence ni de flux continu au départ.
- Pas de modèle de prédiction maison : l'IA interprète, elle ne prédit pas l'avenir.

## Anti-objectifs (ce qui serait un échec même si « ça marche »)

- 🔴 Un chiffre inventé par l'IA présenté comme un fait.
- 🔴 Une promesse de gain (« tu vas gagner », « sans risque »).
- 🔴 Une clé secrète (OpenAI, données de marché) écrite dans le code ou visible en ligne.
- 🟠 Un harness qu'on ne sait pas évaluer : « ça a l'air mieux » ne suffit pas.
- 🟠 Une page publique non protégée.

## Critères de réussite

| Critère | Comment le vérifier |
|---|---|
| Aucun chiffre sans source | Garde-fou automatique + test |
| Chaque réponse est rejouable | Trace complète en base |
| Qualité mesurée | Jeu d'evals qui tourne en une commande |
| Coût maîtrisé | Budget par exécution, visible dans les traces |
| Accès protégé en ligne | Authelia devant toutes les pages |

## Public

Toi seul. Le projet est un carnet de laboratoire, pas un service.
