# Canary Validation Design — 2026-03-01

## Problem

We lost our DB to a Docker migration mishap and are rebuilding. Before running 44+ cities
through the 10-step pipeline, we need to confirm infrastructure is healthy, fix known broken
things, and validate end-to-end on one city before scaling.

## Sequence (must execute in order)

1. Fix known issues
2. Build preflight_check.py
3. Wipe Bend + run clean canary
4. Manual spot-check (human eyes on 10 nodes)
5. Green-light full batch only after sign-off

---

## Step 1: Fix Known Issues

### 1a. Missing vibe_tags (12 slugs)
`rule_inference` references these slugs but they don't exist in the DB.
Silently skips tag assignments for every city until fixed.

Missing: `low-key`, `lively`, `high-energy`, `late-night`, `physical`,
`instagram-worthy`, `historical`, `unique`, `educational`, `slow-paced`, `quiet`, `relaxing`

Fix: INSERT with `ON CONFLICT (slug) DO NOTHING`

### 1b. pg_trgm
Already installed. Verify with `SELECT similarity('a','a')`. Bend's entity_resolution
failure was from before installation — clean re-run should pass.

### 1c. model_registry
`llm_fallback` checks model_registry for an active model. Verify at least one
`status IN ('production','staging')` entry exists.

### 1d. Qdrant collection
`qdrant_sync` needs the `activity_nodes` collection. Verify it exists and has correct
vector config. If missing, first sync will autocreate — but verify the config is right.

---

## Step 2: Preflight Script

**File:** `scripts/preflight_check.py`

**Interface:**
```bash
python3 scripts/preflight_check.py           # global infra checks only
python3 scripts/preflight_check.py --city bend  # + city-specific Parquet check
```

**8 checks (hard-fail on any):**
1. `ANTHROPIC_API_KEY` set and non-empty
2. `DATABASE_URL` set
3. Postgres connectivity + `activity_nodes` table exists
4. `pg_trgm` — `SELECT similarity('a','a')` executes
5. `vibe_tags` — ≥ 40 active tags AND all 12 required rule_inference slugs present
6. `model_registry` — at least one active entry
7. Qdrant — `GET /healthz` returns 200
8. (if --city) Arctic Shift Parquet — at least one `.parquet` file for the city

Exit 0 = all green. Exit 1 = something failed. Batch script gates on this.

---

## Step 3: Bend Canary — Clean Run

**Wipe:**
```bash
rm data/seed_progress/bend.json
# DELETE FROM activity_nodes WHERE city = 'Bend'
# DELETE Qdrant points for city=Bend
```

**Run synchronously (not backgrounded):**
```bash
ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY .env | cut -d= -f2) \
  python3 -m services.api.pipeline.city_seeder bend
```

**Automated pass criteria:**
- `status = completed` in seed_progress/bend.json
- All 10 steps = `completed`
- `activity_nodes` count ≥ 40 for city=Bend
- ≥ 5 distinct categories
- ≥ 50% of nodes have vibe tags assigned
- Qdrant node count matches DB count (±1)

---

## Step 4: Manual Spot-Check

```bash
python3 scripts/canary_spot_check.py --city bend --sample 10
```

Prints readable table: name | category | city | vibes | geocoded

Reviewing for:
- Real Bend place names (no extraction artifacts)
- city = "Bend" on all rows (no cross-contamination)
- Vibes make sense for the venue
- Geocoded = yes on most rows

**No full batch until human sign-off.**

---

## Step 5: Full Batch

After sign-off:
- Run `scripts/backup_db.sh` + `scripts/backup_qdrant.sh` first
- Run `scripts/preflight_check.py` — must pass
- Launch 44-city batch with explicit `ANTHROPIC_API_KEY`
- Tail first 2 cities live, then background

---

## Backup Infrastructure

### `scripts/backup_qdrant.sh`
- `POST /collections/activity_nodes/snapshots` → snapshot file on disk
- Push snapshot to GCS bucket
- Verify snapshot age < 24h check in preflight

### `scripts/backup_db.sh` (already exists)
- `pg_dump` via docker exec (avoids PG15/16 version mismatch)
- Gzip to `data/backups/`
