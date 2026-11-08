#!/usr/bin/env bash
# Mise à jour standard du VPS Investia : pull main + rebuild + up + état.
# Toujours la même procédure (voir docs/mise-a-jour-vps-2026-11-07.md).
# Usage : bash ~/investia/deploy/update.sh
set -euo pipefail

cd "$(dirname "$0")/.."          # racine du repo (~/investia)
git checkout main
git pull --ff-only origin main
echo "→ main = $(git log --oneline -1)"

cd deploy
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ../.env"
$COMPOSE build backend dashboard
$COMPOSE up -d
$COMPOSE ps
