#!/bin/sh
# Applique les rôles applicatifs PostgreSQL sur un volume EXISTANT (étape 11, D68).
#
# Les scripts de docker-entrypoint-initdb.d ne tournent qu'à la création du volume
# : sur le VPS (volume déjà créé), lancer ceci UNE FOIS après avoir rempli
# INVESTIA_APP_DB_PASSWORD et LITELLM_APP_DB_PASSWORD dans ../.env :
#
#   sh deploy/postgres/apply-app-roles.sh
#
# Le script d'init (03-create-app-roles.sh) est idempotent : on le rejoue tel quel
# dans le conteneur postgres. Les secrets ne sont jamais affichés.
set -eu

cd "$(dirname "$0")/.."   # deploy/
set -a
# shellcheck disable=SC1091
. ../.env                  # charge les variables (dont les nouveaux mots de passe)
set +a

: "${INVESTIA_APP_DB_PASSWORD:?INVESTIA_APP_DB_PASSWORD requis dans ../.env (openssl rand -hex 32)}"
: "${LITELLM_APP_DB_PASSWORD:?LITELLM_APP_DB_PASSWORD requis dans ../.env (openssl rand -hex 32)}"

docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env exec -T \
  -e INVESTIA_APP_DB_PASSWORD="$INVESTIA_APP_DB_PASSWORD" \
  -e LITELLM_APP_DB_PASSWORD="$LITELLM_APP_DB_PASSWORD" \
  postgres sh /docker-entrypoint-initdb.d/03-create-app-roles.sh

echo "→ rôles appliqués. Mets à jour DATABASE_URL et LITELLM_DATABASE_URL dans .env"
echo "  (investia_app / litellm_app), puis : bash deploy/update.sh"
