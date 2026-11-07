#!/usr/bin/env bash
# Sauvegarde quotidienne des bases PostgreSQL (D52) : pg_dump au format « custom », rotation en jours.
# Les sauvegardes restent sur le VPS (volume Docker `backups`) : rien n'est envoyé ailleurs.
#
# Usage : backup.sh once   -> une sauvegarde puis sortie (code non nul en cas d'échec)
#         backup.sh        -> boucle : une sauvegarde par jour à BACKUP_HOUR_UTC
# Connexion : variables PGHOST, PGUSER, PGPASSWORD (jamais écrites dans un fichier).
set -euo pipefail
# Dumps lisibles par leur seul propriétaire : ils contiennent la base d'Authelia (secrets TOTP chiffrés).
umask 077

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
DATABASES="${DATABASES:-investia litellm authelia}"
BACKUP_HOUR_UTC="${BACKUP_HOUR_UTC:-3}"
MAX_AGE_BEFORE_STARTUP_BACKUP_SECONDS=$((20 * 3600))

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

validate_settings() {
  [[ "$RETENTION_DAYS" =~ ^[1-9][0-9]*$ ]] || { log "ERREUR RETENTION_DAYS invalide : $RETENTION_DAYS"; return 1; }
  [[ "$BACKUP_HOUR_UTC" =~ ^([0-9]|1[0-9]|2[0-3])$ ]] || { log "ERREUR BACKUP_HOUR_UTC invalide : $BACKUP_HOUR_UTC"; return 1; }
  [[ -n "${PGHOST:-}" && -n "${PGUSER:-}" ]] || { log "ERREUR PGHOST et PGUSER sont requis"; return 1; }
  local database
  for database in $DATABASES; do
    # Le nom sert aussi de nom de fichier : on n'accepte que des caractères simples.
    [[ "$database" =~ ^[A-Za-z0-9_]+$ ]] || { log "ERREUR nom de base invalide : $database"; return 1; }
  done
}

dump_one_database() {
  local database="$1" stamp="$2"
  local final_file="$BACKUP_DIR/$database-$stamp.dump"
  local partial_file="$final_file.partial"

  if ! pg_dump --format=custom --dbname="$database" --file="$partial_file"; then
    rm -f "$partial_file"
    log "ERREUR pg_dump a échoué pour la base $database"
    return 1
  fi
  # Un dump illisible serait une fausse sécurité : on vérifie qu'il se relit.
  if ! pg_restore --list "$partial_file" >/dev/null; then
    rm -f "$partial_file"
    log "ERREUR le dump de $database est illisible"
    return 1
  fi
  if ! mv "$partial_file" "$final_file"; then
    log "ERREUR impossible de finaliser $(basename "$final_file")"
    return 1
  fi
  log "OK $database -> $(basename "$final_file")"
}

run_backup() {
  local stamp database
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  # Chaque commande qui peut échouer est testée explicitement : en mode boucle, run_backup est appelée
  # avec « || », et bash ignore alors `set -e` à l'intérieur de la fonction.
  if ! mkdir -p "$BACKUP_DIR"; then
    log "ERREUR impossible de créer $BACKUP_DIR"
    return 1
  fi

  for database in $DATABASES; do
    dump_one_database "$database" "$stamp" || return 1
  done

  # Rotation seulement après une sauvegarde 100 % réussie : un échec ne doit jamais
  # faire disparaître les anciennes sauvegardes. On supprime ce qui a plus de N x 24 h.
  local removed_files
  if ! removed_files="$(find "$BACKUP_DIR" -maxdepth 1 -name '*.dump' \
      -mmin +"$((RETENTION_DAYS * 24 * 60))" -print -delete)"; then
    log "ERREUR la rotation des anciennes sauvegardes a échoué"
    return 1
  fi
  if [ -n "$removed_files" ]; then
    while read -r removed_file; do log "Rotation : supprimé $(basename "$removed_file")"; done <<<"$removed_files"
  fi
  find "$BACKUP_DIR" -maxdepth 1 -name '*.partial' -mtime +1 -delete \
    || log "AVERTISSEMENT nettoyage des fichiers .partial impossible"
  if ! date -u +%Y-%m-%dT%H:%M:%SZ > "$BACKUP_DIR/last_success"; then
    log "ERREUR impossible d'écrire last_success"
    return 1
  fi
  log "Sauvegarde terminée"
}

seconds_until_next_run() {
  local now next
  now="$(date -u +%s)"
  next="$(date -u -d "today ${BACKUP_HOUR_UTC}:00:00" +%s)"
  if [ "$next" -le "$now" ]; then next=$((next + 86400)); fi
  echo $((next - now))
}

last_success_is_recent() {
  local last_success_file="$BACKUP_DIR/last_success"
  [ -s "$last_success_file" ] || return 1
  local age_seconds=$(( $(date -u +%s) - $(date -u -r "$last_success_file" +%s) ))
  [ "$age_seconds" -lt "$MAX_AGE_BEFORE_STARTUP_BACKUP_SECONDS" ]
}

main() {
  validate_settings

  if [ "${1:-}" = "once" ]; then
    run_backup
    return
  fi

  # Au démarrage : une sauvegarde tout de suite si la dernière est trop ancienne ou absente,
  # ce qui vérifie la connexion dès le premier déploiement.
  if ! last_success_is_recent; then
    run_backup || log "ÉCHEC de la sauvegarde de démarrage : nouvel essai à la prochaine heure prévue"
  fi
  while true; do
    local wait_seconds
    wait_seconds="$(seconds_until_next_run)"
    log "Prochaine sauvegarde dans ${wait_seconds}s (${BACKUP_HOUR_UTC}h UTC)"
    sleep "$wait_seconds"
    run_backup || log "ÉCHEC de la sauvegarde : nouvel essai demain (le healthcheck passera en unhealthy)"
  done
}

main "$@"
