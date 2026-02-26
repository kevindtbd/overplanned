# Geocode Backfill Design

## Problem

LLM fallback seeder creates ActivityNodes with city bbox center coordinates (lat/lng are NOT NULL in Prisma). This causes:
1. Entity resolution over-merging (all nodes at same point)
2. No neighborhood assignment
3. Proximity-based features are useless

The `ST_Distance > 1.0` guard in entity resolution prevents over-merging, but nodes still lack real coordinates.

## Solution

Add `geocode_backfill()` to `services/api/pipeline/llm_fallback_seeder.py` that:
1. Finds nodes at bbox center (within 200m, no `googlePlaceId`)
2. Calls Google Places Text Search API for real lat/lng
3. Updates nodes in-place

## Architecture

### Function: `geocode_backfill(pool, city_slug, *, google_places_key=None, limit=100)`

**Detection query**: Nodes where `ST_Distance(node_coords, bbox_center) < 200` AND `googlePlaceId IS NULL`. The 200m tolerance catches all LLM fallback nodes (at exact center) while excluding legitimately downtown venues.

**Geocoding**: Reuses existing Google Places Text Search pattern — query `"{venue_name}, {city_name}"`, extract lat/lng/address/placeId from first result.

**DB update**: `UPDATE activity_nodes SET latitude, longitude, address, "googlePlaceId", "contentHash" WHERE id = $1`. Recomputes `contentHash` (which includes lat/lng) to keep Tier 4 entity resolution valid. No creates, no deletes.

**Stats**: `GeocodeBackfillStats(nodes_found, nodes_geocoded, nodes_failed, nodes_skipped)`

### Pipeline Integration

New step 2.5 in city_seeder.py between LLM fallback and entity resolution:
- `PipelineStep.GEOCODE_BACKFILL` enum value
- Skips if no `GOOGLE_PLACES_API_KEY` env var
- Checkpoint/resume via standard `_should_run_step` / `_mark_step_done`
- Total steps: 7 → 8

### Cost Control

- Default limit: 100 nodes per run (Tacoma has ~82, fits in one run)
- Override via `--limit` CLI flag
- Google Places Text Search: ~$5/1000 requests
- Tacoma backfill estimate: ~$0.41

### Error Handling

- No API key → skip all, return immediately
- 429/5xx → exponential backoff, 3 retries, then skip node
- Wrong city returned → **bbox validation rejects** results outside city bounding box, keeps bbox center coords
- NaN/Infinity/out-of-range → `_validate_geocode_result()` rejects before DB write
- Inter-request delay: `asyncio.sleep(0.15)` between API calls (~6.6 QPS, prevents 429 storms)
- Idempotent: skips nodes with existing `googlePlaceId`
- Crash-safe: partially geocoded runs resume cleanly

### CLI

```bash
python3 -m services.api.pipeline.llm_fallback_seeder --geocode-backfill tacoma --limit 100
```

## Testing

Unit tests only (mock httpx, no real API calls):

**P0 — Must have:**
1. Detection query finds bbox center nodes (correct ST_Distance + IS NULL + city filter)
2. Bbox validation rejects out-of-city geocode results
3. Bbox validation accepts in-city geocode results
4. Skips already-geocoded nodes (googlePlaceId IS NOT NULL)
5. No API key returns immediately with skip stats
6. API returns empty places array — node skipped gracefully
7. Respects limit cap
8. Verifies DB UPDATE query has correct columns (lat, lng, address, googlePlaceId, contentHash)
9. `_validate_geocode_result` rejects NaN, Infinity, out-of-range coords

**P1 — Should have:**
10. 429/5xx retry with backoff, then skip
11. Node-level failure does not abort remaining nodes
12. GeocodeBackfillStats defaults
13. GEOCODE_BACKFILL step ordering in STEP_ORDER
14. Old progress JSON without geocode step triggers backfill

## Decisions

- **Bbox center proximity over boolean flag**: No schema change needed, works on existing data
- **In llm_fallback_seeder.py over separate file**: Keeps Google Places API logic together
- **Per-city cap over budget cap**: Simpler, predictable, sufficient for current scale
- **200m detection radius**: Generous enough to catch all fallback nodes, tight enough to skip real venues
- **Bbox validation on geocode results**: Reject lat/lng outside city bounding box (prevents cross-city mismatches like "Thai Pepper" geocoding to Seattle instead of Tacoma)
- **Single geocoding code path with CLI fallback**: Keep inline `_geocode_venues` in `run_llm_fallback` with `skip_geocode=False` param. `city_seeder.py` passes `skip_geocode=True` since it runs the dedicated backfill step. Standalone CLI path still geocodes inline.
- **No checkpoint migration**: `_should_run_step` returns True for missing steps. Old progress JSONs auto-trigger backfill on next run.
- **Runs on all cities uniformly**: Hardcoded cities (Bend) have real coords → 0 nodes match bbox-center query → 0 API calls. No special casing.

## Agent Review Findings (incorporated)

**Architect:**
- Content hash invalidation: UPDATE must recompute `contentHash` (includes lat/lng) → ADDED
- CLI contract: keep inline geocode with `skip_geocode` param → CHANGED decision
- PipelineStep enum + STEP_ORDER must be synchronized → noted
- Detection query needs city filter → ADDED to detection query

**Security:**
- `_validate_geocode_result()` helper: reject NaN, Infinity, out-of-range, wrong types → ADDED
- Inter-request delay 150ms → ADDED
- Bbox validation is the primary defense → already designed
- Address length cap (500 chars), placeId length cap (200 chars) → ADDED to validation

**Test Engineer:**
- Original 5 tests = ~25% coverage. Expanded to 14 tests (9 P0 + 5 P1) → UPDATED
- Bbox validation tests are highest priority gap → ADDED as P0 items 2-3
- NaN validation test → ADDED as P0 item 9

## Review Notes

See `docs/plans/geocode-backfill-review-notes.md` for full deepen-plan analysis.
