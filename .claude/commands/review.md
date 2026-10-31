---
description: "Review le diff en cours contre la spec de la fonctionnalité : critères couverts, régressions, secrets. Ne modifie aucun fichier."
---

Review le diff git en cours (`git diff`, ou `git diff main...HEAD` sur une branche) contre la spec de la fonctionnalité en cours dans `docs/specs/`.

Pour chaque changement, vérifie :
1. Chaque critère d'acceptation de la spec est couvert par le code ET par un test.
2. Rien hors du périmètre de la spec.
3. Aucune régression : cherche avec grep qui utilise les fonctions/classes modifiées.
4. Règles absolues de `AGENTS.md` : pas de secret en dur, entrées validées, gestion d'erreurs, noms clairs.

Classe chaque retour : 🔴 bloquant (casse le produit, sécurité, perte de données) / 🟠 majeur (régression probable, critère non couvert, erreur non gérée) / 💡 suggestion utile. Cite fichier:ligne. Ne modifie aucun fichier.
