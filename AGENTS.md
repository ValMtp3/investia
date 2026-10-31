# AGENTS.md — Investia

Projet d'apprentissage : un **harness** d'agent IA écrit à la main (boucle, outils, garde-fous, mémoire, evals, traces) appliqué à un portefeuille simulé de 10 000 €. **Aucun conseil financier réel, aucun ordre réel.**

> **Harness** = tout ce qui entoure le modèle d'IA : ses règles, ses outils, ses tests, sa mémoire. Le modèle est le moteur, le harness est la voiture autour.

Ce fichier est la **constitution** du projet : lu par tous les outils d'IA (Claude Code, Codex, Cursor, Vibe...) au début de chaque session. Il reste volontairement court (moins de 200 lignes) : plus il est long, moins il est suivi. Le détail vit dans `docs/`.

## Début de session — lire dans cet ordre

1. `docs/GOVERNANCE.md` — quel document joue quel rôle (constitution / map / status / history).
2. `docs/STATUS.md` — étape en cours, bloqueurs actuels, zone de suppression.
3. La spec de la fonctionnalité en cours dans `docs/specs/` (si elle existe).

## Stack (résumé — détail dans `docs/11-stack-moderne-2026.md`)

- **Backend** : Python 3.12+, FastAPI async, SQLAlchemy 2.0 + Alembic, PostgreSQL 17 (+ pgvector), Redis, Polars + DuckDB. Gestionnaire : `uv`. Lint/format : `Ruff`. Types : `ty`. Tests : `pytest`.
- **Frontend** : React 19 + Vite + TanStack Router/Query + AG-UI, TypeScript.
- **IA** : harness maison, modèles derrière le gateway **LiteLLM** : Jev (décisions), GPT-6 Luna (petit), Mistral Large 4 (gros). Budget max 10-20 €/mois.
- **Déploiement** : Docker Compose derrière le Nginx Proxy Manager existant, Authelia pour la connexion, sur `investia.valentin-fiess.fr`.

## Commandes (à partir de l'étape 0)

```bash
uv run pytest            # lancer les tests
uv run ruff check .      # lint
uv run ruff format .     # formatage
uv run ty check          # vérification des types
cd deploy && docker compose --env-file ../.env up   # stack locale complète
```

## Conventions

- **Documentation en français**, **code et noms de variables en anglais**.
- Noms de variables explicites, gestion des erreurs obligatoire (`try/except`, valeurs vides vérifiées).
- Une spec écrite **avant** tout code pour chaque fonctionnalité : `docs/specs/`.
- Tests écrits **avant** le code sur le cœur du harness (boucle d'agent, outils, garde-fous) ; tests systématiques partout ailleurs.
- **Commits git** : seul **Mistral Vibe** est mentionné comme co-auteur (`Co-Authored-By: Mistral Vibe <vibe@mistral.ai>`). Aucun autre outil d'IA (Claude Code, Codex, Cursor...) ne s'ajoute comme co-auteur.
- **Ne pas réinventer la roue** : ce projet sert à apprendre et explorer. Avant d'écrire du code maison, toujours chercher si un outil, une librairie ou une solution **existe déjà et est récente** (maintenue, répandue). On préfère une solution existante à du code fait maison, et on documente ce qu'on a trouvé (nom, version, pourquoi).

## Règles absolues

1. 🔴 **Aucun secret** (clé API, mot de passe) dans le code ou les docs. Fichier `.env`, jamais commité.
2. 🔴 **Rien n'est ajouté** (librairie, outil, dépendance) sans validation explicite du propriétaire.
3. 🔴 **Toute décision métier ou technique majeure** (prix, règles, statuts, nouveau modèle de données) est discutée avec le propriétaire avant d'être codée.
4. 🟠 **Zéro régression** : un changement ne doit jamais dégrader ce qui existe. En cas de doute, le dire.
5. 🟠 Avant de dire « c'est terminé » : lancer les commandes de validation et montrer le résultat.
6. 🟠 Toute décision durable (et son pourquoi) est notée dans `docs/09-decisions.md`.

## Organisation de l'IA dans ce repo

| Élément | Où | Quand l'utiliser |
|---|---|---|
| Règles toujours vraies | ce fichier `AGENTS.md` | Jamais ailleurs (pas de copie) |
| Procédures réutilisables | `.agents/skills/<nom>/SKILL.md` | Quand la procédure s'invoque (ex. écrire une spec, lancer le TDD) |
| Commandes slash | `.claude/commands/*.md` | Raccourcis invoqués à la main (review, explain-diff) |
| Spec d'une fonctionnalité | `docs/specs/<etape>-<feature>.md` | Avant d'écrire du code |
| Suivi du projet | `docs/STATUS.md` | Blockers, étape en cours, suppressions |

## Où trouver quoi

| J'ai besoin de... | Je vais dans |
|---|---|
| La vision, le périmètre, les non-objectifs | `docs/01-vision-et-perimetre.md` |
| L'architecture des briques | `docs/02-architecture.md` |
| Le détail du harness (boucle, garde-fous, evals) | `docs/03-harness.md` |
| Les sources de données de marché | `docs/04-donnees-de-marche.md` |
| Les 4 pages du dashboard | `docs/05-dashboards.md` |
| Sécurité et légal | `docs/06-securite-et-legal.md` |
| Le déploiement sur le VPS | `docs/07-deploiement-vps.md` |
| La roadmap par étapes | `docs/08-roadmap.md` |
| Pourquoi tel choix (ADR) | `docs/09-decisions.md` |
| La définition d'un mot technique | `docs/10-glossaire.md` |
| La stack détaillée et à jour | `docs/11-stack-moderne-2026.md` |
| Les plans détaillés par étape | `docs/superpowers/plans/` |
