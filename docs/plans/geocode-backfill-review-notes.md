# Geocode Backfill — Plan Review Notes

## Issues Found & Resolved

### 1. Cross-city geocoding mismatch (CRITICAL)
**Issue**: Generic venue names like "Thai Pepper" could geocode to a different city (Seattle instead of Tacoma).
**Fix**: Add bbox validation — reject Google Places results whose lat/lng falls outside the city's bounding box. Keep bbox center coords if validation fails.

### 2. Double geocoding on fresh runs (MODERATE)
**Issue**: `_geocode_venues` runs during LLM fallback creation AND the new backfill step would run right after — double API calls.
**Fix**: Remove inline geocoding from `run_llm_fallback`. All geocoding happens in the dedicated backfill step only. Single code path.

### 3. Checkpoint compatibility (LOW)
**Issue**: New `PipelineStep.GEOCODE_BACKFILL` enum not present in existing progress JSON files.
**Fix**: `_should_run_step` already returns True for missing steps. Old checkpoints auto-trigger the new step on next run. No migration needed.

### 4. Scope — hardcoded cities (NON-ISSUE)
Bend's nodes have real coords, so the bbox-center detection query returns 0 matches. No special casing needed. Run on all cities uniformly.

## Updated Design Decisions

- Bbox validation on geocode results (reject out-of-city responses)
- Single geocoding code path (backfill step only, not inline during creation)
- No checkpoint migration needed (auto-handled by existing logic)
- Runs on all cities uniformly (detection query self-filters)

## No Remaining Gaps

Plan is ready for agent review and implementation.
