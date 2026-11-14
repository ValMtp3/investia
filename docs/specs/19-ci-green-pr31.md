# Spec — 19 : CI green — rendre la PR #31 (chantier 17 → main) verte sur GitHub

*Écrite le : 14/11/2026 | Étape roadmap : 19 (infra CI) | Statut : validée le 14/11/2026, TERMINÉE le 14/11/2026*

## Constat (vérifié le 14/11/2026)

`origin/main` est à `6af03b0` (08/11, PR #18) : les chantiers 12–16 n'avaient jamais été poussés sur GitHub, donc la **PR #31 embarque ~64 commits jamais testés par la CI GitHub**. Résultat, CI rouge sur 4 jobs :

| Job | Échecs constatés | Cause racine |
|---|---|---|
| ruff | 54 erreurs (33 E501, 10 E402, 8 F401, 1 F841, 2 I001) | dérive lint dans des tests des chantiers 12–16 (jamais lintés en CI) |
| format | 15 fichiers non formatés | idem |
| ty | 11 erreurs (tests : `None` subscript, `DbTraceStore` arg, `SentenceTransformer`…) | idem |
| pytest | tests `integration`/live (DB user `u`, gateway :4000 absent) + `test_portfolio_api` (URL SQLAlchemy non parsée en env CI) | `ci.yml` lance `pytest --cov` **sans** `-m "not integration"` ; les tests integration sont prévus pour le pgvector/Redis local (STATUS) |

Aucun de ces échecs n'est une régression de code applicatif : la suite locale est verte (631 passed / 1 skip sur la branche 18, 622 sur la branche 17).

## Objectif

PR #31 verte (4 jobs) en ne touchant que CI + tests + lint — **zéro changement de comportement applicatif**.

## Plan

1. **`.github/workflows/ci.yml`** : étape pytest → `uv run pytest --cov --cov-fail-under=80 -m "not integration"` (les tests integration restent pour le local pgvector/Redis, documenté dans STATUS). Diagnostiquer `test_portfolio_api` en env CI (reproduire localement avec les mêmes env) : soit il est marqué `integration` s'il a besoin de DB, soit on corrige la lecture de l'URL.
2. **ruff** : `ruff check --fix` (I001, F401 sûrs), puis wrap manuel des E501 restants, `# noqa: E402` là où l'import milieu de fichier est intentionnel (pattern tests existant). Aucun `per-file-ignores` ajouté (on ne fragilise pas la règle).
3. **format** : `ruff format .` (15 fichiers).
4. **ty** : corriger les 11 diagnostics dans les tests (assert `is not None`, casts) sans changer la logique.
5. **Vérification locale** : `uv run pytest -q -m "not integration"` vert + `ruff check .` + `ruff format --check .` + `ty check` tous propres + reproduire le job pytest CI avec les env CI (`DATABASE_URL=postgresql+asyncpg://investia:ci-test@localhost:5432/investia_test` etc.) pour `test_portfolio_api`.
6. Push sur `feat/etape-17-forecast` → la PR #31 se met à jour et sa CI relance.

## Contraintes

- Aucun changement de logique métier ; diffs de tests = lint/format/asserts uniquement.
- La suite non-integration locale doit rester verte à chaque étape.
- Pas de dépendance nouvelle.

## Critères d'acceptation

- [x] `ruff check .` = 0 ; `ruff format --check .` = OK (176 fichiers) ; `ty check` = 0 — branche feat/etape-17-forecast. Fixes : `ruff --fix` (11), `ruff format .` (15 fichiers, dont repli des signatures `chat(...)` longues), 10 `# noqa: E402` sur imports milieu de fichier intentionnels (tests), 2 docstrings raccourcis, 1 F841 (`cache` inutilisé) supprimé, ty : asserts `is not None` (test_agui), `setattr` (test_embeddings_local), `or ""` (test_evals_deepeval), `cast(Any, ...)` (test_redaction).
- [x] `uv run pytest -q -m "not integration"` vert (622 passed / 1 skip) ; job pytest CI reproduit localement avec les env CI exacts (`DATABASE_URL=…investia:ci-test@localhost:5432…` etc.) : 622 passed, `--cov-fail-under=80` OK. `test_portfolio_api` passe avec l'env CI (10 passed).
- [x] ci.yml : étape pytest → `-m "not integration"` (tests integration = pgvector/Redis local, cf. STATUS).
- [ ] PR #31 : 4 jobs CI verts après push (vérifié après push).
- [x] STATUS.md à jour.

## Fichiers touchés

`.github/workflows/ci.yml`, tests (lint/format/asserts), `docs/STATUS.md`, cette spec. Éventuellement `pyproject.toml` si un réglage s'avère nécessaire (à valider).

## Hors périmètre

- Faire tourner les tests integration en CI (nécessiterait pgvector service + env alignés — chantier séparé si voulu).
- Refaire passer toute l'historique ; on répare la tête de branche.
