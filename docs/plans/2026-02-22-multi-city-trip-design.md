# Multi-City Trip Architecture

**Date:** 2026-02-22
**Status:** Reviewed — deepen + architect + security + test-engineer complete
**Scope:** Trip data model, generation engine, onboarding, backfill, UI

---

## Problem

Both Trip and BackfillTrip are single-city. A trip has one `city`, one `country`, one `timezone`. Activities are hard-matched to the trip's city (422 if mismatched). Generation queries `WHERE city = ?`.

Real travel is multi-city. "2 weeks in Japan" = Tokyo -> Kyoto -> Osaka. "Europe backpacking" = Lisbon -> Barcelona -> Paris. The current model forces users to create separate trips per city, which is a dead-end UX.

## Design Principles

- **Type A for Type B** — the system does the structuring. User picks cities and total dates, we allocate days per leg with travel days inserted automatically.
- **Legs are the unit of generation** — each leg gets its own city, timezone, date range, and activity pool. Generation runs per-leg, not per-trip.
- **Travel days are explicit** — reduced/no activity slots on leg transition days. Transit-aware scheduling.
- **No production data** — there are no shipped users. Migration is a clean cut, not a compatibility dance.

---

## Data Model

### New: `TripLeg` model

```prisma
model TripLeg {
  id          String   @id @default(uuid())
  tripId      String
  trip        Trip     @relation(fields: [tripId], references: [id], onDelete: Cascade)

  position    Int      // 0-indexed ordering within the trip route
  city        String
  country     String
  timezone    String
  destination String   // "Kyoto, Japan" display string

  startDate   DateTime // first full day in this city
  endDate     DateTime // last full day in this city
  dayCount    Int      // number of activity days in this leg (derived from date range)

  // Travel day config
  arrivalTime   String?  // "morning", "afternoon", "evening" — affects first-day slot count
  departureTime String?  // affects last-day slot count

  // Inter-leg transit (how you arrive at this leg from the previous one)
  // Position 0 (first leg) has null transit fields.
  transitMode        String?   // "shinkansen", "flight", "bus", "car", "ferry"
  transitDurationMin Int?      // estimated minutes
  transitCostHint    String?   // "~13,320 yen", "~$200" — display string, not structured pricing
  transitConfirmed   Boolean   @default(false)  // user has confirmed/edited the suggestion

  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt

  slots       ItinerarySlot[]

  @@unique([tripId, position])
  @@index([tripId])
  @@index([city])
}

// NOTE from reviews:
// - TripLeg.timezone should be String? (nullable) for freeform cities without timezone lookup
// - dayCount: compute from endDate - startDate, do NOT store as a column (drift risk)
//   Use a helper: daysBetween(startDate, endDate) wherever dayCount is needed

```

### Modified: `Trip` model

Remove `city`, `country`, `timezone`, `destination` as direct fields. Replace with legs.

Since there is no production data, this is a clean cut — no denormalized columns, no dual source of truth. All code that reads `trip.city` gets updated to read `trip.legs[0].city` (or the appropriate leg).

```prisma
model Trip {
  id          String     @id @default(uuid())
  userId      String
  user        User       @relation(fields: [userId], references: [id], onDelete: Cascade)
  name        String
  startDate   DateTime   // overall trip start (= first leg startDate)
  endDate     DateTime   // overall trip end (= last leg endDate)
  status      TripStatus @default(draft)
  template    String?
  pace        String?
  // ... other existing fields unchanged
  // REMOVED: city, country, timezone, destination (now on TripLeg)

  legs        TripLeg[]  // ordered by position
  members     TripMember[]
  slots       ItinerarySlot[] // kept — slots also link to TripLeg
  // ...
}
```

### Modified: `ItinerarySlot` model

Add required `tripLegId` foreign key. Slots belong to both a trip and a specific leg.

**Day numbering is leg-relative**: `dayNumber` = day within this leg (1-indexed). The API computes absolute trip day at read time: `sum(previous legs' dayCount) + slot.dayNumber`. This means reordering legs only requires updating `TripLeg.position` — zero slot mutations.

```prisma
model ItinerarySlot {
  // ... existing fields
  tripLegId   String
  tripLeg     TripLeg @relation(fields: [tripLegId], references: [id], onDelete: Cascade)
  // dayNumber = day within this leg (1-indexed), NOT absolute trip day
  // ...
}
```

**NOTE:** `onDelete: Cascade` is required — without it, deleting a TripLeg is blocked by its slots (Prisma defaults to Restrict for required FKs).

### Modified: `BackfillTrip` model

Replace single `city`/`country` with a `BackfillLeg` array for multi-city diary extraction. BackfillVenue FK moves from `backfillTripId` to `backfillLegId` (clean migration, no production data).

```prisma
model BackfillLeg {
  id              String       @id @default(uuid())
  backfillTripId  String
  backfillTrip    BackfillTrip @relation(fields: [backfillTripId], references: [id], onDelete: Cascade)

  position        Int
  city            String
  country         String
  timezone        String?       // nullable — may be unknown for diary text, resolved later

  createdAt       DateTime     @default(now())

  venues          BackfillVenue[]  // FK moved from BackfillTrip to BackfillLeg

  @@unique([backfillTripId, position])
  @@index([backfillTripId])
}
```

---

## Inter-Leg Transit

### Source of truth: TripLeg, not ItinerarySlot

Inter-leg transit (Tokyo -> Kyoto) is stored on `TripLeg` fields (`transitMode`, `transitDurationMin`, `transitCostHint`, `transitConfirmed`). There is NO phantom ItinerarySlot created for inter-leg transit.

`SlotType.transit` on ItinerarySlot is reserved for **intra-city** transit between activities (e.g., "Taxi to Nishiki — 18 min, 1,200 yen"). These are different concepts:

| | Inter-leg transit | Intra-city transit |
|---|---|---|
| **Source** | `TripLeg` fields | `ItinerarySlot` with `SlotType.transit` |
| **Example** | Shinkansen Tokyo -> Kyoto | Taxi to Kinkaku-ji |
| **Duration** | Hours | Minutes |
| **Editable by** | User on TripLeg | System-generated, user-editable |
| **Rendered as** | Divider between leg groups in day nav | Card between activity slots |

### LLM-suggested transit (MVP)

Instead of distance heuristic tables (which require city coordinates we don't have), use an **LLM call per leg transition** to suggest the transit mode:

```
System: "Suggest the most common way to travel between these two cities
for a tourist. Return: mode (train/flight/bus/car/ferry), approximate
duration in minutes, and approximate cost in local currency."

User: "From Tokyo, Japan to Kyoto, Japan"

Response: { mode: "shinkansen", durationMin: 135, costHint: "~13,320 yen" }
```

One call per leg transition. Uses claude-haiku-4-5-20251001 (classification task). Runs during trip creation, results stored on TripLeg. User can override.

If hotel/accommodation coordinates are available later (calendar integration, manual input), those refine origin/destination for more precise suggestions.

### Day slot reduction

When legs are adjacent (Leg 0 endDate = Day 4, Leg 1 startDate = Day 5):

1. **Last day of departing leg:** Reduce afternoon/evening slots based on `departureTime`. If `departureTime = "morning"`, zero activity slots that day.
2. **First day of arriving leg:** Reduce morning slots based on `arrivalTime`. If `arrivalTime = "evening"`, only 1 evening slot (dinner near hotel).
3. **Gap days:** If there's a full day between legs (endDate Day 4, startDate Day 6), Day 5 is a travel day with no activity slots. The UI renders the TripLeg transit info for that gap.

### Slot density by arrival/departure time

| Timing | Slots available |
|--------|----------------|
| morning | Full day (no reduction) |
| afternoon | Skip morning slots |
| evening | 1 evening slot only |
| null (not specified) | Treat as "afternoon" default |

### Connection to existing systems

- **`Trip.logisticsState`** — group trips store confirmed transport bookings here (Shinkansen tickets, flight confirmations, cost splits). TripLeg transit fields are the *suggestion*, logisticsState is the *booking*.
- **`PivotEvent.trigger_source = 'transit_delay'`** — future: real-time transit disruptions feed into the cascade evaluator. Inter-leg transit delays can trigger downstream slot adjustments in the arriving leg.
- **Micro-stops** — intra-city transit only. Inter-leg transit is longer-distance and does not trigger micro-stop proximity nudges.
- **Map view** — inter-leg transit renders as a dashed line between city clusters, distinct from intra-city walking lines (solid).

---

## Generation Engine Changes

### Current flow
```
generateItinerary(tripId, userId, city, country, startDate, endDate, personaSeed)
  -> fetch ActivityNodes WHERE city = ?
  -> score + rank + place into day slots
```

### New flow
```
generateTripItinerary(tripId, userId, personaSeed)
  -> fetch trip.legs ordered by position
  -> for each leg:
      -> generateLegItinerary(leg, personaSeed)
          -> if ActivityNode count > 0 for leg.city:
              -> deterministic scoring (existing logic)
          -> else (unseeded city):
              -> LLM-only generation (haiku for activity suggestions)
          -> apply travel day reductions for first/last day
          -> score + rank + place into day slots (leg-relative dayNumber)
          -> tag each ItinerarySlot with tripLegId
```

**Transit suggestion is a SEPARATE module** (`lib/generation/transit-suggestion.ts`), NOT part of the generation orchestrator. Called fire-and-forget from the API route handler after trip creation, same pattern as LLM enrichment:

```
// In POST /api/trips route handler, AFTER returning response:
suggestTransitForLegs(tripId)  // fire-and-forget, non-blocking
  -> for each leg with position > 0:
      -> LLM call (haiku): "best transit from {prevLeg.city} to {leg.city}"
      -> parse response, validate transitMode against enum
      -> store on TripLeg
```

Key changes:
- `generateItinerary` becomes `generateLegItinerary` (same core logic, scoped to one leg)
- New `generateTripItinerary` orchestrates across legs
- **Unseeded cities get LLM-only generation** — the enrichment path becomes the primary generator when ActivityNode count = 0. No blank legs.
- Travel day reduction applied via `arrivalTime`/`departureTime` on the leg
- Slot `dayNumber` is **leg-relative** (1-indexed within the leg). API computes absolute trip day at read time.
- Transit suggestions are **async/fire-and-forget** — trip creation returns immediately with null transit fields. Client polls or receives update via SSE.

### Discover feed
Currently requires `?city=` param. Change to accept `?tripLegId=` which resolves to the leg's city. The FAB on trip detail links to `/discover?tripLegId=${currentLeg.id}&tripId=${tripId}&day=${currentDay}` instead of `?city=`.

**SECURITY: ownership check required.** When resolving `tripLegId`, must verify the caller is a member of the leg's trip (`TripMember.status = "joined"`). Without this, any authenticated user can probe arbitrary leg UUIDs to enumerate cities on other users' trips. Return 404 for non-members.

### City-match guard on slot creation
Currently: `activityNode.city !== trip.city` -> 422.
New: `activityNode.city !== tripLeg.city` -> 422.
The guard still exists but is leg-scoped, not trip-scoped.

**SECURITY: cross-trip leg injection.** Slot creation must verify `tripLeg.tripId === params.tripId` before inserting. Without this check, a user could point a slot at another trip's leg by guessing the UUID.

---

## Onboarding Flow Changes

### Current flow
1. Fork (new user vs returning)
2. Backfill (optional past trip)
3. Destination (pick ONE city from LAUNCH_CITIES)
4. Dates (start + end date)
5. Trip name (auto: "Tokyo Apr 2026")
6. TripDNA (template + pace)

### New flow
1. Fork
2. Backfill (optional past trip diary)
3. **Route builder** (replaces single Destination step)
   - Start with "Where are you going?" — add first city
   - "+ Add another city" button to add legs
   - Drag to reorder (or simple up/down arrows for MVP)
   - Each city shows as a pill/chip in the route: `Tokyo -> Kyoto -> Osaka`
   - Minimum 1 city, **maximum 8 legs** (hard cap — bounds worst-case LLM calls to 7)
   - **Freeform city input accepted** — LAUNCH_CITIES shown as suggestions, but any city name is valid. Unseeded cities get LLM-only generation.
   - City name validation: max 100 chars, printable Unicode only (no control characters). Sanitized before entering LLM prompts.
4. Dates (start + end for overall trip)
5. **Day allocation** (new step — skipped for single-leg trips)
   - Shows both: **"10 days total, 8 activity days"** — travel days are transparent
   - System auto-suggests days per leg: equal distribution of activity days, rounded
   - User can adjust with +/- buttons per leg
   - Travel days auto-inserted between legs with LLM-suggested transit
   - Visual timeline: `[Tokyo 3d] — Shinkansen 2h — [Kyoto 3d] — train 15min — [Osaka 2d]`
6. Trip name (auto-generation rules):
   - All same country: "Japan Apr 2026"
   - Multi-city same country: "Tokyo to Osaka Apr 2026"
   - Multi-country: "Japan & Thailand Apr 2026"
   - Manual override always available
7. TripDNA (template + pace — applies to all legs uniformly for MVP)

### Backward compatibility
Single-city trips are just routes with one leg. The route builder starts with one city and the "+ Add another" is optional. Day allocation step is skipped for single-leg trips. No forced multi-city, no UX penalty for simple trips.

---

## Trip Detail Page Changes

### Day navigation
Currently a flat day list. New: grouped by leg with city labels and transit dividers.

```
[Day 1] [Day 2] [Day 3]  |  Shinkansen 2h  |  [Day 4] [Day 5] [Day 6]
        Tokyo                                           Kyoto
```

Day numbers shown are **absolute trip days** (computed from leg-relative at read time). The transit divider between legs renders from `TripLeg.transitMode` + `TripLeg.transitDurationMin`.

The active leg determines:
- Which city photo shows in the header
- Which city the FAB/Discover links to
- Which timezone applies for time display

### Header
Instead of static `trip.city, trip.country`, show the route:
`Tokyo -> Kyoto -> Osaka` with the current leg highlighted in accent.
Tapping a city in the route jumps to that leg's first day.

### WelcomeCard
Update to reference the route: "Your Tokyo -> Kyoto -> Osaka trip is ready!"

---

## API Changes Summary

| Endpoint | Change |
|----------|--------|
| `POST /api/trips` | Accept `legs: [{ city, country, timezone, destination, dayCount }]` instead of single city fields. Remove old single-city fields. |
| `POST /api/trips/draft` | Same — accept legs array |
| `GET /api/trips` (list) | Return first leg's city/country for display. Include `legCount` for multi-city indicator. |
| `GET /api/trips/[id]` | Return `legs` array ordered by position, with slots nested per leg. Compute absolute day numbers. |
| `PATCH /api/trips/[id]` | Allow reordering legs (position swap), adjusting day counts, editing transit fields |
| `POST /api/trips/[id]/slots` | Require `tripLegId`. Validate against `tripLeg.city` not `trip.city` |
| `GET /api/discover/feed` | Accept `tripLegId` as alternative to `city` param |
| `POST /api/backfill/submit` | No change (diary text extraction handles multi-city in pipeline) |
| `GET /api/backfill/trips` | Return `legs` array per backfill trip |

---

## Implementation Phases

### Phase A: Schema + API (one pass)
No production data — clean cut, no backward compat scaffolding.

**Schema:**
1. Add `TripLeg` model to Prisma (timezone nullable for freeform cities)
2. Add `BackfillLeg` model (with `timezone String?`)
3. Add `tripLegId` FK to `ItinerarySlot` (required, `onDelete: Cascade`)
4. Move `BackfillVenue` FK from `backfillTripId` to `backfillLegId`
5. Remove `city`/`country`/`timezone`/`destination` from `Trip` model
6. Remove `city`/`country` from `BackfillTrip` model

**Validation:**
7. Update `createTripSchema` + `createDraftSchema` to accept `legs[]` array (max 8)
8. Add city name validation: max 100 chars, printable Unicode, no control chars
9. Constrain `transitMode` to enum: `["flight", "train", "shinkansen", "bus", "car", "ferry"]`
10. Bound `transitDurationMin`: `z.number().int().min(0).max(10080)`
11. Cap `transitCostHint`: max 100 chars

**API routes (explicit callsite list from architect review):**
12. `POST /api/trips` — accept legs array, create TripLeg records
13. `POST /api/trips/draft` — same
14. `GET /api/trips` (list) — return legCount + first leg display fields
15. `GET /api/trips/[id]` — return legs with nested slots, compute absolute day numbers
16. `PATCH /api/trips/[id]` — leg reordering, day count adjustment, transit field edits
17. `POST /api/trips/[id]/slots` — require tripLegId, validate `leg.tripId === trip.id` (security), city-match against leg
18. `GET /api/discover/feed` — accept tripLegId with **ownership check** (security)
19. `GET /api/backfill/trips` — return legs array with explicit select (no `include: true`)

**Generation engine:**
20. Extract `computeAbsoluteDay()` pure function to `lib/trip-legs.ts`
21. Rename `generateItinerary` → `generateLegItinerary`
22. New `generateTripItinerary` orchestrating per-leg calls
23. LLM-only generation fallback for unseeded cities
24. Extract `suggestTransitForLegs()` to `lib/generation/transit-suggestion.ts` (fire-and-forget)
25. Update `lib/generation/promote-draft.ts` to read `trip.legs` (critical — currently reads `trip.city` directly)

**Other callsites (from architect review):**
26. Update `lib/ics-export.ts` — read timezone from legs, handle multi-timezone
27. Update `lib/city-photos.ts` usage — use first leg city
28. Update `lib/validations/trip.ts` — both create + draft schemas
29. Define `RankingEvent.dayNumber` semantics — keep as absolute trip day, computed at write time

**Tests:**
30. Extract shared fixture factories to `__tests__/helpers/fixtures.ts`
31. Update all 12+ breaking test files (see test review for full list)
32. Add `computeAbsoluteDay` unit tests
33. Add trip name auto-generation unit tests (`lib/trip-name.ts`)
34. Migrate seed data

### Phase B: Onboarding + UI
13. Build RouteBuilder component (replaces DestinationStep)
14. Build DayAllocation step with transit timeline
15. Update trip detail page: leg-grouped day nav, route header, transit dividers
16. Update TripHeroCard/DraftIdeaCard to show route
17. Update trip name auto-generation
18. Update WelcomeCard, ICS export, city photos

### Phase C: Backfill multi-city
19. Update FastAPI backfill pipeline to extract multiple cities from diary text
20. Create BackfillLeg records from extraction results
21. Update DiaryTripCard to show route

---

## What This Does NOT Cover

- **Real-time transit API integration** — transit suggestions use LLM heuristics, not live transit APIs. Real-time disruption handling (`PivotEvent.transit_delay`) is a future enhancement.
- **Exact transport pricing** — cost hints are approximate display strings ("~13,320 yen"), not structured pricing from booking APIs.
- **Per-leg template/pace** — MVP applies TripDNA uniformly. Per-leg customization is a future enhancement.
- **Timezone display in slot times** — currently not shown. Multi-timezone trips will need this eventually but not in MVP.
- **Collaborative leg editing** — TripMember permissions apply at trip level. Per-leg permissions are out of scope.

---

## Resolved Design Decisions

| Decision | Resolution | Rationale |
|----------|-----------|-----------|
| Transit source of truth | TripLeg fields only, no phantom ItinerarySlot | ItinerarySlot has no transport-specific columns; `SlotType.transit` is for intra-city only |
| Day numbering | Leg-relative on ItinerarySlot, absolute computed at read time | Reordering legs = zero slot mutations |
| Travel day transparency | Show both total days and activity days | No hidden math, no surprises |
| Unseeded cities | Allow freeform, LLM-only generation | No artificial restrictions; enrichment path already exists |
| Transit suggestion source | LLM call per leg transition (haiku) | No city coordinates needed; handles any city pair |
| BackfillVenue FK | Clean migration to BackfillLeg | No production data to preserve |
| Phase structure | 3 phases (Schema+API, UI, Backfill) | No production compat needed; Schema+API are tightly coupled |
| Denormalized Trip.city | Removed entirely (clean cut) | No production data = no dual source of truth risk |

## Agent Review Findings (incorporated above)

### Architect (11 issues)
- `onDelete: Cascade` on ItinerarySlot.tripLegId — **fixed in schema**
- `promote-draft.ts` reads `trip.city` — **added to Phase A step 25**
- `ics-export.ts` needs timezone from legs — **added to Phase A step 26**
- `dayCount` stored column drift risk — **resolved: compute, don't store**
- `BackfillLeg` missing timezone — **fixed: added nullable timezone**
- Transit suggestion in wrong module — **fixed: separate fire-and-forget module**
- `TripLeg.timezone` nullable for freeform — **fixed in schema**
- `RankingEvent.dayNumber` ambiguity — **added to Phase A step 29**
- Draft save hook timing — **noted for Phase B**
- BehavioralSignal leg context — **deferred (data quality, not blocking)**
- `slots/route.ts` not in Phase A — **added to step 17**

### Security (6 issues)
- Discover feed IDOR via tripLegId — **added ownership check to step 18**
- Cross-trip leg injection in slots — **added `leg.tripId === trip.id` check to step 17**
- LLM prompt injection via city names — **added city name sanitization to step 8**
- Transit field validation gaps — **added enum + bounds to steps 9-11**
- LLM rate limiting — **resolved: hard cap 8 legs + fire-and-forget transit calls**
- BackfillLeg response field discipline — **added explicit select to step 19**

### Test Engineer (12+ files break)
- P0 breaks: trips.test.ts, trips-draft.test.ts, trips-route.test.ts, ics-export.test.ts, onboarding-draft.test.tsx
- P1 breaks: TripHeroCard, PastTripRow, DraftIdeaCard, DashboardPage, WelcomeCard, DayView, slots-move tests
- New infra: shared fixtures, `computeAbsoluteDay` tests, trip name tests, Anthropic SDK mock pattern
- **All addressed in Phase A steps 30-34**
