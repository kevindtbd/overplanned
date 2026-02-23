# Backfill Enrichment — Plan Review Notes

**Reviewed:** 2026-02-22
**Plan:** docs/plans/2026-02-22-backfill-enrichment-design.md

---

## Critical Issues Found & Resolved

### 1. Entity Resolution Strategy Mismatch
**Issue:** Plan said "Qdrant fuzzy search scoped to city namespace" but existing entity resolution uses a 4-tier Postgres cascade (external ID -> geocode -> fuzzy name -> content hash). Backfill venues lack external IDs and lat/lng, so only pg_trgm fuzzy name matching (tier 3) is viable.
**Resolution:** Use pg_trgm fuzzy name matching scoped by city + category. Extract from existing `EntityResolver`. Threshold 0.7 (existing calibration). No Qdrant embedding step needed.
**Update required:** Change Stage 3 from Qdrant to Postgres pg_trgm.

### 2. Async Pipeline Reliability on Cloud Run
**Issue:** FastAPI BackgroundTasks on Cloud Run can be killed when container scales down after HTTP response returns.
**Resolution:** BackgroundTasks is acceptable for beta scale. Cloud Run min-instances keeps containers warm. Document limitation. Cloud Tasks is the upgrade path if pipeline drops become measurable.
**No plan change needed** — just document the limitation.

### 3. Onboarding Step Context
**Issue:** Backfill step between fork and destination is a context shift — user chose "Plan a trip" then immediately sees "Where have you traveled?"
**Resolution:** Frame backfill as feeding into the upcoming trip: "First, tell us about a recent trip so we can personalize your itinerary." Ties data collection to immediate value.
**Update required:** Add framing copy to the onboarding step spec.

### 4. API Split Confirmed
**Decision:** FastAPI handles ingestion pipeline (LLM + entity resolution + anomaly checks). Next.js handles auth'd CRUD + enrichment routes. Both share Postgres. This matches existing architecture patterns.

### 5. Quality Gate — AND Logic Confirmed
**Decision:** Rejection requires BOTH <3 venues AND no temporal context. A 2-venue submission with dates is accepted. A single venue with no dates is rejected.

---

## Gaps Identified (Not Blockers)

### A. FastAPI → Prisma Schema Coordination
FastAPI writes directly to Postgres via asyncpg, not Prisma. New models (BackfillTrip, BackfillVenue, etc.) need to exist in both:
- Prisma schema (for Next.js reads/writes)
- Raw SQL or Prisma-py generated models (for FastAPI writes)
The project already uses `generator python` in schema.prisma for prisma-client-py. Ensure pipeline uses prisma-client-py or raw asyncpg — not a mix.

### B. Unresolved Venue Frequency Tracking
Plan notes unresolved venues "surface gaps in world knowledge" but doesn't specify how. Consider: a simple counter table or aggregation query on `BackfillVenue WHERE isResolved = false GROUP BY extractedName, city ORDER BY count DESC`. Not a V2 build item, but the data is there for ops queries.

### C. Photo Storage Cleanup
Plan has DELETE endpoint for photos but doesn't specify GCS object deletion. When a BackfillPhoto row is deleted, the GCS object must also be deleted (or orphaned objects accumulate). Add GCS delete to the photo delete endpoint.

### D. Rate Limiting on Backfill Submit
No rate limit specified for POST /api/backfill/submit. Each submission triggers 2-3 LLM calls (Sonnet extraction + Haiku classification + Haiku validation). A user spamming submissions could burn API credits. Add reasonable rate limit (e.g., 10 submissions per user per hour).

---

## Suggested Improvements

1. **Batch extraction for multiple trips in onboarding** — if user submits 3 trips during onboarding, pipeline should batch-process rather than 3 separate async runs. Lower latency, fewer LLM calls.
2. **Idempotency key on submit** — prevent double-submission on slow networks. Hash of (userId + rawSubmission text) as dedup key.
3. **pg_trgm threshold for backfill** — existing EntityResolver uses 0.7. For backfill, consider raising to 0.75 or 0.80 since extracted names may be less precise than scraped names. This reduces false matches at the cost of more unresolved venues (acceptable — unresolved is safe, false match is not).
