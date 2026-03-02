#!/bin/bash
# Backup overplanned postgres DB to timestamped gzip file.
# Uses pg_dump inside the container (avoids version mismatch with PG16 server vs PG15 local).
# Run BEFORE any Docker operations, migrations, or destructive ops.
#
# Usage: ./scripts/backup_db.sh [output_dir]

set -euo pipefail

OUTPUT_DIR="${1:-/home/pogchamp/Desktop/overplanned/data/backups}"
TIMESTAMP=$(date +%Y%m%dT%H%M%S)
BACKUP_FILE="${OUTPUT_DIR}/overplanned_postgres_${TIMESTAMP}.sql.gz"

mkdir -p "$OUTPUT_DIR"

echo "Backing up overplanned postgres DB -> $BACKUP_FILE"

DOCKER_HOST=unix:///var/run/docker.sock DOCKER_API_VERSION=1.42 \
  docker exec overplanned-postgres \
  pg_dump -U overplanned -d overplanned \
  | gzip > "$BACKUP_FILE"

SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
echo "Done. Backup: $BACKUP_FILE ($SIZE)"
echo ""
echo "To restore:"
echo "  gunzip -c $BACKUP_FILE | PGPASSWORD=localdev123 psql -h localhost -p 15432 -U overplanned -d overplanned"
