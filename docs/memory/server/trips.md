# Server / Trips & Legs

## API Routes
- `app/api/trips/route.ts` — Trip list (GET) + create (POST)
- `app/api/trips/[id]/route.ts` — Trip detail (GET) + update (PATCH)
- `app/api/trips/draft/route.ts` — Draft trip creation
- `app/api/trips/[id]/legs/route.ts` — Leg list (GET) + create (POST)
- `app/api/trips/[id]/legs/[legId]/route.ts` — Leg update (PATCH) + delete
- `app/api/trips/[id]/legs/reorder/route.ts` — Leg reorder (PATCH)
- `app/api/trips/[id]/slots/route.ts` — Trip slots

## Key Libraries
- `lib/trip-legs.ts` — TripLeg utilities
- `lib/trip-status.ts` — Status state machine
- `lib/validations/trip.ts` — Trip Zod schemas
- `lib/constants/trip.ts` — Trip constants
- `lib/generation/generate-itinerary.ts` — Itinerary generation
- `lib/generation/scoring.ts` — Activity scoring
- `lib/generation/slot-placement.ts` — Slot placement algorithm
- `lib/generation/promote-draft.ts` — Draft -> active promotion
- `lib/generation/transit-suggestion.ts` — Inter-leg transit

## Trip Status State Machine
- **draft** -> planning -> active (auto on startDate) -> completed -> archived
- Draft = saved idea, incomplete onboarding. Resume via `/onboarding?resume=<tripId>`
- Duplicate detection: `userId + city + status = draft`
- Auto-transition: organizer-only, check-on-read in trip detail GET only

## Multi-City Architecture
- Trip -> TripLeg[] (ordered by position, max 8)
- dayNumber is leg-relative, absolute day computed at read time
- Inter-leg transit on TripLeg, NOT as phantom ItinerarySlot
- GET /api/trips returns derived: primaryCity, primaryCountry, primaryDestination, legCount
- Trip no longer has destination/city/country/timezone (moved to TripLeg)

## Generation Engine
- Hybrid: deterministic scoring/placement first, async LLM enrichment after HTTP response
- Fire-and-forget: LLM enrichment failure = no-op, deterministic itinerary stands alone
- Pace -> slots/day: packed=6, moderate=4, relaxed=2
- Diversity cap: no single category > 1/3 of total slots
- `generateLegItinerary` (per-leg), `generateTripItinerary` (orchestrator)

## Learnings
- Plans from memory have wrong API shapes — always verify interfaces against source code
