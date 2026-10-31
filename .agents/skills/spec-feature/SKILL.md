---
name: spec-feature
description: "Écrire (ou faire écrire) la spec d'une fonctionnalité dans docs/specs/ avant tout code : objectif, contraintes, critères d'acceptation concrets, fichiers touchés, comment vérifier."
---

# spec-feature — la spec avant le code

> Une **spec** (spécification) = le contrat écrit d'une fonctionnalité : ce qu'elle fait, ce qu'elle ne fait pas, et comment on prouvera qu'elle marche. Comme un devis signé avant les travaux.

## Procédure

1. Partir de `docs/specs/template-spec.md` et créer `docs/specs/<etape>-<feature>.md`.
2. Remplir chaque section. Règles :
   - **10 à 30 lignes** de spec suffisent. Au-delà, découper la fonctionnalité.
   - Chaque critère d'acceptation doit être **concret et copiable-collable** (une commande, un test, un comportement observable). Si on ne peut pas l'écrire concrètement, la spec est trop floue → la découper ou la préciser.
   - Lister les fichiers touchés et le hors périmètre.
3. Faire valider la spec par le propriétaire du projet **avant** d'écrire du code.
4. Marquer le statut « validée » en haut de la spec.

## Anti-patterns

- Une spec de 200 lignes que personne ne relit : découper en plus petites specs.
- Des critères du type « le code est propre » : non vérifiable. Dire plutôt « `uv run ruff check .` passe sans erreur ».
- Coder d'abord et écrire la spec après : non. La spec sert à éviter que l'agent ne devine de travers.
