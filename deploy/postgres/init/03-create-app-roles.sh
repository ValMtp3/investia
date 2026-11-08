#!/bin/sh
# Rôles applicatifs PostgreSQL sans SUPERUSER (étape 11, D68) : investia_app possède
# la base investia (backend + Alembic), litellm_app possède la base litellm.
# Le compte POSTGRES_USER (superuser) n'est plus utilisé que par le conteneur
# backup (pg_dump) et le healthcheck.
#
# Idempotent : rejouable à la main sur un volume existant (apply-app-roles.sh).
# Sans les mots de passe (développement local) : on saute proprement, comme 02 —
# jamais de mot de passe vide ni écrit en dur dans ce dépôt public.
set -eu

if [ -z "${INVESTIA_APP_DB_PASSWORD:-}" ] || [ -z "${LITELLM_APP_DB_PASSWORD:-}" ]; then
  echo "INVESTIA_APP_DB_PASSWORD / LITELLM_APP_DB_PASSWORD absents : rôles applicatifs non créés (normal en local)."
  exit 0
fi

# --- Base "postgres" : créer/mettre à jour les rôles, transférer les bases. ---
psql -v ON_ERROR_STOP=1 \
  -v admin_role="$POSTGRES_USER" \
  -v investia_app_password="$INVESTIA_APP_DB_PASSWORD" \
  -v litellm_app_password="$LITELLM_APP_DB_PASSWORD" \
  --username "$POSTGRES_USER" --dbname postgres <<'SQL'
SELECT format('CREATE ROLE investia_app LOGIN PASSWORD %L', :'investia_app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'investia_app')\gexec
SELECT format('CREATE ROLE litellm_app LOGIN PASSWORD %L', :'litellm_app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'litellm_app')\gexec

-- Rejoué à chaque passage : le mot de passe suit toujours l'env, les privilèges restent verrouillés.
ALTER ROLE investia_app LOGIN PASSWORD :'investia_app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;
ALTER ROLE litellm_app LOGIN PASSWORD :'litellm_app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;

-- Les bases appartiennent aux rôles applicatifs (création de tables autorisée ;
-- le superuser n'est plus utilisé par aucun service applicatif).
ALTER DATABASE investia OWNER TO investia_app;
ALTER DATABASE litellm OWNER TO litellm_app;

-- Personne d'autre ne se connecte à ces bases (les rôles app n'ont accès
-- qu'à la leur ; la base "postgres" et template1 restent réservées à l'admin).
REVOKE CONNECT ON DATABASE investia FROM PUBLIC;
REVOKE CONNECT ON DATABASE litellm FROM PUBLIC;
REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;
REVOKE CONNECT ON DATABASE template1 FROM PUBLIC;
GRANT CONNECT ON DATABASE investia TO investia_app;
GRANT CONNECT ON DATABASE litellm TO litellm_app;
GRANT CONNECT ON DATABASE postgres TO :"admin_role";
SQL

# --- Chaque base applicative : les objets existants suivent le nouveau propriétaire. ---
# (REASSIGN OWNED est impossible ici : il toucherait aussi les objets partagés
# — les bases elles-mêmes — owned by le compte admin. On transfère objet par objet.)
psql -v ON_ERROR_STOP=1 -v admin_role="$POSTGRES_USER" \
  --username "$POSTGRES_USER" --dbname investia <<'SQL'
-- CREATE EXTENSION exige un privilège système : fait par l'admin, pas par le rôle app.
CREATE EXTENSION IF NOT EXISTS vector;
ALTER SCHEMA public OWNER TO investia_app;
SELECT format('ALTER TABLE %I.%I OWNER TO investia_app', schemaname, tablename)
FROM pg_tables WHERE tableowner = :'admin_role'
  AND schemaname NOT LIKE 'pg\_%' AND schemaname <> 'information_schema'\gexec
SELECT format('ALTER SEQUENCE %I.%I OWNER TO investia_app', schemaname, sequencename)
FROM pg_sequences WHERE sequenceowner = :'admin_role'
  AND schemaname NOT LIKE 'pg\_%' AND schemaname <> 'information_schema'\gexec
SELECT format('ALTER VIEW %I.%I OWNER TO investia_app', schemaname, viewname)
FROM pg_views WHERE viewowner = :'admin_role'
  AND schemaname NOT LIKE 'pg\_%' AND schemaname <> 'information_schema'\gexec
SQL

psql -v ON_ERROR_STOP=1 -v admin_role="$POSTGRES_USER" \
  --username "$POSTGRES_USER" --dbname litellm <<'SQL'
ALTER SCHEMA public OWNER TO litellm_app;
SELECT format('ALTER TABLE %I.%I OWNER TO litellm_app', schemaname, tablename)
FROM pg_tables WHERE tableowner = :'admin_role'
  AND schemaname NOT LIKE 'pg\_%' AND schemaname <> 'information_schema'\gexec
SELECT format('ALTER SEQUENCE %I.%I OWNER TO litellm_app', schemaname, sequencename)
FROM pg_sequences WHERE sequenceowner = :'admin_role'
  AND schemaname NOT LIKE 'pg\_%' AND schemaname <> 'information_schema'\gexec
SELECT format('ALTER VIEW %I.%I OWNER TO litellm_app', schemaname, viewname)
FROM pg_views WHERE viewowner = :'admin_role'
  AND schemaname NOT LIKE 'pg\_%' AND schemaname <> 'information_schema'\gexec
SQL

echo "Rôles applicatifs à jour : investia_app (base investia), litellm_app (base litellm), sans SUPERUSER."
