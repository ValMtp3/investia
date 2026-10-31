---
name: tdd-core
description: "Appliquer le TDD (test d'abord) sur le cœur du harness Investia : boucle d'agent, outils, garde-fous. L'humain définit ou review les tests ; l'agent implémente."
---

# tdd-core — test d'abord sur le cœur du harness

> **TDD** (Test-Driven Development) = écrire le test avant le code, voir le test échouer (rouge), écrire le minimum de code pour le passer au vert, puis nettoyer. Comme vérifier qu'une ampoule est grillée avant de changer le fusible.

## Périmètre

Le TDD strict s'applique au **cœur du harness** : boucle d'agent, outils (`get_quote`, `get_history`...), garde-fous (chiffres sourcés, langage interdit, budget). Partout ailleurs : tests systématiques, mais pas forcément avant le code.

## Procédure (boucle rouge → vert)

1. Écrire **un** test pour le comportement voulu, dans `backend/tests/`. Le faire tourner : il doit échouer. **Voir l'échec de ses propres yeux** — un test jamais vu rouge ne teste peut-être rien.
2. Écrire le **minimum** de code qui fait passer le test.
3. Relancer le test : vert.
4. Nettoyer le code (noms clairs, pas de duplication) sans changer le comportement. Tests toujours verts.
5. Passer au comportement suivant. Un test à la fois.

## Rôle humain / agent

- L'humain définit les scénarios de test (ou review le test écrit) **avant** l'implémentation.
- L'agent écrit l'implémentation minimale pour passer le test.

## Règles

- Jamais de `except: pass` pour faire passer un test.
- Chaque test couvre un seul comportement.
- Commandes : `uv run pytest -q`, `uv run pytest tests/test_<fichier>.py -q` pour un seul fichier.
