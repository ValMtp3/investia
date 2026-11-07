# 07 — Déploiement sur ton VPS

> **VPS** : un serveur que tu loues et gères toi-même. ⚠️ **Le tien n'est pas dédié à ce projet** : d'autres services y tournent déjà, dont **Nginx Proxy Manager (NPM)** qui gère déjà les ports 80/443, le HTTPS et les certificats. On s'intègre derrière, on ne rajoute pas un deuxième portier.

## Les services (Docker Compose)

> **Docker** empaquette chaque programme dans une boîte isolée. **Docker Compose** lance toutes les boîtes ensemble avec un seul fichier.

| Service | Rôle |
|---|---|
| `authelia` | Connexion par session, léger (~50 Mo de RAM), forward-auth demandé par NPM. Portail sur le chemin `/auth` du même domaine (Q13, D39) |
| `backend` | API Python + harness |
| `dashboard` | Pages web |
| `postgres` | **Un seul** PostgreSQL 17 : base de l'app (+ base Authelia si besoin, même serveur) |
| `redis` | Cache données de marché (TTL) + cache sémantique LLM |

**NPM (hors notre compose, déjà sur le VPS)** : point d'entrée de `investia.valentin-fiess.fr`. On y ajoute **un seul Proxy Host** vers le conteneur `dashboard` (D49 : son nginx sert les pages et aiguille `/api/` vers `investia-backend:8000` en retirant le préfixe, donc une seule origine, pas de CORS) plus le chemin `/auth` vers Authelia (D39), avec en « Advanced » la config nginx de forward-auth vers `http://investia-authelia:9091/auth/api/authz/auth-request` (pattern Authelia 4.39 + NPM). Aucune page ni API accessible sans session Authelia. Les noms `investia-*` sont des alias Docker uniques : le réseau de NPM est partagé avec d'autres piles, un nom court (`backend`, `postgres`) pourrait désigner le service d'un autre projet. NPM envoie aussi un secret partagé (en-tête `X-Edge-Secret`, D53) pour qu'un autre conteneur du réseau ne puisse pas appeler le dashboard sans passer par Authelia. SSE : le réglage (`proxy_buffering off`, délai long) vit dans `dashboard/nginx.conf` (propriétaire du fait) ; le bloc à coller dans NPM est dans `docs/deploiement-guide-pas-a-pas.md`.

Un seul serveur PostgreSQL héberge plusieurs bases de données si besoin : on sépare logiquement, pas en conteneurs. C'est comme un seul frigo avec plusieurs compartiments.

## Mêmes fichiers en local et en ligne

Trois fichiers : `docker-compose.yml` (base commune), `docker-compose.override.yml` (local, chargé automatiquement), `docker-compose.prod.yml` (VPS, chargé avec `-f`). Avantage : ce qui marche en local marche en ligne.

## Préparation du VPS (checklist)

1. ✅ Sous-domaine `investia.valentin-fiess.fr` pointant vers le VPS (DNS déjà chez toi, HTTPS géré par NPM).
2. Pare-feu : NPM a besoin de 80/443 (déjà ouverts) ; nos conteneurs ne publient **aucun port** en dehors du réseau Docker interne.
3. Connexion SSH par clé, mot de passe désactivé (déjà en place a priori — à vérifier).
4. Mises à jour de sécurité automatiques.
5. Sauvegardes : `pg_dump` quotidien, 7 jours gardés **sur le VPS seulement** (D52, remplace D40), avec test de restauration. ⚠️ Si le VPS tombe, base et dumps partent ensemble : risque assumé, à revoir si la perte devient coûteuse.

## Ressources (VPS partagé)

✅ **VPS : OVH VPS-1 2026 — 4 vCores, 8 Go RAM, 75 Go disque, partagé avec d'autres services.** Notre stack ajoute ~2-3 Go (Authelia + backend + dashboard + PostgreSQL + Redis). ⚠️ La RAM restante dépend de ce qui tourne déjà : surveiller `htop`/`docker stats` au déploiement. C'est justement pour ça qu'on a choisi Authelia (~50 Mo) plutôt qu'Authentik (1-2 Go, 4+ conteneurs) et un seul PostgreSQL.

## Mise en ligne

Pas avant l'étape 4 de la roadmap, et seulement après la revue de sécurité (voir `06-securite-et-legal.md`). Le déploiement est une action difficile à annuler : chaque mise en ligne est validée avec toi. Tu lances les commandes sur le VPS (`git pull` puis `docker compose build`), je prépare les fichiers et le guide (D48). Spec : `docs/specs/4bis-mise-en-ligne.md`.

## À prévoir plus tard

- Surveillance simple : **Uptime Kuma** (le service répond-il ?) — très léger.
- Rotation des clés.
- Journaux centralisés : à décider, rien de choisi.
