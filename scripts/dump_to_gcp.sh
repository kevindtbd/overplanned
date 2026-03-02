#!/bin/bash
# Dump overplanned local postgres to GCP Cloud SQL.
# Requires: Cloud SQL proxy running on port 25432
# Cloud SQL instance: overplanned (confirmed via gcloud sql instances list)
#
# Usage: ./scripts/dump_to_gcp.sh
#
# Pre-requisites:
#   1. GCP Cloud SQL proxy must be running:
#      ./cloud-sql-proxy overplanned:us-west1:overplanned --port 25432 &
#   2. DATABASE_URL_TCP must be set in .env (cloud sql TCP address)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP=$(date +%Y%m%dT%H%M%S)
DUMP_FILE="/tmp/overplanned_dump_${TIMESTAMP}.sql.gz"

echo "================================================"
echo "  DUMP TO GCP CLOUD SQL"
echo "================================================"
echo ""

# Check Cloud SQL proxy is running
if ! nc -z localhost 25432 2>/dev/null; then
    echo "ERROR: Cloud SQL proxy not detected on port 25432."
    echo "Start it first:"
    echo "  ./cloud-sql-proxy overplanned:us-west1:overplanned --port 25432 &"
    exit 1
fi

echo "Cloud SQL proxy detected on port 25432."
echo ""

# Step 1: Dump from local docker (via container pg_dump to match PG16)
echo "[1/3] Dumping local DB..."
DOCKER_HOST=unix:///var/run/docker.sock DOCKER_API_VERSION=1.42 \
    docker exec overplanned-postgres \
    pg_dump -U overplanned -d overplanned --no-owner --no-acl \
    | gzip > "$DUMP_FILE"

SIZE=$(du -sh "$DUMP_FILE" | cut -f1)
echo "  Local dump: $DUMP_FILE ($SIZE)"
echo ""

# Step 2: Load credentials from .env
GCP_DB_URL=$(grep DATABASE_URL_TCP .env 2>/dev/null | cut -d= -f2- | tr -d '"' || true)
if [ -z "$GCP_DB_URL" ]; then
    # Fall back to parsing from Secret Manager env
    echo "DATABASE_URL_TCP not in .env — trying Secret Manager..."
    GCP_DB_URL=$(gcloud secrets versions access latest --secret=DATABASE_URL_TCP 2>/dev/null || true)
fi

if [ -z "$GCP_DB_URL" ]; then
    echo "ERROR: Could not find GCP DATABASE_URL_TCP"
    echo "Set DATABASE_URL_TCP=postgresql://user:pass@localhost:25432/overplanned in .env"
    exit 1
fi

echo "[2/3] Restoring to GCP Cloud SQL..."
echo "  Target: $GCP_DB_URL"
echo ""

gunzip -c "$DUMP_FILE" | psql "$GCP_DB_URL" --no-password

echo ""
echo "[3/3] Verifying restore..."
TABLE_COUNT=$(psql "$GCP_DB_URL" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" --no-password 2>/dev/null | tr -d ' ')
NODE_COUNT=$(psql "$GCP_DB_URL" -t -c "SELECT COUNT(*) FROM activity_nodes;" --no-password 2>/dev/null | tr -d ' ' || echo "0")

echo "  Tables: $TABLE_COUNT"
echo "  activity_nodes: $NODE_COUNT"
echo ""
echo "Cleaning up temp file..."
rm -f "$DUMP_FILE"
echo "Done!"
