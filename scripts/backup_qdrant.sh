#!/bin/bash
# Snapshot Qdrant collection and push to GCS
# Usage: ./scripts/backup_qdrant.sh [gcs-bucket-name]
#
# Requires: QDRANT_API_KEY in .env or env, GCS bucket with write access
# Snapshots are stored locally under data/backups/qdrant/ and uploaded to GCS

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COLLECTION="activity_nodes"
QDRANT_URL="${QDRANT_URL:-http://127.0.0.1:6333}"
GCS_BUCKET="${1:-}"

# Load env vars from .env if not already set
if [ -f "$PROJECT_ROOT/.env" ]; then
  export $(grep -E '^(QDRANT_API_KEY|QDRANT_URL|GCS_BUCKET)=' "$PROJECT_ROOT/.env" | xargs) 2>/dev/null || true
fi

QDRANT_API_KEY="${QDRANT_API_KEY:-localdev123}"
GCS_BUCKET="${GCS_BUCKET:-${GCS_BUCKET:-}}"

BACKUP_DIR="$PROJECT_ROOT/data/backups/qdrant"
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%dT%H%M%S)

echo "==> Triggering Qdrant snapshot for collection: $COLLECTION"

# POST to create snapshot
SNAPSHOT_RESPONSE=$(curl -s -X POST \
  -H "api-key: $QDRANT_API_KEY" \
  "$QDRANT_URL/collections/$COLLECTION/snapshots")

SNAPSHOT_NAME=$(echo "$SNAPSHOT_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
result = data.get('result', {})
name = result.get('name', '')
print(name)
" 2>/dev/null || echo "")

if [ -z "$SNAPSHOT_NAME" ]; then
  echo "ERROR: Failed to create snapshot. Response: $SNAPSHOT_RESPONSE"
  exit 1
fi

echo "==> Snapshot created: $SNAPSHOT_NAME"

# Download snapshot to local disk
LOCAL_FILE="$BACKUP_DIR/qdrant_${COLLECTION}_${TIMESTAMP}.snapshot"
echo "==> Downloading snapshot to $LOCAL_FILE"

curl -s \
  -H "api-key: $QDRANT_API_KEY" \
  "$QDRANT_URL/collections/$COLLECTION/snapshots/$SNAPSHOT_NAME" \
  -o "$LOCAL_FILE"

SIZE=$(du -sh "$LOCAL_FILE" | cut -f1)
echo "==> Saved locally: $LOCAL_FILE ($SIZE)"

# Push to GCS if bucket is configured
if [ -n "$GCS_BUCKET" ]; then
  GCS_PATH="gs://$GCS_BUCKET/qdrant-snapshots/qdrant_${COLLECTION}_${TIMESTAMP}.snapshot"
  echo "==> Uploading to $GCS_PATH"
  gsutil cp "$LOCAL_FILE" "$GCS_PATH"
  echo "==> GCS upload complete"
else
  echo "==> No GCS bucket configured — snapshot stored locally only"
  echo "    To enable GCS: add GCS_BUCKET=your-bucket to .env"
fi

# Keep last 5 local snapshots, delete older ones
echo "==> Pruning old local snapshots (keeping 5)"
ls -t "$BACKUP_DIR"/qdrant_${COLLECTION}_*.snapshot 2>/dev/null | tail -n +6 | xargs -r rm -f

echo "==> Qdrant backup complete"
