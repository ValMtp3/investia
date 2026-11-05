#!/bin/sh
# Base dédiée à Authelia (D50) sur le même serveur PostgreSQL, avec son propre utilisateur
# qui ne voit que cette base. Exécuté une seule fois, à la création du volume PostgreSQL.
# Sans AUTHELIA_DB_PASSWORD (développement local sans Authelia), on saute proprement :
# jamais de mot de passe vide ni écrit en dur dans ce dépôt public.
set -eu

if [ -z "${AUTHELIA_DB_PASSWORD:-}" ]; then
  echo "AUTHELIA_DB_PASSWORD absent : base authelia non créée (normal en local sans Authelia)."
  exit 0
fi

psql -v ON_ERROR_STOP=1 -v authelia_password="$AUTHELIA_DB_PASSWORD" \
  --username "$POSTGRES_USER" --dbname postgres <<'SQL'
SELECT format('CREATE ROLE authelia LOGIN PASSWORD %L', :'authelia_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authelia')\gexec

SELECT 'CREATE DATABASE authelia OWNER authelia'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'authelia')\gexec

REVOKE CONNECT ON DATABASE authelia FROM PUBLIC;
SQL
