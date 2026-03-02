#!/bin/bash
# Safe docker compose down — ALWAYS backs up postgres first.
# Use this instead of bare `docker compose down` or `docker stop`.
#
# Usage: ./scripts/docker_down_safe.sh [docker compose down args...]
# Example: ./scripts/docker_down_safe.sh -v  (removes volumes too)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="$SCRIPT_DIR/backup_db.sh"
BACKUP_DIR="/home/pogchamp/Desktop/overplanned/data/backups"

echo "================================================"
echo "  SAFE DOCKER DOWN — backing up first"
echo "================================================"

# Check if postgres container is running
if DOCKER_API_VERSION=1.42 docker ps --format '{{.Names}}' 2>/dev/null | grep -q "overplanned-postgres"; then
    echo "Postgres is running — creating backup..."
    bash "$BACKUP_SCRIPT" "$BACKUP_DIR"
    echo "Backup complete."
else
    echo "Postgres container not running — skipping backup."
fi

echo ""
echo "Bringing down containers..."
DOCKER_API_VERSION=1.42 docker compose down "$@"
echo "Done."
