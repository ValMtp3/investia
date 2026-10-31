# 05 — Dashboards

Quatre pages, en TypeScript (React 19 + Vite + TanStack). Toutes protégées par Authelia.

## 1. Marché en temps réel

- Liste de suivi (actions, ETF, crypto) : prix, variation, heure de la donnée.
- Graphique d'un actif sélectionné (lightweight-charts).
- Indicateur clair « marché ouvert / fermé » et « donnée différée » le cas échéant.
- **SSE** : le serveur pousse les mises à jour, le client ne poll jamais.

## 2. Portefeuille simulé

- Capital fictif (10 000 € de départ), positions, valeur totale, performance.
- Courbe de performance comparée à un indice de référence.
- Historique des ordres simulés (qui les a proposés, validés ou non).
- **Mode admin** : ajuster le capital (ajouter / retirer de l'argent fictif), avec historique des ajustements (`capital_adjustments`).
- Bandeau permanent : « Simulation, argent fictif ».

## 3. Conseils de l'agent

- Poser une question, lire la réponse en streaming (**AG-UI / CopilotKit** : tokens, appels d'outils et état partagés en direct).
- Réponse structurée : thèse, risques, niveau de confiance, sources.
- Historique des conseils passés.
- Chaque chiffre renvoie à sa source.
- Bouton « voir la trace » vers la page 4.
- Bouton « valider » natif (interrupt AG-UI) pour les ordres simulés.

## 4. Traces et évaluations

- Liste des exécutions : date, question, coût, durée, statut des garde-fous.
- Détail pas à pas d'une exécution (messages, outils, résultats).
- Courbes des scores d'evals dans le temps : permet de voir si une modification a amélioré ou dégradé l'agent.

## Principes d'interface

- Clair et lisible avant d'être joli.
- Accessibilité de base : navigation au clavier, contrastes suffisants, libellés sur les champs.
- Les erreurs s'affichent avec un message compréhensible, jamais une page blanche.
- L'attribution exigée par les fournisseurs gratuits (ex. CoinGecko, voir `04-donnees-de-marche.md`) est affichée dans le dashboard.
- Les dashboards n'appellent jamais directement les API de marché : tout passe par le backend (les clés restent côté serveur).

## Ordre de construction

Les dashboards arrivent à l'étape 4 de la roadmap. Avant, tout se teste en ligne de commande.
