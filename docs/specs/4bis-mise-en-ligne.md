# Spec — 4 bis : Mise en ligne sur le VPS

*Écrite le : 2026-11-05 | Mise à jour le 2026-11-07 (D54 : NPM en `network_mode: host`, ports loopback) | Étape roadmap : 4 bis | Statut : validée par le propriétaire le 2026-11-05*

## Objectif

`https://investia.valentin-fiess.fr` affiche le dashboard et ne répond **qu'après connexion Authelia** (mot de passe + TOTP). Le backend, PostgreSQL, Redis et LiteLLM ne sont joignables que depuis le réseau Docker interne.

## Pourquoi

Dernière étape avant l'usage réel du projet. Décisions : D12, D13, D21, D39 (existantes) et D48 à D54 (`docs/09-decisions.md`). `docs/06-securite-et-legal.md` impose une revue de sécurité avant toute mise en ligne.

## Contraintes

- **Le propriétaire exécute les commandes sur le VPS** ; je livre fichiers + guide (D48). Aucune action sur le VPS depuis cette session.
- VPS OVH VPS-1 **partagé** (4 vCores, 8 Go) avec NPM déjà en place sur 80/443. NPM tourne en `network_mode: host` (constaté le 07/11/2026, D54) : on ne publie **aucun port sur `0.0.0.0`** — `dashboard` et `authelia` écoutent sur `127.0.0.1` uniquement, NPM y accède en `localhost` (D13, D54).
- Aucun secret dans le repo public (D42) : tout dans `.env` sur le VPS, `.env.example` sans valeurs.
- Ne rien casser en local : `docker-compose.yml` + `override.yml` continuent de fonctionner (`cd deploy && docker compose --env-file ../.env up`).
- SSE (`/agent/run`, `/market/stream`) : pas de buffering, timeout long, dans le nginx du dashboard **et** dans NPM.
- Sauvegardes sur le VPS seulement (D52, risque assumé).
- Durcissements issus de la revue de sécurité du 05/11/2026 : D53 (alias Docker uniques, secret partagé NPM -> dashboard, variables explicites pour backend/LiteLLM, jeton admin >= 32 caractères).

## Critères d'acceptation

- [ ] `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` passe sans erreur, et **aucun** service ne publie de port sur `0.0.0.0` (seuls `dashboard`/`authelia`, liés à `127.0.0.1` — D54, testé par `test_compose.py`).
- [ ] Le service `dashboard` (nginx) sert `/` et aiguille `/api/x` vers `backend:8000/x` ; test local : `curl localhost:<port-test>/api/health` → 200.
- [ ] Le dashboard construit avec `VITE_API_URL=/api` ; plus aucun appel vers `127.0.0.1:8000` dans le build de prod.
- [ ] Le service `authelia` démarre, sert le portail sur `/auth`, stocke dans la base PostgreSQL `authelia` ; un compte unique avec TOTP.
- [ ] En ligne, sans session : `curl -I https://investia.valentin-fiess.fr/` → redirection vers `/auth` ; `curl https://investia.valentin-fiess.fr/api/portfolio` → 401/302, **jamais** 200.
- [ ] Avec session : les 4 pages marchent ; le chat de la page Agent reçoit les événements en direct (pas de blocage du flux SSE).
- [ ] `POST /portfolio/adjust` sans `X-Admin-Token` → refusé, même avec session Authelia (D51).
- [ ] Script de sauvegarde : un `pg_dump` quotidien, 7 jours gardés ; **test de restauration** réussi sur une base vide.
- [ ] `docker compose -f ... ps` : tous les services `healthy` ; `docker stats` relevé et noté (RAM).
- [ ] Revue de sécurité (`security-review` + agent `security-reviewer`) : aucun point 🔴 bloquant ni 🟠 critique ouvert.

## Fichiers touchés (prévision)

| Fichier | Changement |
|---|---|
| `deploy/docker-compose.yml` / `docker-compose.prod.yml` | ajout des services `dashboard`, `authelia`, `backup` (prod) |
| `dashboard/Dockerfile`, `dashboard/nginx.conf` | build 2 temps + routage `/api/` + SSE sans buffering |
| `deploy/authelia/configuration.yml` (+ modèle `users_database.yml`) | portail `/auth`, TOTP, stockage PostgreSQL, **sans secret** |
| `deploy/postgres/init/` | création de la base et de l'utilisateur `authelia` |
| `deploy/backup/` | script `pg_dump` quotidien + rotation 7 jours + script de restauration |
| `.env.example` | nouvelles variables, sans valeurs |
| `docs/07-deploiement-vps.md` | corrigé : un Proxy Host + `/auth` (D49), sauvegardes VPS (D52) |
| `docs/deploiement-guide-pas-a-pas.md` (nom à confirmer) | guide à exécuter sur le VPS |
| `docs/STATUS.md` | étape 4 bis en cours puis terminée |

## Comment vérifier

```bash
cd deploy
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env config   # syntaxe + aucun port publié
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env up -d --build
docker compose ps                                                                          # tous healthy
curl -I https://investia.valentin-fiess.fr/                                                # → redirection /auth
```

## Hors périmètre

- Pas de CI/CD automatique ni de registre d'images (D48).
- Pas de sauvegarde hors du VPS (D52).
- Pas d'Uptime Kuma, de rotation des clés ni de journaux centralisés (« à prévoir plus tard » dans `07`).
- Aucune modification de la logique métier du backend ou du harness.
