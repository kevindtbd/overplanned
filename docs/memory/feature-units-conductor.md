# Feature Units Sprint + Conductor Learnings (2026-02-22/23)

## Conductor Execution Patterns
- **M-001 schema INTERRUPT caused cascade hallucinations** — when the schema gate migration interrupted (3 parallel workers tried to write prisma/schema.prisma simultaneously), downstream workers that depended on it ran anyway and hallucinated schema additions (TripLeg/BackfillLeg models that weren't in the plan). Conductor dependency gates aren't strictly enforced on INTERRUPT.
- **Workers hallucinate helpfully** — when a conductor worker sees unexpected schema state, it "helpfully" updates files to match, even if the schema change wasn't planned. This turned a 1-file interrupt into 17+ rogue file modifications + 3 rogue new files.
- **Schema migrations must be SOLO** — never put schema changes in a parallel wave. Gate M-001 should have been `workers: 1` for that wave only, or run manually before launching conductor.
- **Cleanup strategy for rogue changes** — cross-reference every modified file against the plan's target file lists. `git checkout` files not in the plan, `rm` new files not in the plan. Surgical, not `git reset --hard`.
- **conductor.yaml settings that worked**: workers: 5, model: claude-opus-4-6, budget_usd: 500, root_dir: ../../, retry with backoff, silence_timeout_ms: 120000

## Test Fix Patterns from Feature Units
- **Non-UUID test IDs hit Zod `.uuid()` validation first** — "slot-1", "alt-1", "item-1" all fail Zod before reaching business logic. Tests expecting 404/500 get 400 instead. ALWAYS use valid UUIDs in test payloads when Zod schema has `.uuid()`.
- **`vi.clearAllMocks()` doesn't clear `mockResolvedValueOnce` queues** — in some vitest versions, only call history is cleared, not mock return value queues. Use `vi.resetAllMocks()` in `beforeEach` to fully reset between tests.
- **Module-level `new Anthropic()` throws in jsdom** — Anthropic SDK checks for browser environment and throws. Tests importing routes that transitively import llm-enrichment.ts need `vi.mock("@anthropic-ai/sdk")` before any imports.
- **TripLeg migration test pattern** — tests referencing `trip.city`/`trip.destination` need:
  1. Mock payloads: flat fields -> `legs: [{ city, country, ... }]` array
  2. Mock prisma: add `tripLeg.createMany`, `trip.findUnique` (re-fetch with legs)
  3. Assertions: `json.trip.city` -> `json.trip.legs[0].city`
  4. ICS: `IcsTripData` uses `name` + `legs[]` instead of `destination` + flat tz

## Feature Units API Summary (6 tracks, all committed)
- **Track 1 (Invite)**: 3 endpoints (preview, join, create), TOCTOU atomic SQL, 256-bit tokens, 35 tests
- **Track 2 (Vote)**: Zod schema, quorum logic, 70% yes-only threshold, behavioral signal logging, 24 tests
- **Track 3 (Share)**: create token, public view, import (clones Trip+Legs+Slots with fresh UUIDs), 28 tests
- **Track 4 (Reflection)**: validation with HTML strip, read-merge-write + atomic signal logging
- **Track 5 (Packing)**: POST (LLM generation) + PATCH (item toggle), PackingList.tsx component, 33 tests
- **Track 6 (Pivot)**: creation + resolution, scoring, caps enforcement (3 active max), vote reset on swap
- **Infrastructure (Track 0)**: rate limiter (3 tiers), NextAuth redirect validation, test helpers (transaction mock, auth factory)
- **Cross-track**: 9 new SignalType enum values, integration tests (invite->vote, import->reflection, quorum adjustment, pivot voteState reset)

## Schema State After Sprint
- 34+ Prisma models (added TripLeg, BackfillLeg, expanded UserPreference/NotificationPreference)
- Trip lost destination/city/country/timezone (moved to TripLeg)
- TripLeg: position-ordered, @@unique([tripId, position]), transit fields for multi-city
- ItinerarySlot gained tripLegId FK
- ownerTip on ItinerarySlot (separated from voteState per architect review)
- @@index([tripId, status]) on TripMember (security performance)
- 716 tests passing across 46 files
