# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Utilisateur réel : le propriétaire du projet, seul, qui ouvre le dashboard pour suivre un portefeuille simulé et comprendre comment l'agent IA décide.

Exigence confirmée : l'interface ne doit pas être pensée pour une seule personne. Elle doit rester compréhensible par un public non expert, comme pour un produit grand public. Un inconnu doit comprendre ce qu'il voit sans explication.

## Product Purpose

Investia est un projet d'apprentissage : un agent IA gère un portefeuille simulé de 10 000 € (argent fictif). Le dashboard sert à voir le marché, le portefeuille, les conseils de l'agent et les traces de son raisonnement. Aucun conseil financier réel, aucun ordre réel.

## Positioning

On voit comment l'agent a raisonné : chaque conseil renvoie à sa trace (outils appelés, sources, garde-fous, scores d'évaluation). Un outil d'investissement classique ne montre pas son raisonnement.

## Operating Context

- Quatre pages : marché en temps réel, portefeuille simulé, conseils de l'agent, traces et évaluations (voir `docs/05-dashboards.md`).
- Données de marché poussées en direct par le serveur (SSE). Le navigateur n'appelle jamais les API de marché.
- Connexion via Authelia, hébergé sur `investia.valentin-fiess.fr`.

## Capabilities and Constraints

- Stack frontend en place : React 19, Vite, TanStack Router/Query, TypeScript.
- Bandeau « Simulation, argent fictif » visible en permanence.
- Chaque chiffre renvoie à sa source.
- Attribution exigée par les fournisseurs gratuits (ex. CoinGecko) affichée dans le dashboard.
- Mode admin : ajuster le capital fictif, avec historique.
- Marché ouvert / fermé et donnée différée toujours signalés.

## Brand Commitments

Aucun nom de marque, logo ou charte existants au-delà du nom « Investia ». Direction visuelle à décider (ambiance « salle de contrôle / instrument » souhaitée, en évitant les clichés « terminal hacker », néon, cartes arrondies SaaS, Inter + Lucide, bento et glassmorphism).

## Evidence on Hand

- Dashboard React existant (4 pages, API portefeuille, chat agent en streaming, marché temps réel), graphique encore mock sur une partie.
- Aucun témoignage, client, benchmark ou performance réelle : ne rien inventer.

## Product Principles

1. Clair et lisible avant d'être joli.
2. Montrer d'où vient chaque chiffre et chaque décision.
3. Toujours rappeler que c'est une simulation.
4. Une erreur s'explique, elle n'affiche jamais une page blanche.

## Accessibility & Inclusion

Navigation au clavier, contrastes suffisants, libellés sur tous les champs. Compréhensible par un public non expert en finance.
