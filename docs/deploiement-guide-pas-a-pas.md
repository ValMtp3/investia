# Guide de mise en ligne (4 bis) — à exécuter sur le VPS

> **Qui fait quoi (D48)** : les fichiers sont prêts dans le dépôt, **tu** lances les commandes ci-dessous sur le VPS. Spec : `docs/specs/4bis-mise-en-ligne.md`. Décisions : `docs/09-decisions.md` (D48 à D54).
>
> **Avant de commencer** : la revue de sécurité (`security-review`) doit être faite et sans point 🔴 ni 🟠 ouvert. Une mise en ligne est difficile à annuler : on avance phase par phase et on vérifie à chaque phase.
>
> **Particularité de ton VPS (D54, constaté le 07/11/2026)** : NPM tourne en `network_mode: host`. Il voit le `localhost` du VPS, mais **pas** les noms des conteneurs Docker. Conséquence : notre pile publie deux ports **liés à `127.0.0.1` uniquement** (invisibles d'Internet et des autres conteneurs) et NPM y accède en `localhost`.

Légende : ✅ = résultat attendu. ⚠️ = piège connu.

## Ce qu'on met en place

```text
Internet ──HTTPS──> NPM (network_mode: host, déjà sur le VPS, ports 80/443)
                       │   chaque requête est d'abord vérifiée par Authelia via 127.0.0.1:9092
                       └─── localhost:8080 ──> dashboard (nginx, port loopback 127.0.0.1)
                                                        └── /api/ ──> backend ──> postgres, redis, litellm
                       (postgres, redis, backend, litellm : réseau Docker interne, aucun port publié)
```

> **NPM** (Nginx Proxy Manager) est le « portier » du VPS : il gère déjà le HTTPS et les ports 80/443. **Authelia** est le « vigile » : NPM lui demande « cette personne est-elle connectée ? » avant de laisser passer. Seuls `dashboard` et `authelia` sont visibles par NPM, et seulement depuis le VPS lui-même (`127.0.0.1`). La base, Redis, le backend et LiteLLM restent cachés dans le réseau interne.

---

## Phase A — Préparer le VPS

1. Récupère le code (branche `feat/get-portfolio` : elle contient tout le 4 bis) :
   ```bash
   git clone --branch feat/get-portfolio https://github.com/ValMtp3/investia.git && cd investia
   ```
2. Vérifie que les ports loopback prévus sont libres sur le VPS :
   ```bash
   ss -tlnp | grep -E ':(8080|9092) '
   ```
   ✅ Aucune ligne ne sort. ⚠️ Si un port est pris ou bloqué : choisis-en un autre et note-le — il faudra le reporter dans `.env` (`DASHBOARD_LOOPBACK_PORT` / `AUTHELIA_LOOPBACK_PORT`, étape 4) **et** dans le bloc nginx de la phase C (remplacer `8080` / `9092`). Exemple : 8081 et 9093.
3. Crée ton fichier de secrets. `.env` n'est jamais commité (dépôt public, D42) :
   ```bash
   cp .env.example .env && chmod 600 .env
   ```
4. Remplis `.env`. Pour chaque secret, génère une valeur aléatoire différente :
   ```bash
   openssl rand -hex 32
   ```
   Il faut : `POSTGRES_PASSWORD`, `APP_SECRET_KEY` (c'est aussi le jeton `X-Admin-Token`, D51 : **32 caractères minimum**, sinon le backend refuse de démarrer, D53), `LITELLM_MASTER_KEY`, `AUTHELIA_DB_PASSWORD`, `AUTHELIA_SESSION_SECRET`, `AUTHELIA_STORAGE_ENCRYPTION_KEY`, `AUTHELIA_JWT_SECRET`, `EDGE_SECRET` (secret partagé avec NPM, étape C4), puis tes clés de fournisseurs (OpenRouter, Mistral, Finnhub, EODHD...). `DASHBOARD_LOOPBACK_PORT` et `AUTHELIA_LOOPBACK_PORT` gardent leurs défauts (8080 / 9092) sauf collision à l'étape 2.
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
   ✅ `postgres`, `redis`, `backend`, `litellm`, `dashboard`, `authelia` : `healthy`. `backup` : démarre, puis `healthy` après sa première sauvegarde (quelques secondes). Dans la colonne PORTS, tu dois voir `127.0.0.1:8080->80/tcp` (dashboard) et `127.0.0.1:9092->9091/tcp` (authelia), et **rien d'autre**.
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
>
> NPM est en `network_mode: host` (D54) : on lui donne des **IP littérales** (`127.0.0.1`), donc **pas de `resolver 127.0.0.11`** (le DNS interne de Docker n'est pas joignable depuis le réseau du host).

1. Dans NPM → *Hosts* → *Proxy Hosts* → *Add* :
   - Domain : `investia.valentin-fiess.fr`
   - Scheme `http`, Forward Hostname : `127.0.0.1`, Port : `8080` (ou ton `DASHBOARD_LOOPBACK_PORT`)
   - Block Common Exploits : activé. Websockets : inutile (on utilise SSE, pas WebSocket).
2. Onglet *SSL* : certificat Let's Encrypt, *Force SSL*, *HTTP/2* et *HSTS Enabled* activés (HSTS dit au navigateur de n'utiliser que HTTPS pour ce site).
3. Onglet *Advanced* → *Custom Nginx Configuration* : colle ceci (si tu as changé le port à l'étape A2, remplace `9092` par ton `AUTHELIA_LOOPBACK_PORT`) :
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
       proxy_pass http://127.0.0.1:9092;
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
       proxy_pass http://127.0.0.1:9092/auth/api/authz/auth-request;
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
4. **Secret partagé NPM → dashboard (D53).** Sans lui, tout processus du VPS pourrait appeler le dashboard en `127.0.0.1:8080` directement, sans passer par Authelia. Dans l'onglet *Custom locations* du même Proxy Host : *Add location* → *Define location* : `/`, Scheme `http`, Forward Hostname `127.0.0.1`, Port `8080` (ton `DASHBOARD_LOOPBACK_PORT`) ; clique sur l'icône d'engrenage et colle (avec la valeur de `EDGE_SECRET` de ton `.env`) :
   ```nginx
   proxy_set_header X-Edge-Secret "COLLE_ICI_LA_VALEUR_DE_EDGE_SECRET";
   ```
   Pourquoi dans cet emplacement et pas dans l'onglet *Advanced* : nginx n'hérite pas des `proxy_set_header` du serveur dès qu'un emplacement en définit lui-même, et NPM en définit. ⚠️ Non testé avec ton NPM : si cela échoue, **le site répond 403 à tout le monde** (le test D1 le montre tout de suite). C'est le comportement voulu en cas d'erreur, rien n'est exposé.
5. Enregistre. ✅ NPM affiche « Online ». ⚠️ Si NPM refuse (erreur nginx) : vérifie que la pile tourne et que les ports loopback écoutent bien :
   ```bash
   cd deploy
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env ps
   ss -tlnp | grep -E ':(8080|9092) '      # doit montrer 127.0.0.1:8080 et 127.0.0.1:9092
   curl -s http://127.0.0.1:8080/healthz     # doit répondre "ok" depuis le VPS (/healthz est ouvert sans secret)
   ```

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
3. Dans ton navigateur : ouvre `https://investia.valentin-fiess.fr/` et connecte-toi avec le mot de passe seul. ⚠️ Depuis D63 (07/11/2026) il n'y a **plus de second facteur TOTP** (l'enregistrement exigeait un e-mail que le VPS n'envoie pas ; risque assumé, voir `docs/09-decisions.md`) : la connexion se fait en `one_factor`.
4. Connecté, vérifie les 4 pages, et que la page **Agent** affiche les étapes en direct (flux SSE sans blocage) et que le graphique **Marché** se charge.
5. Route admin protégée par son propre jeton (D51). Depuis le VPS, sans jeton, on veut un refus :
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env exec dashboard \
     wget -qS -O- --post-data='{"amount": 1, "reason": "test"}' --header='Content-Type: application/json' http://investia-backend:8000/portfolio/adjust
   ```
   ✅ `HTTP/1.1 401 Unauthorized` (le capital n'est pas modifié).

Ensuite : vérifie qu'**aucun port n'est ouvert vers l'extérieur** par notre pile — `docker compose ... ps` ne montre que `127.0.0.1:8080->80/tcp` et `127.0.0.1:9092->9091/tcp`, **aucune** colonne `0.0.0.0:` — et note le résultat dans `docs/STATUS.md`.

### Tests de contournement (à faire avant de déclarer la mise en ligne terminée)

On vérifie que les raccourcis évidents sont fermés. Tests 1 à 3 depuis ton Mac, sans connexion ; test 4 depuis le VPS.

1. Le point de contrôle interne n'est pas joignable de l'extérieur :
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" https://investia.valentin-fiess.fr/internal/authelia/authz
   ```
   ✅ `404`.
2. Des en-têtes falsifiés n'ouvrent rien :
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" -H 'X-Original-URL: https://investia.valentin-fiess.fr/auth/' -H 'Remote-User: valentin' -H 'X-Forwarded-User: valentin' https://investia.valentin-fiess.fr/api/portfolio
   ```
   ✅ `302` (jamais `200`).
3. Une adresse déguisée en chemin du portail n'ouvre rien :
   ```bash
   curl -s --path-as-is -o /dev/null -w "%{http_code}\n" "https://investia.valentin-fiess.fr/auth/../api/portfolio"
   ```
   ✅ `302` ou `404` (jamais `200`).
4. **Le port loopback du dashboard est fermé sans secret, et injoignable depuis un autre conteneur.** Depuis le VPS :
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/api/portfolio
   ```
   ✅ `403` (pas de `X-Edge-Secret`). Puis, depuis un conteneur jetable, avec l'IP du VPS (`hostname -I | awk '{print $1}'`) :
   ```bash
   docker run --rm busybox wget -qS -O- "http://$(hostname -I | awk '{print $1}'):8080/api/portfolio" 2>&1 | head -3
   ```
   ✅ « Connection refused » : le port est lié à `127.0.0.1`, un autre conteneur ne peut pas y arriver.
5. **Le renouvellement du certificat fonctionne.** `auth_request` est posé sur tout le serveur : il pourrait bloquer le challenge Let's Encrypt (la vérification que tu possèdes le domaine) et le certificat expirerait en silence au bout de 90 jours. Dans NPM → *SSL Certificates* → ton certificat → *Renew now*. ✅ Le renouvellement réussit. ⚠️ S'il échoue : utilise le challenge DNS dans NPM, ou dis-le-moi avant d'aller plus loin.

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
