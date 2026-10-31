# STATUS — où en est le projet

> **Mis à jour le : 31/10/2026.** C'est le seul endroit qui dit l'état *actuel*. Le reste des docs décrit la cible, pas le présent.

## Étape en cours

**Étape 0 — Fondations : TERMINÉE le 31/10/2026.** Branche `feat/etape-0-fondations` pushée sur GitHub (`ValMtp3/investia`), CI verte (run 41219238270 : ruff, format, ty, pytest 25 tests + couverture 89 % ≥ 80 %). Plan : `docs/superpowers/plans/2026-10-30-etape-0-fondations.md`.

- T1 structure + toolchain uv/Ruff/ty ✅ · T2 FastAPI + config + `/health` ✅ · T3 PostgreSQL async + Alembic + `/ready` ✅ · T4 Redis async ✅ · T5 Docker Compose (vérifié via OrbStack : 4 conteneurs healthy, `/health` 200, `/ready` 200, 0 port en prod) ✅ · T6 CI + push ✅
- `cd deploy && docker compose --env-file ../.env up -d` démarre tout en local ; `curl localhost:8000/ready` → 200 `{"db":"up","redis":"up"}`.

**Prochaine étape : 1.1 — Connecteurs données + cache** (découpage D34 fait). Avant de la lancer : D36 (tester la couverture Europe de Finnhub en gratuit — attend la clé API dans `.env`).

Environnement de test local : PostgreSQL 17.11 (brew, port 5433), Redis 8.10 (brew, port 6380) pour les tests `@pytest.mark.integration` ; Docker via OrbStack.

## Bloqueurs / à vérifier maintenant

| # | Quoi | Pourquoi | Statut |
|---|---|---|---|
| D36 | Couverture Europe de Finnhub en gratuit (temps réel ou US seulement ?) | Décide si on a du temps réel européen avant l'étape 1 | 🔄 en attente : clé API Finnhub à créer sur finnhub.io et à mettre dans `.env` |
| D34 | Découper les étapes 1 et 4 de la roadmap en sous-étapes | Trop grosses pour un seul plan | ✅ fait le 31/10/2026 : étapes 1.1-1.5 et 4.1-4.5 dans `08-roadmap.md` |

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
