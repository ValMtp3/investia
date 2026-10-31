---
name: review-diff
description: "Reviewer un diff (git diff) contre la spec de la fonctionnalité : le code fait-il exactement ce que la spec demande, pas plus, pas moins ? Signaler bloquants et régressions."
---

# review-diff — relire le code contre la spec, pas au feeling

## Procédure

1. Lire la spec concernée dans `docs/specs/` (celle au statut « validée » ou « en cours »).
2. Lancer `git diff` (ou `git diff main...HEAD` sur une branche) et lire chaque changement.
3. Vérifier, critère par critère d'acceptation de la spec :
   - chaque critère est-il couvert par le code **et** par un test ?
   - le code fait-il **plus** que la spec (hors périmètre) ?
   - le code casse-t-il quelque chose d'existant (régression) ? Chercher avec `grep` qui utilise les fonctions modifiées.
4. Vérifier les règles absolues de `AGENTS.md` : pas de secret en dur, entrées validées, gestion des erreurs présente, noms de variables clairs.
5. Classer les retours :
   - 🔴 bloquant : casse le produit, faille de sécurité, perte de données, secret exposé.
   - 🟠 majeur : régression probable, critère de la spec non couvert, gestion d'erreur absente.
   - 💡 suggestion : gain de clarté ou de fiabilité.
   - Le reste (style, micro-optimisations) : ne pas remonter.

## Règles

- Ne pas réécrire le code pendant la review : on signale, l'humain décide.
- Citer fichier et ligne pour chaque retour.
