# STATUS — où en est le projet

> **Mis à jour le : 31/10/2026.** C'est le seul endroit qui dit l'état *actuel*. Le reste des docs décrit la cible, pas le présent.

## Étape en cours

**Étape 0 — Fondations** (en cours, branche `feat/etape-0-fondations`). Plan détaillé : `docs/superpowers/plans/2026-10-30-etape-0-fondations.md`.

Avancement (31/10/2026) : Tasks 1 à 5 terminées et commitées — structure + toolchain (T1), FastAPI + config + `/health` (T2), PostgreSQL async + Alembic + `/ready` (T3), Redis async (T4), Docker Compose complet (T5, vérifié en local via OrbStack : `compose up` → 4 conteneurs healthy, `/health` 200, `/ready` 200 db+redis up, 0 port publié en config prod). **Reste : Task 6 (CI GitHub Actions + premier push).**

Environnement de test local : PostgreSQL 17.11 (brew, port 5433) et Redis 8.10 (brew, port 6380) lancés en local pour les tests `@pytest.mark.integration` ; Docker via OrbStack.

## Bloqueurs / à vérifier maintenant

| # | Quoi | Pourquoi | Statut |
|---|---|---|---|
| D36 | Couverture Europe de Finnhub en gratuit (temps réel ou US seulement ?) | Décide si on a du temps réel européen avant l'étape 1 | 🔄 à tester |
| D34 | Découper les étapes 1 et 4 de la roadmap en sous-étapes | Trop grosses pour un seul plan | 🔄 à faire avant l'étape 1 |

## Zone de suppression (ne pas recréer)

| Quoi | Pourquoi retiré | Remplacé par |
|---|---|---|
| Hébergement Render | Supposé par erreur pendant le cadrage ; l'hébergement est le VPS perso | `docs/07-deploiement-vps.md` (Docker Compose derrière NPM) |
| Authentik | Trop lourd (~1-2 Go) pour un seul utilisateur | Authelia (~50 Mo), décision D12 |
| Caddy en frontal | Le VPS est partagé, NPM gère déjà 80/443 et le HTTPS | Nginx Proxy Manager existant, D13 |
| `redis-stack-server` | La recherche vectorielle est dans PostgreSQL (pgvector) | Image `redis:8`, D33 |
| pandas | Remplacé par Polars (10-100x plus rapide sur les séries de prix) | Polars + DuckDB, D30 |

## Organisation IA du projet (résumé — détail dans `AGENTS.md`)

- Règles toujours vraies : `AGENTS.md` (racine, lu par tous les outils d'IA).
- Procédures réutilisables : `.agents/skills/` (versionnées dans le repo).
- Spec avant code : `docs/specs/`.
- Commandes slash : `.claude/commands/`.
- Suivi : ce fichier.
