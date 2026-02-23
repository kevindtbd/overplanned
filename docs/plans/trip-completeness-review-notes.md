# Trip Completeness Gaps — Deepening Review Notes

**Date:** 2026-02-22

## Issues Found & Resolutions

### 1. Dashboard progress N+1 query (Critical)
**Issue:** Computing `confirmedSlots / totalSlots` for every trip in the dashboard list GET means N+1 DB queries.
**Resolution:** Only compute progress in the trip detail GET (single trip, already touching slots). Dashboard reads the stored `planningProgress` value from DB. Stale by at most one page-load — fine for a card progress bar.

### 2. dayNumber bounds validation (Medium)
**Issue:** `?day=99` or `?day=0` could create slots on invalid days. Plan didn't specify validation.
**Resolution:** Strict 400 rejection in POST /api/trips/[id]/slots. Fetch trip dates, compute totalDays, reject if `dayNumber < 1` or `dayNumber > totalDays`. User can then use "Move to Day" to fix.

### 3. Track C scope too wide (Medium)
**Issue:** Track C bundles Start Trip button + Trip Settings panel + completion flow + archive/delete. Too much for one agent.
**Resolution:** Split into:
- Track C1: Start Trip button + completion banner (conditional buttons, no new components)
- Track C2: Trip Settings panel + archive/delete (new TripSettings.tsx + DELETE endpoint)
Both can run in parallel.

### 4. Slot endpoint proliferation (Medium)
**Issue:** Plan creates 2 new slot endpoints (day, reorder) on top of existing 2 (status, swap). 4 slot endpoints is fragmented.
**Resolution:** Single combined PATCH `/api/slots/[slotId]/move` that accepts `{ dayNumber?, sortOrder? }`. Handles both day moves and reorders. Transaction-wrapped for atomic sortOrder swaps. Reduces from 4 to 3 endpoints.

### 5. Delete/Archive UX on mobile (Low)
**Issue:** Overflow `...` menu has poor mobile UX (tiny tap targets, competes with header).
**Resolution:** Delete/archive actions live inside TripSettings panel (gear icon → full panel → danger zone at bottom). Standard mobile pattern, proper touch targets, room for confirmation.

## Updated Track Layout

```
Track A:  Planning Progress (detail GET only, dashboard reads stored value)
Track B:  Discover Return Path (day param, toast, back link)
Track C1: Trip Status Buttons (Start Trip + completion banner — buttons only)
Track C2: Trip Settings Panel (settings form + archive/delete + DELETE endpoint)
Track D:  Slot Management (combined /move endpoint for day moves + reorder)
Track E:  Calendar Export (.ics generation)
Track F:  Tests (depends on A-E)
```

All tracks A-E remain fully independent. Track C split into C1+C2 adds one more parallel unit.

## No Issues Found With:
- State machine transitions (verified: planning→active already allowed)
- IDOR protection pattern (all new endpoints should copy the existing membership check)
- Behavioral signal logging (plan correctly specifies signals for new actions)
- Calendar export approach (client-side .ics from existing data — no API needed)
- Tier 3 deferrals (all correctly scoped out)
