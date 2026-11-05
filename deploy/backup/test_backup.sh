#!/usr/bin/env bash
# Test de bout en bout des sauvegardes (D52) sur un PostgreSQL jetable :
# sauvegarde, rotation, restauration réelle, et refus de supprimer les anciens fichiers en cas d'échec.
# Usage : cd deploy && bash backup/test_backup.sh   (nécessite Docker)
set -u

IMAGE="pgvector/pgvector:pg17"
HERE="$(cd "$(dirname "$0")" && pwd)"
SUFFIX="$$"
NET="bktest-net-$SUFFIX"
PG="bktest-pg-$SUFFIX"
VOL="bktest-vol-$SUFFIX"
PG_PASSWORD="$(openssl rand -hex 12)"
AUTHELIA_PASSWORD="$(openssl rand -hex 12)"
FAILURES=0

cleanup() {
  docker rm -f "$PG" >/dev/null 2>&1
  docker volume rm "$VOL" >/dev/null 2>&1
  docker network rm "$NET" >/dev/null 2>&1
}
trap cleanup EXIT

check() { # check "description" commande...
  local description="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "  OK    $description"; else echo "  ECHEC $description"; FAILURES=$((FAILURES + 1)); fi
}

run_in_backup_container() { # arguments passés au conteneur (après l'image)
  docker run --rm --network "$NET" -v "$HERE:/scripts:ro" -v "$VOL:/backups" \
    -e PGHOST="$PG" -e PGUSER=investia -e PGPASSWORD="${TEST_PGPASSWORD:-$PG_PASSWORD}" \
    "$IMAGE" "$@"
}

psql_pg() { docker exec "$PG" psql -U investia -v ON_ERROR_STOP=1 -tA "$@"; }

echo "== Préparation : PostgreSQL jetable avec le vrai script d'init"
docker network create "$NET" >/dev/null
docker volume create "$VOL" >/dev/null
docker run -d --name "$PG" --network "$NET" -e POSTGRES_USER=investia -e POSTGRES_PASSWORD="$PG_PASSWORD" \
  -e AUTHELIA_DB_PASSWORD="$AUTHELIA_PASSWORD" -v "$HERE/../postgres/init:/docker-entrypoint-initdb.d:ro" "$IMAGE" >/dev/null
until psql_pg -d postgres -c "select 1 from pg_database where datname='authelia'" 2>/dev/null | grep -q 1; do sleep 1; done
sleep 2
psql_pg -d investia -c "create table positions(symbol text); insert into positions values ('AAPL'),('SAP.DE'),('BTC');" >/dev/null

echo "== 1) Sauvegarde"
run_in_backup_container bash /scripts/backup.sh once
check "script de sauvegarde terminé avec succès (code 0)" test $? -eq 0
for database in investia litellm authelia; do
  check "un fichier .dump existe pour $database" bash -c "docker run --rm -v $VOL:/backups $IMAGE sh -c 'ls /backups/$database-*.dump'"
done
check "le fichier de dernière réussite existe" bash -c "docker run --rm -v $VOL:/backups $IMAGE test -s /backups/last_success"

echo "== 2) Rotation (7 jours) : un vieux fichier disparaît, un récent reste"
docker run --rm -v "$VOL:/backups" "$IMAGE" sh -c "touch -d '10 days ago' /backups/investia-vieux.dump && touch /backups/investia-recent.dump"
run_in_backup_container bash /scripts/backup.sh once
check "le fichier de 10 jours est supprimé" bash -c "! docker run --rm -v $VOL:/backups $IMAGE test -e /backups/investia-vieux.dump"
check "le fichier récent est gardé" bash -c "docker run --rm -v $VOL:/backups $IMAGE test -e /backups/investia-recent.dump"

echo "== 3) Restauration réelle dans une nouvelle base"
psql_pg -d postgres -c "create database restore_check" >/dev/null
LATEST="$(docker run --rm -v "$VOL:/backups" "$IMAGE" sh -c 'ls -1 /backups/investia-2*.dump | tail -1' | tr -d '\r')"
run_in_backup_container bash /scripts/restore.sh "$LATEST" restore_check
check "restore.sh terminé avec succès" test $? -eq 0
COUNT="$(psql_pg -d restore_check -c 'select count(*) from positions' 2>/dev/null)"
check "les 3 lignes sont revenues (obtenu : ${COUNT:-rien})" test "${COUNT:-0}" = "3"

echo "== 4) Échec : mauvais mot de passe => code non nul et anciens fichiers intacts"
docker run --rm -v "$VOL:/backups" "$IMAGE" sh -c "touch -d '10 days ago' /backups/investia-protege.dump"
TEST_PGPASSWORD="mauvais" run_in_backup_container bash /scripts/backup.sh once >/dev/null 2>&1
check "code de sortie non nul" test $? -ne 0
check "le vieux fichier n'est PAS supprimé après un échec" bash -c "docker run --rm -v $VOL:/backups $IMAGE test -e /backups/investia-protege.dump"

echo
if [ "$FAILURES" -eq 0 ]; then echo "TOUS LES TESTS PASSENT"; else echo "$FAILURES TEST(S) EN ECHEC"; exit 1; fi
