# User Backfill & Trip Enrichment — V2 Design

**Date:** 2026-02-22
**Source:** Internal Product & ML doc (backfill-enrichment.docx)
**Status:** Reviewed (deepener + architect + security + test-engineer)

---

## Scope

### Building
- Backfill ingestion pipeline (free-form text -> LLM extraction -> LLM validation -> entity resolution -> anomaly checks -> signal storage)
- Travel diary section on dashboard + diary detail view per backfilled trip
- Onboarding backfill step (skippable, pre-trip-planning)
- Trip enrichment surfaces: per-venue photo upload (EXIF extraction), "would return" toggle, free-text trip notes, context tags (Solo/Partner/Family/Friends/Work)
- Delta logging tables for future ML (PersonaDelta — schema + write path only)
- Earn-out flag logic on BackfillSignal (based on completed in-app trip count)

### NOT Building
- Structured import parsers (TripIt, Google Takeout) — architecture supports them, not wired
- Scene classification / vision models on photos
- Persona scoring from backfill signals (columns exist, ML reads deferred)
- Third tower / EM algorithm
- Email forwarding ingestion
- Ranking model integration (backfill never touches ranking — no counterfactual context)

---

## Data Model

### New Models

**`BackfillTrip`** — diary entry container (separate from Trip)
- `id`, `userId` (FK → User, cascade delete), `city`, `country`, `startDate?`, `endDate?`
- `confidenceTier` (tier_2/tier_3/tier_4)
- `source` ("freeform" — extensible for future structured parsers)
- `rawSubmission` (original text, max 10,000 chars — validated server-side)
- `contextTag?` (solo/partner/family/friends/work)
- `tripNote?` (free-text "anything you'd do differently")
- `status` (processing/complete/rejected/quarantined/archived)
- `rejectionReason?`
- `createdAt`, `updatedAt`
- Prisma relation: `user User @relation(fields: [userId], references: [id], onDelete: Cascade)`
- User model gets: `backfillTrips BackfillTrip[]`

**`BackfillVenue`** — extracted venue within a backfill trip
- `id`, `backfillTripId` (FK → BackfillTrip, cascade delete), `activityNodeId?` (FK → ActivityNode, nullable)
- `extractedName`, `extractedCategory?`, `extractedDate?`, `extractedSentiment?`
- `latitude?`, `longitude?`
- `resolutionScore?` (0-1 from pg_trgm match)
- `isResolved`, `isQuarantined`, `quarantineReason?`
- `wouldReturn?` (boolean, null = not answered)
- `createdAt`, `updatedAt`

**`BackfillPhoto`** — per-venue photo attachment
- `id`, `backfillVenueId` (FK → BackfillVenue, cascade delete)
- `gcsPath`, `originalFilename`, `mimeType`
- `exifLat?` (validated: -90 to 90), `exifLng?` (validated: -180 to 180), `exifTimestamp?`
- `createdAt`
- Note: userId derived from venue → trip → user chain (no redundant FK)

**`BackfillSignal`** — weighted persona signals (write-only, ML reads deferred)
- `id`, `userId` (FK → User), `backfillTripId` (FK → BackfillTrip), `backfillVenueId?`
- `signalType`, `signalValue`, `confidenceTier`
- `weight` (tier-based: 0.65/0.40/0.20)
- `earnedOut` (boolean, flipped after 3/7 completed trips)
- `createdAt`, `updatedAt`

**`PersonaDelta`** — delta logging for future third tower
- `id`, `userId` (FK → User), `backfillSignalId` (FK → BackfillSignal)
- `dimensionName`, `personaScore`, `backfillImpliedScore`, `delta`
- `createdAt`

### New Enums
- `ConfidenceTier`: tier_2, tier_3, tier_4
- `BackfillStatus`: processing, complete, rejected, quarantined, archived
- `TripContext`: solo, partner, family, friends, work

### No changes to existing models
BackfillTrip is intentionally separate from Trip — different lifecycle, data shape, trust level. Shares ActivityNode via resolution link on BackfillVenue.

---

## Ingestion Pipeline (FastAPI)

### Endpoint: `POST /api/backfill/submit`
Accepts raw free-form text + optional metadata (city hint, date range hint). Returns immediately with `backfillTripId` and `status: "processing"`. Pipeline runs async via FastAPI BackgroundTasks (acceptable for beta scale — Cloud Tasks is upgrade path).

**Auth:** Next.js proxy route forwards to FastAPI with service-to-service token. User never hits FastAPI directly. Follows existing architecture pattern.

**Rate limit:** 5 submissions per user per hour, 20 per day. Idempotency key: hash of (userId + rawSubmission text) prevents duplicate processing.

**Input validation:** rawSubmission max 10,000 characters. Rejected server-side before any LLM call.

### Stage 1 — Source Classification
- Rules-based, no ML. Everything is free-form for now.
- Haiku classifies whether text contains annotations (ratings, sentiment phrases) -> Tier 3 if yes, Tier 4 if bare.
- Tier is permanent — nothing downstream promotes it.

### Stage 2 — LLM Extraction
- Sonnet extracts structured data. Prompt: output null over guessing, prefer 8 high-confidence extractions over 15 low-confidence.
- Output per venue: name, category, dateOrRange, city, sentiment (positive/negative/neutral + raw phrase).
- **Structured JSON via Anthropic tool use** (enforced — constrains output schema, mitigates prompt injection).
- **Prompt injection defense:** System prompt contains extraction instructions. User message contains ONLY the raw text wrapped in `<user_diary>...</user_diary>` delimiters. Raw submission text is never part of the instruction layer.

### Stage 2.5 — LLM Validation / Sanitization
- Haiku second pass on extraction output.
- Validates plausibility, NOT existence in our database:
  - Is venue name a plausible real place (not hallucinated)?
  - Does geographic context match claimed city?
  - Are dates internally consistent?
  - Is category assignment reasonable?
- Failed validation -> venue nulled out (not passed to entity resolution).
- "Could this be real" not "do we know about it."
- Unresolved venues (real but not in our DB) are valuable — surface gaps in world knowledge.

### Stage 3 — Entity Resolution
- **pg_trgm fuzzy name matching** (NOT Qdrant vector search — corrected from initial draft).
- Each validated venue name -> `normalize_name()` (existing function in entity_resolution.py) -> pg_trgm `similarity()` query scoped by city.
- Match threshold: 0.75 (slightly higher than existing 0.7 since LLM-extracted names may be less precise).
- Category matching: attempt with extracted category first; if no match, retry without category constraint (handles LLM category misclassification).
- Below threshold: stored as unresolved (isResolved: false, activityNodeId: null). Visible in diary, excluded from persona signals.
- Above threshold: linked to ActivityNode, resolutionScore saved.

### Stage 4 — Anomaly & Integrity Checks
Deterministic rules:
- Geographic impossibility: two resolved venues >500mi apart same day (haversine)
- Temporal impossibility: >8 venues on a single day
- Density outlier: >70% venues are priceLevel 4+ (aspirational flag)
- Duplicate: same user + same city + overlapping date range with existing backfill
- Flagged venues: isQuarantined: true + quarantineReason. Still in diary, excluded from signals.

### Stage 5 — Signal Generation
- Clean, resolved, non-quarantined venues -> BackfillSignal rows.
- Weight by tier: 0.65 (T2) / 0.40 (T3) / 0.20 (T4).
- earnedOut defaults false. Separate job/check-on-read flips based on completed trip count (halved at 3, residual at 7).
- No persona computation yet — just storage.

### Quality Gate
Submission rejected at Stage 1 if <3 venues extractable AND no temporal context. User gets explanation. (AND logic: 2 venues with dates = accepted.)

### Status Updates
Pipeline writes BackfillTrip.status as it progresses. Each stage updates status before doing work (crash recovery — avoids stuck "processing" state). Frontend polls via GET /api/backfill/trips/[id]/status.

---

## Enrichment API Routes (Next.js)

All require auth, scoped to backfill trip owner.

**Ownership enforcement:** All venue-level endpoints resolve `BackfillVenue.backfillTripId -> BackfillTrip.userId` and verify against `session.user.id`. Photo endpoints resolve full chain: `BackfillPhoto.backfillVenueId -> BackfillVenue.backfillTripId -> BackfillTrip.userId`.

**Response filtering:** Never return `confidenceTier`, `resolutionScore`, or `quarantineReason` to client. Quarantined venues return generic `status: "flagged"` with no reason. Use explicit Prisma `select` on all queries.

**Soft-delete queries:** All GET endpoints filter `status NOT IN ('archived', 'rejected')`.

- `GET /api/backfill/trips` — list user's backfill trips (bundled into existing `/api/trips` response as separate `backfillTrips` key)
- `GET /api/backfill/trips/[id]` — diary detail (venues, photos, enrichment state)
- `PATCH /api/backfill/trips/[id]` — update context tag, trip note
- `DELETE /api/backfill/trips/[id]` — soft delete (status -> archived)
- `PATCH /api/backfill/venues/[id]` — update wouldReturn toggle (resolved venues only)
- `POST /api/backfill/venues/[id]/photos` — photo upload (multipart, EXIF extraction, GCS)
- `DELETE /api/backfill/venues/[id]/photos/[photoId]` — remove photo (deletes GCS object + DB row)
- `GET /api/backfill/trips/[id]/status` — processing status poll
- `POST /api/backfill/submit` — Next.js proxy to FastAPI (service-to-service auth)

### Photo Upload Details
- Max 10MB, JPEG/PNG/HEIC/WebP
- **MIME validation via magic bytes** (file header), not Content-Type header or extension
- **Pixel dimension cap:** max 8192x8192 via sharp (prevents decompression bombs)
- **Extension derived from validated MIME type**, never from originalFilename (prevents path traversal)
- EXIF GPS + timestamp extracted server-side via sharp
- EXIF coordinate validation: lat -90 to 90, lng -180 to 180. Discard non-GPS EXIF fields.
- EXIF GPS rounded to 3 decimal places (~111m precision) for privacy
- GCS bucket: `backfill-photos/{userId}/{venueId}/{uuid}.{ext}`
- Display via signed URLs (15-minute expiration, `response-content-disposition: attachment`)
- Max 20 photos per venue
- GCS object deleted on photo row deletion

---

## Frontend

### Onboarding Backfill Step
- New step between fork and destination: "Tell us about a recent trip so we can personalize your itinerary"
- Large free-form text area with guiding placeholder: "Where you went, what you did, places you loved. The more detail, the better."
- Two CTAs: "Add trip" (submits via proxy to FastAPI, shows brief confirmation) / "Skip for now"
- Non-blocking: doesn't wait for pipeline completion, advances to city selection
- "Add another trip" link after first submission for multiple entries
- Same card layout, Sora/DM Mono typography, skippable pattern
- Added to WizardStep type and STEP_ORDER array

### Dashboard Diary Section
- "Past Travels" section below active/upcoming, above completed
- Backfill trips bundled into existing `/api/trips` response (single fetch, no second loading state)
- `DiaryTripCard` component:
  - Warm-surface background (lightweight, no hero image)
  - City + country, date range, context tag badge
  - Venue count (resolved only): "7 places"
  - Processing indicator if status: processing
  - CTA: "View diary" -> /diary/[id]
- Section visibility: shows when 1+ backfill trips exist
- Zero-state: QuickStartGrid gets "Add a past trip" card; if planned trips exist but no backfill, small prompt card at bottom

### Diary Detail View — /diary/[id]
**Header:**
- City + country (Sora heading), date range or "Dates unknown" (DM Mono)
- Context tag selector (single-tap pills, saves on tap)
- Status badge if processing

**Venue list:**
- Chronological if dates extracted, alphabetical by category otherwise
- Resolved venues: linked name (ActivityNode data), neighborhood, price level, "would return" heart toggle
- Unresolved venues: dimmed, name as-is, no toggle, "Not in our database yet" label
- Quarantined venues: visible, generic "We couldn't verify this one" (no quarantineReason exposed)

**Photos per venue:**
- "+" button on each venue card (max 20 per venue)
- Thumbnail grid (max 4 visible, "+N more" overflow)
- Lightbox on tap, EXIF GPS badge if coordinates extracted
- Upload/delete via API

**Trip note:**
- Bottom of page, single prompt: "Anything you'd do differently?"
- Text area, auto-saves on blur
- Optional — empty state prompt if unfilled

**Not a planner:** Flat venue list with enrichment surfaces, no day-by-day timeline, no FAB.

---

## Build Sequence

### Phase 1 — Schema + Pipeline
1. Prisma schema additions (5 new models, 3 new enums, User relation update)
2. FastAPI backfill endpoint + async pipeline (stages 1-5)
3. LLM extraction prompt (Sonnet) + validation prompt (Haiku) with injection defenses
4. pg_trgm entity resolution (reuse normalize_name, add backfill-specific resolver)
5. Anomaly/integrity check rules
6. Next.js proxy route for backfill submit (service-to-service auth)

### Phase 2 — Enrichment APIs
7. Backfill CRUD routes (Next.js) with ownership chain verification
8. Photo upload route + GCS integration + EXIF extraction + security hardening
9. Processing status poll endpoint
10. Bundle backfillTrips into /api/trips response

### Phase 3 — Frontend
11. Onboarding backfill step (new step in wizard, skippable)
12. Dashboard diary section + DiaryTripCard
13. Diary detail page with venues, photos, enrichment controls
14. QuickStartGrid "Add a past trip" card

### Phase 4 — Infrastructure
15. PersonaDelta table — schema + write path only
16. Earn-out logic (check completed trip count, update BackfillSignal.earnedOut)

Testing follows each phase — pipeline unit tests (mocked LLM fixtures + contract tests), API integration tests, frontend component tests (Vitest).

---

## Constraints (from source doc)
- Backfill NEVER enters ranking model (no counterfactual context)
- Confidence tiers never exposed to users
- Tiers are permanent — nothing downstream promotes them
- No third tower build until 500+ users with 3+ trips each
- Backfill signals are priors, not state — separate partition, auditable
- Progressive earn-out: halved at 3 completed trips, residual at 7
- Minimum quality gate: <3 venues AND no temporal context = rejection

## Security Requirements (from review)
- LLM prompt injection: system/user message separation, tool use enforcement, `<user_diary>` delimiters
- Venue IDOR: full ownership chain verification on all venue/photo endpoints
- Photo upload: magic byte MIME validation, pixel dimension cap, EXIF coordinate validation, GCS path from MIME not filename
- Signed URLs: 15-minute expiration, attachment disposition
- Rate limiting: 5/hour, 20/day on backfill submit
- Input length: 10,000 char max on rawSubmission
- Response filtering: no confidenceTier, resolutionScore, quarantineReason in API responses
- Soft-delete consistency: all queries filter archived/rejected status
