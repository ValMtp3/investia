#!/usr/bin/env bash
# Restaure un dump dans une base PostgreSQL EXISTANTE (D52).
# Usage : restore.sh /backups/investia-20261105T030000Z.dump nom_de_la_base_cible
# Connexion : PGHOST, PGUSER, PGPASSWORD.
#
# ⚠️ Les objets de la base cible sont remplacés (--clean). Pour tester une sauvegarde sans risque,
# restaurer dans une base vide (ex. `createdb restore_check`), jamais directement dans la vraie.
set -euo pipefail

dump_file="${1:-}"
target_database="${2:-}"

if [ -z "$dump_file" ] || [ -z "$target_database" ]; then
  echo "Usage : restore.sh <fichier.dump> <base_cible>" >&2
  exit 2
fi
if [ ! -s "$dump_file" ]; then
  echo "ERREUR fichier introuvable ou vide : $dump_file" >&2
  exit 2
fi
if [[ ! "$target_database" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "ERREUR nom de base invalide : $target_database" >&2
  exit 2
fi

pg_restore --dbname="$target_database" --clean --if-exists --exit-on-error "$dump_file"
echo "Restauration de $(basename "$dump_file") dans $target_database terminée."
