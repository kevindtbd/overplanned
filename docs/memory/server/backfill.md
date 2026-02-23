# Server / Backfill & Enrichment

## Routes
- `app/api/backfill/trips/route.ts` — Backfill trip list
- `app/api/backfill/trips/[id]/route.ts` — Backfill trip detail
- `app/api/backfill/trips/[id]/status/route.ts` — Backfill status
- `app/api/backfill/venues/[id]/route.ts` — Venue enrichment
- `app/api/backfill/venues/[id]/photos/route.ts` — Venue photos
- `app/api/backfill/venues/[id]/photos/[photoId]/route.ts` — Individual photo
- `app/api/backfill/submit/route.ts` — Submit backfill

## Key Libraries
- `lib/backfill-auth.ts` — Backfill-specific auth checks
- `lib/validations/backfill.ts` — Backfill Zod schemas

## Patterns
- BackfillLeg model added for multi-city backfills
- Venue enrichment pipeline with photo management
- Backfill uses separate auth flow (can be less restrictive)

## Learnings
- (space for future compound learnings)
