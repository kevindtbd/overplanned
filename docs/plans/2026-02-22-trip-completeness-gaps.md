# Trip Completeness Gaps — Design & SoC Execution Plan

**Date:** 2026-02-22
**Context:** User's 3 explicit complaints: (1) no way to publish/start a trip manually, (2) planningProgress always 0%, (3) "Add Activity" FAB → Discover is a dead-end with no return path. Plus 12 additional gaps found in docs-vs-implementation audit.

---

## Tier 0: User's Explicit Complaints (Must Fix Now)

### Gap 0A: Planning Progress Always 0%

**Problem:** `planningProgress` field exists in Prisma schema and UI (TripHeroCard progress bar) but nothing ever writes to it. Always shows "0%".

**Root cause:** No computation logic exists anywhere. The PATCH endpoint accepts `planningProgress` but no code ever calls it.

**Solution:** Compute `planningProgress` server-side in GET /api/trips/[id] on every read (check-on-read pattern, same as auto-transition). Formula:

```
progress = decidedSlots / totalSlots
where decidedSlots = slots with status "confirmed" OR "skipped"
```

"Progress" means "how many decisions has the user made," not "how many things are confirmed." A user who explicitly skips a slot is making progress. This prevents the weird UX where skipping 5/10 slots shows 0% progress.

- If `totalSlots === 0` → progress = 0
- Round to 2 decimal places: `Math.round(x * 100) / 100` (stored as 0.0-1.0 float)
- **Compute from in-memory data:** The GET already fetches `trip.slots` via `include`. Count from the included array — zero extra DB queries: `trip.slots.filter(s => s.status === "confirmed" || s.status === "skipped").length / trip.slots.length`
- Write to DB on read (same `trip.update` call as auto-transition) only if value changed
- Only organizer triggers the write (same guard as auto-transition)

**Files:**
- Edit: `apps/web/app/api/trips/[id]/route.ts` — add progress computation in GET after slot fetch

**Dashboard reads stored value:** The dashboard list GET (`/api/trips`) does NOT recompute progress — it reads the stored `planningProgress` value from the DB. This avoids N+1 queries (one aggregate per trip). Progress is stale by at most one page-load, which is fine for a card progress bar. The trip detail GET is the single source of truth that writes the computed value.

**Why check-on-read, not on every slot action?** Slot actions (confirm/skip/lock) go through `/api/slots/[id]/status`, which is a different endpoint. Adding progress recomputation there creates coupling. Check-on-read keeps it self-contained and eventually consistent.

**Note:** Existing mock data uses `planningProgress: 65` (integer percentage). After this change, semantics are 0.0-1.0 float. Dashboard test mock must update from `65` to `0.65`.

### Gap 0B: Add Activity → Discover → No Return Path

**Problem:** FAB links to `/discover?city=X&tripId=Y`. Discover's "Add to Trip" button works (POST /api/trips/[id]/slots, creates slot on Day 1). But after adding, the user is stuck on Discover with no way back to the trip, no feedback that it worked, and the slot always lands on Day 1 regardless of which day they were viewing.

**Solution (3 parts):**

**0B-1: Day selection in slot creation**
- Pass `dayNumber` as query param from FAB: `/discover?city=X&tripId=Y&day=3`
- POST /api/trips/[id]/slots accepts optional `dayNumber` field (default: 1)
- Zod schema: `dayNumber: z.number().int().min(1).optional()`
- **Strict validation:** Server fetches trip dates, computes totalDays, returns 400 if `dayNumber < 1` or `dayNumber > totalDays`. User can fix via "Move to Day" after creation.

**0B-2: Success toast + return link on Discover**
- After successful POST, show inline toast: "Added to Day {n}" with a "Back to trip" link
- Toast auto-dismisses after 5s, link stays

**0B-3: "Back to trip" persistent link**
- When `tripId` is in the URL, show a persistent "Back to trip" link/button in Discover's header
- Links to `/trip/${tripId}`

**Files:**
- Edit: `apps/web/app/trip/[id]/page.tsx` — FAB href includes `&day=${currentDay}`
- Edit: `apps/web/app/api/trips/[id]/slots/route.ts` — accept `dayNumber` param
- Edit: `apps/web/app/discover/DiscoverClient.tsx` — add toast state, "Back to trip" header link
- Edit: `apps/web/app/discover/components/Shortlist.tsx` — pass day info through

### Gap 0C: No Manual "Start Trip" / Publish Button

**Problem:** Only auto-transition (planning → active on startDate) exists. No way for a user to say "I'm ready, start this trip now." Planning → active is gated on the calendar, not on user intent.

**Solution:** Add a "Start Trip" button on the trip detail page header. Only visible when:
- `status === "planning"`
- `myRole === "organizer"`

Clicking it PATCHes `{ status: "active" }` via the existing PATCH endpoint (state machine already allows planning → active). Optimistic UI: update local state immediately, revert on failure.

**Files:**
- Edit: `apps/web/app/trip/[id]/page.tsx` — add button in header, wire PATCH call

---

## Tier 1: Critical Functional Gaps

### Gap 1A + 1C: Slot Movement (Combined — Move Between Days + Reorder)

**Problem:** Generated slots are placed on specific days but users can't move them between days or reorder within a day. No drag-to-reorder, no "move to Day X" option. Slots have `sortOrder` but no UI to change it.

**Solution (MVP):** Single combined endpoint + UI additions.

**API:** PATCH `/api/slots/[slotId]/move` — accepts `{ dayNumber?, sortOrder? }`
- If `dayNumber` provided (no sortOrder): moves slot to target day, appends to end (max sortOrder + 1)
- If `sortOrder` provided (no dayNumber): **insert-at-position** within current day. Shifts all slots at or after the target position down by 1. NOT a swap — users expect [1,2,3,4] → move 4 to 2 → [1,4,2,3], not [1,4,3,2].
- If both provided: moves to target day AND inserts at specified position
- **Transaction with SELECT FOR UPDATE:** Lock all slots for the trip+day being modified to prevent concurrent reorder corruption. Uses `prisma.$transaction` with `SELECT ... FOR UPDATE` on the affected day's slots.
- **CRITICAL: All swap/insert queries MUST include `tripId` in WHERE clause.** Without this, sortOrder queries could match slots from other trips. The slot's `tripId` is read from the fetched slot, then used in all subsequent queries.
- Behavioral signal: `slot_moved` (covers both day moves and reorders)
- Auth: requires joined TripMember (any role can move their trip's slots)
- Validation: dayNumber must be 1..totalDays, sortOrder must be >= 1

**UI:**
- "Move to Day" dropdown on each slot's action menu (SlotActions)
- Up/Down arrow buttons on each slot card for within-day reorder
- Both trigger the same `/move` endpoint with different params

**Files:**
- Create: `apps/web/app/api/slots/[slotId]/move/route.ts` — combined move endpoint
- Edit: `apps/web/components/slot/SlotActions.tsx` — add "Move to Day" dropdown + up/down arrows
- Edit: `apps/web/app/trip/[id]/page.tsx` — handle `move` action type, pass totalDays to SlotActions

### Gap 1B: Trip Settings / Edit Page

**Problem:** No way to edit trip name, dates, or mode after creation. The PATCH endpoint supports these fields but no UI exists.

**Solution:** Trip settings accessible via a gear icon in the trip detail header. Opens an inline panel (not a separate page — keeps context). Mobile-forward: full panel with proper touch targets.

Fields: trip name, start/end dates, mode badge. Cancel/Save buttons. PATCH /api/trips/[id] on save.

**Danger zone at bottom:** Archive button (completed trips only) and Delete button (draft trips only). Confirmation dialog before destructive actions.

**Files:**
- Create: `apps/web/components/trip/TripSettings.tsx` — inline settings panel with danger zone
- Edit: `apps/web/app/trip/[id]/page.tsx` — gear icon + settings panel toggle

---

## Tier 2: Important but Not Blocking

### Gap 2A: Calendar Export (.ics)

**Problem:** CalendarClient.tsx exists at `/trip/[id]/calendar/` but it's just a grid view. No actual .ics export.

**Solution:** Add "Export to Calendar" button that generates an .ics file client-side from the trip's slot data. No new API needed — the data is already on the page.

**RFC 5545 escaping required:** All slot/activity names must escape special characters before embedding in .ics SUMMARY/DESCRIPTION fields:
```typescript
function escapeIcsText(text: string): string {
  return text.replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\n/g, '\\n');
}
```
This prevents injection of iCalendar properties via crafted activity names. Required even though current data is system-seeded — future user-generated content will flow through this path.

**Files:**
- Create: `apps/web/lib/ics-export.ts` — generates .ics string from trip + slots (with escaping)
- Note: Export button wired by Track C2 in TripSettings panel (Track E does NOT touch page.tsx)

### Gap 2B: Trip Completion Flow

**Problem:** No way to mark a trip as "completed". Status goes planning → active (auto or manual), but active → completed has no trigger.

**Solution:** After the trip's endDate passes + organizer visits, show a "Trip complete!" banner with a "Mark as done" button. PATCHes `{ status: "completed" }`. State machine already supports active → completed.

**Files:**
- Edit: `apps/web/app/trip/[id]/page.tsx` — completion banner logic

### Gap 2C: Delete/Archive Trip

**Problem:** No way to remove unwanted trips from the dashboard. Archived status exists in the state machine but no UI.

**Solution:** Actions live inside TripSettings panel (gear icon → full panel → danger zone at bottom). Mobile-forward: proper touch targets, room for confirmation dialogs.

- "Archive trip" — PATCHes `{ status: "archived" }`. Only visible for completed trips (state machine: completed → archived).
- "Delete draft" — DELETE endpoint (hard delete, not status change) since drafts are throwaway. Confirmation dialog required.

**DELETE handler implementation details (from security review):**
- Must replicate full auth chain: session check → membership check (`status: "joined"`) → role check (`organizer`) → status check (`draft` only)
- Add `DELETABLE_STATUSES = ["draft"]` to `trip-status.ts` alongside existing state machine
- **CRITICAL: BehavioralSignal and PivotEvent have NO cascade relation to Trip.** `prisma.trip.delete()` will NOT cascade to these tables. DELETE handler must explicitly clean up in a transaction:
  ```
  await prisma.$transaction([
    prisma.behavioralSignal.deleteMany({ where: { tripId } }),
    prisma.pivotEvent.deleteMany({ where: { tripId } }),
    prisma.trip.delete({ where: { id: tripId } }),
  ]);
  ```
- TripMember, ItinerarySlot, SharedTripToken, InviteToken DO have `onDelete: Cascade` and are handled automatically.

**Files:**
- Edit: `apps/web/app/api/trips/[id]/route.ts` — add DELETE handler (draft-only, organizer-only)
- Edit: `apps/web/lib/trip-status.ts` — add `DELETABLE_STATUSES`
- Edit: `apps/web/components/trip/TripSettings.tsx` — archive + delete in danger zone section

---

## Tier 3: Nice-to-Have (Defer Unless Time Permits)

### Gap 3A: Before You Go Page
Entry requirements, health advisories, local context. Heavy content that requires new data sources. **Defer.**

### Gap 3B: Trip Todo List / Shared Checklist
New Prisma model, new UI component, new API. **Defer.**

### Gap 3C: Prompt Bar (Mid-Trip Mood Signals)
Complex: real-time mood input → itinerary adjustment. **Defer.**

### Gap 3D: Micro-Stops (Between-Slot Detours)
Requires proximity search + new slot type. **Defer.**

### Gap 3E: Packing List Generation
LLM-generated, city/weather-dependent. **Defer.**

### Gap 3F: Notifications Infrastructure
Cross-cutting concern that touches every feature. **Defer.**

---

## SoC Track Layout

Seven parallel tracks targeting Tier 0 + Tier 1 + Tier 2. Tier 3 is explicitly deferred.

### Track A: Planning Progress (Gap 0A)
**Scope:** Server-side progress computation in trip detail GET only. Dashboard reads stored value.
**Files:** `apps/web/app/api/trips/[id]/route.ts`
**Complexity:** Lite — single concern, 1 file, no new models
**Agent:** soc-core-lite

### Track B: Discover Return Path (Gap 0B)
**Scope:** Day param in FAB + slots API (with strict bounds validation), toast + back link in Discover
**Files:** trip detail page.tsx, slots/route.ts, DiscoverClient.tsx, Shortlist.tsx
**Complexity:** Medium — 4 files, cross-page coordination
**Agent:** soc-core-ultra

### Track C1: Trip Status Buttons (Gap 0C + 2B) — RUNS FIRST
**Scope:** "Start Trip" button (planning → active) + completion banner (active → completed after endDate)
**Files:** `apps/web/app/trip/[id]/page.tsx` — conditional buttons only, no new components
**Complexity:** Lite — buttons + PATCH calls in existing page
**Agent:** soc-core-lite
**Insertion point:** "Start Trip" button goes inside `<header className="space-y-1">` after the metadata div (the `<div className="flex items-center gap-3...">`). Completion banner goes BEFORE the DayNavigation component.

### Track C2: Trip Settings Panel (Gap 1B + 2C) — RUNS AFTER C1
**Scope:** Settings panel (edit name/dates/mode) + danger zone (archive completed, delete draft) + DELETE endpoint + calendar export button (imports from Track E's `ics-export.ts`)
**Files:** `apps/web/components/trip/TripSettings.tsx` (new), `apps/web/app/api/trips/[id]/route.ts` (add DELETE), `apps/web/lib/trip-status.ts` (add DELETABLE_STATUSES), `apps/web/app/trip/[id]/page.tsx` (gear icon toggle)
**Complexity:** Medium — new component + new API handler + page integration
**Agent:** soc-core-ultra
**Insertion point:** Gear icon goes as the FIRST child of `<header>` wrapped in a flex container with the existing content. Settings panel renders as a sibling after the header block.
**Note on dates:** `WRITABLE_BY_STATUS.planning` currently only allows `["name", "status", "planningProgress"]`. To support date editing for planning trips, add `"startDate"` and `"endDate"` to the planning writable set. Otherwise the settings panel silently drops date changes for any non-draft trip.

### Track D: Slot Management (Gap 1A + 1C combined)
**Scope:** Single PATCH `/api/slots/[slotId]/move` endpoint for day moves + reorder. UI: "Move to Day" dropdown + up/down arrows in SlotActions.
**Files:** `apps/web/app/api/slots/[slotId]/move/route.ts` (new), `apps/web/components/slot/SlotActions.tsx`, `apps/web/app/trip/[id]/page.tsx`
**Complexity:** Medium — new endpoint + SlotActions expansion + transaction logic
**Agent:** soc-core-ultra

### Track E: Calendar Export (Gap 2A)
**Scope:** .ics file generation + export button
**Files:** `apps/web/lib/ics-export.ts` (new), trip detail page integration
**Complexity:** Lite — isolated utility, no API changes
**Agent:** soc-core-lite

### Track F: Tests
**Scope:** Tests for all new endpoints + UI changes across tracks A-E
**Files:** New test files for each track
**Complexity:** Medium — needs to cover all new behavior
**Agent:** soc-testing

### Dependency Graph

```
Track A  (progress)       → independent
Track B  (discover)       → independent
Track C1 (status buttons) → independent
Track C2 (settings panel) → depends on C1 + E (C1 edits header first, E provides ics-export.ts)
Track D  (slot mgmt)      → independent
Track E  (calendar)       → independent
Track F  (tests)          → depends on A-E completion
```

**Wave 1 (parallel):** A, B, C1, D, E — all independent
**Wave 2 (after Wave 1):** C2 — depends on C1 (header changes) and E (ics-export.ts)
**Wave 3 (after Wave 2):** F — tests for everything

### File Ownership (Conflict-Free via Waves)

**Shared file: `apps/web/app/trip/[id]/page.tsx`** — touched by tracks B, C1, C2, D.
- **Wave 1:** B (FAB href only, line ~183 `discoverUrl`), C1 (header buttons, line ~260), D (`handleSlotAction` line ~115)
- **Wave 2:** C2 (gear icon in header + settings panel toggle) — runs after C1, so header is stable

Track E does NOT touch page.tsx — export button lives in TripSettings (C2 imports `ics-export.ts`).

**Shared file: `apps/web/app/api/trips/[id]/route.ts`** — touched by tracks A and C2.
- **Wave 1:** A modifies GET handler (progress computation)
- **Wave 2:** C2 adds DELETE handler (new export)
No overlap — different HTTP methods, different waves.

**Track B note:** The slots route (`apps/web/app/api/trips/[id]/slots/route.ts`) currently only selects `city` from the trip (line 84). For dayNumber validation, the select must expand to include `startDate` and `endDate` to compute totalDays.

**Track B client-side note:** Query params arrive as strings. Client must parse `searchParams.get("day")` with `Number()` and validate before including in POST body. Zod catches NaN server-side, but clean parsing avoids sending garbage.

---

## Success Criteria

1. Planning progress updates when user confirms/skips slots (visible on next page load)
2. "Add Activity" FAB sends current day number, slot lands on correct day
3. After adding activity on Discover, user sees toast + can navigate back to trip
4. "Start Trip" button manually transitions planning → active
5. Slots can be moved between days and reordered within a day
6. Trip settings panel allows editing name/dates
7. Calendar .ics export generates valid file
8. Trip completion banner appears after endDate
9. Draft trips can be deleted, completed trips can be archived
10. All new behavior has test coverage
