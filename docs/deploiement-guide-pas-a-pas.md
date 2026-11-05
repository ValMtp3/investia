# Guide de mise en ligne (4 bis) — à exécuter sur le VPS

> **Qui fait quoi (D48)** : les fichiers sont prêts dans le dépôt, **tu** lances les commandes ci-dessous sur le VPS. Spec : `docs/specs/4bis-mise-en-ligne.md`. Décisions : `docs/09-decisions.md` (D48 à D52).
>
> **Avant de commencer** : la revue de sécurité (`security-review`) doit être faite et sans point 🔴 ni 🟠 ouvert. Une mise en ligne est difficile à annuler : on avance phase par phase et on vérifie à chaque phase.

Légende : ✅ = résultat attendu. ⚠️ = piège connu.

## Ce qu'on met en place

```text
Internet ──HTTPS──> NPM (déjà sur le VPS) ──> /auth  ──> authelia   (connexion mot de passe + TOTP)
                       │  chaque requête est d'abord vérifiée par Authelia
                       └──────────────────> /      ──> dashboard (nginx) ──> /api/ ──> backend ──> postgres, redis, litellm
```

> **NPM** (Nginx Proxy Manager) est le « portier » du VPS : il gère déjà le HTTPS et les ports 80/443. **Authelia** est le « vigile » : NPM lui demande « cette personne est-elle connectée ? » avant de laisser passer. Seuls `dashboard` et `authelia` sont visibles par NPM. La base, Redis et le backend restent cachés dans le réseau interne.

---

## Phase A — Préparer le VPS

1. Récupère le code (branche à confirmer avec moi avant le déploiement) :
   ```bash
   git clone https://github.com/ValMtp3/investia.git && cd investia
   ```
2. Cherche le nom du réseau Docker de NPM :
   ```bash
   docker network ls
   ```
   ✅ Tu repères celui de NPM (souvent `proxy`, `npm_default` ou `nginxproxymanager_default`). Note-le : c'est `NPM_NETWORK_NAME`.
3. Crée ton fichier de secrets. `.env` n'est jamais commité (dépôt public, D42) :
   ```bash
   cp .env.example .env && chmod 600 .env
   ```
4. Remplis `.env`. Pour chaque secret, génère une valeur aléatoire différente :
   ```bash
   openssl rand -hex 32
   ```
   Il faut : `POSTGRES_PASSWORD`, `APP_SECRET_KEY` (c'est aussi le jeton `X-Admin-Token`, D51), `LITELLM_MASTER_KEY`, `AUTHELIA_DB_PASSWORD`, `AUTHELIA_SESSION_SECRET`, `AUTHELIA_STORAGE_ENCRYPTION_KEY`, `AUTHELIA_JWT_SECRET`, `NPM_NETWORK_NAME`, puis tes clés de fournisseurs (OpenRouter, Mistral, Finnhub, EODHD...).
   ⚠️ Dans `DATABASE_URL` et `LITELLM_DATABASE_URL`, remplace `CHANGE_ME` par le **même** `POSTGRES_PASSWORD`.
5. Crée ton utilisateur Authelia **avant tout démarrage** :
   ```bash
   cp deploy/authelia/users_database.example.yml deploy/authelia/users_database.yml
   docker run --rm -it authelia/authelia:4.39.28 authelia crypto hash generate argon2
   ```
   La commande te demande ton mot de passe (choisis-en un long) et affiche `Digest: $argon2id$...`. Colle ce texte à la place de `$argon2id$REMPLACER_PAR_LE_HASH_GENERE` dans `deploy/authelia/users_database.yml`.
   ⚠️ Si ce fichier n'existe pas au démarrage, Docker crée un **dossier** du même nom et Authelia plante.

## Phase B — Démarrer la pile (sans NPM encore)

1. Vérifie la configuration (aucune erreur attendue) :
   ```bash
   cd deploy
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env config > /dev/null && echo OK
   ```
2. Démarre. ⚠️ Le build prend quelques minutes et de la RAM sur un VPS partagé : garde `htop` ou `docker stats` ouvert dans un autre terminal.
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env up -d --build
   ```
3. Applique les migrations de la base. Elles ne sont **pas** lancées automatiquement : sans elles, la base est vide.
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env exec backend uv run alembic upgrade head
   ```
   ✅ La dernière ligne finit par `0005_portfolio`.
4. Vérifie que tout est en bonne santé :
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env ps
   ```
   ✅ `postgres`, `redis`, `backend`, `litellm`, `dashboard`, `authelia` : `healthy`. `backup` : démarre, puis `healthy` après sa première sauvegarde (quelques secondes).
5. Note la RAM utilisée (`docker stats --no-stream`). La spec attend ~2-3 Go pour toute la pile.

⚠️ **Si le volume PostgreSQL existait déjà avant ce déploiement** : le script d'init ne rejoue pas, la base `authelia` n'existe pas. Crée-la à la main (remplace le mot de passe par ta valeur `AUTHELIA_DB_PASSWORD`) :
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env exec postgres \
  psql -U investia -d postgres -c "CREATE ROLE authelia LOGIN PASSWORD 'TON_AUTHELIA_DB_PASSWORD'" \
  -c "CREATE DATABASE authelia OWNER authelia" -c "REVOKE CONNECT ON DATABASE authelia FROM PUBLIC"
```
Puis `docker compose ... restart authelia`.

## Phase C — Brancher NPM

> ⚠️ **Ce bloc nginx n'a pas été testé avec ton NPM réel** : il suit la documentation d'Authelia pour nginx. La phase D sert à le vérifier. Si un test échoue, ne force rien : donne-moi le message et la sortie de `docker logs <conteneur NPM>`.

1. Dans NPM → *Hosts* → *Proxy Hosts* → *Add* :
   - Domain : `investia.valentin-fiess.fr`
   - Scheme `http`, Forward Hostname : `investia-dashboard`, Port : `80`
   - Block Common Exploits : activé. Websockets : inutile (on utilise SSE, pas WebSocket).
2. Onglet *SSL* : certificat Let's Encrypt, *Force SSL* et *HTTP/2* activés.
3. Onglet *Advanced* → *Custom Nginx Configuration* : colle ceci.
   ```nginx
   # Chaque requête est d'abord vérifiée par Authelia.
   auth_request /internal/authelia/authz;
   auth_request_set $redirection_url $upstream_http_location;
   error_page 401 =302 $redirection_url;

   # Flux SSE (/api/agent/run, /api/market/stream) : pas de mise en mémoire, délai long.
   proxy_buffering off;
   proxy_read_timeout 3600s;

   # Le portail de connexion est lui-même ouvert, sinon on ne pourrait jamais se connecter.
   location /auth {
       auth_request off;
       resolver 127.0.0.11 valid=10s ipv6=off;
       set $upstream_authelia http://investia-authelia:9091;
       proxy_pass $upstream_authelia;
       proxy_http_version 1.1;
       proxy_set_header Host $host;
       proxy_set_header X-Forwarded-Proto $scheme;
       proxy_set_header X-Forwarded-Host $http_host;
       proxy_set_header X-Forwarded-URI $request_uri;
       proxy_set_header X-Forwarded-For $remote_addr;
   }

   # Point de contrôle interne : jamais joignable depuis Internet.
   location /internal/authelia/authz {
       internal;
       auth_request off;   # sans cette ligne, le contrôle se rappellerait lui-même en boucle
       resolver 127.0.0.11 valid=10s ipv6=off;
       set $upstream_authelia http://investia-authelia:9091;
       proxy_pass $upstream_authelia/auth/api/authz/auth-request;
       proxy_pass_request_body off;
       proxy_http_version 1.1;
       proxy_set_header Content-Length "";
       proxy_set_header Connection "";
       proxy_set_header Host $host;
       proxy_set_header X-Original-Method $request_method;
       proxy_set_header X-Original-URL $scheme://$http_host$request_uri;
       proxy_set_header X-Forwarded-For $remote_addr;
   }
   ```
4. Enregistre. ✅ NPM affiche « Online ». ⚠️ Si NPM refuse (« host not found in upstream » ou erreur nginx) : la pile de la phase B n'est pas démarrée ou n'est pas sur le réseau `NPM_NETWORK_NAME`. Vérifie avec `docker network inspect <réseau NPM>`, on doit y voir `investia-dashboard` et `investia-authelia`.

## Phase D — Vérifier (critères de la spec)

Depuis ton Mac (pas besoin du VPS) :

1. Sans connexion, la page redirige vers le portail :
   ```bash
   curl -sI https://investia.valentin-fiess.fr/ | grep -i "^HTTP\|^location"
   ```
   ✅ `302` et une `location` vers `https://investia.valentin-fiess.fr/auth/?rd=...`.
2. Sans connexion, l'API ne répond **jamais** 200 :
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" https://investia.valentin-fiess.fr/api/portfolio
   ```
   ✅ `302` (jamais `200`).
3. Dans ton navigateur : ouvre `https://investia.valentin-fiess.fr/`, connecte-toi, puis enregistre ton TOTP (appli d'authentification). Le code de vérification demandé est écrit dans un fichier (pas d'e-mail) :
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env exec authelia cat /data/notification.txt
   ```
4. Connecté, vérifie les 4 pages, et que la page **Agent** affiche les étapes en direct (flux SSE sans blocage) et que le graphique **Marché** se charge.
5. Route admin protégée par son propre jeton (D51). Depuis le VPS, sans jeton, on veut un refus :
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env exec dashboard \
     wget -qS -O- --post-data='{"amount": 1, "reason": "test"}' --header='Content-Type: application/json' http://backend:8000/portfolio/adjust
   ```
   ✅ `HTTP/1.1 401 Unauthorized` (le capital n'est pas modifié).

Ensuite : vérifie qu'**aucun port** n'est ouvert vers l'extérieur par notre pile (`docker compose ... ps` ne montre aucune colonne `0.0.0.0:`), et note le résultat dans `docs/STATUS.md`.

## Phase E — Sauvegardes : le test de restauration est obligatoire

Une sauvegarde jamais restaurée n'est pas une sauvegarde (D52). Une fois la première faite :

1. Liste les fichiers :
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env exec backup ls -l /backups
   ```
2. Restaure la dernière sauvegarde de `investia` dans une **base de test vide**, jamais dans la vraie :
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env exec postgres \
     psql -U investia -d postgres -c "CREATE DATABASE restore_check"
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env exec backup \
     bash -c 'bash /scripts/restore.sh "$(ls -1 /backups/investia-2*.dump | tail -1)" restore_check'
   ```
3. Contrôle que les tables sont revenues, puis supprime la base de test :
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env exec postgres \
     psql -U investia -d restore_check -c "\dt"
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env exec postgres \
     psql -U investia -d postgres -c "DROP DATABASE restore_check"
   ```

⚠️ Pour une **vraie** restauration de la base `authelia`, arrête d'abord Authelia (`docker compose ... stop authelia`), restaure, puis relance-le.
⚠️ Rappel D52 : ces sauvegardes sont sur le même disque que la base. Elles protègent d'une erreur ou d'une corruption, pas de la perte du VPS.

## Revenir en arrière

1. Dans NPM : désactive ou supprime le Proxy Host `investia.valentin-fiess.fr`. Le site n'est plus joignable, les autres services du VPS ne bougent pas.
2. Arrête la pile **sans supprimer les données** :
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env down
   ```
   🔴 Ne jamais ajouter `-v` : cela supprimerait les volumes (base de données, sauvegardes, état d'Authelia).

## Mettre à jour plus tard

```bash
git pull
cd deploy
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env exec backend uv run alembic upgrade head
```
