# Draft Trip Status Design

**Date:** 2026-02-22
**Status:** Approved (deepened + agent-reviewed)
**Summary:** Give `draft` a real purpose — saved trip ideas that resume onboarding when clicked.

---

## Problem

The `draft` trip status exists in the enum but is a dead-end state. Nothing creates drafts intentionally, nothing transitions out of them, and the UI either hides them or treats them identically to `planning`. Meanwhile, there's a real product need: users who want to explore a trip idea without committing.

## State Machine

| Status | Meaning | Entry | Exit |
|--------|---------|-------|------|
| `draft` | Saved idea, incomplete onboarding | User advances past dates step in onboarding, then bounces | Resume onboarding, complete it -> `planning` |
| `planning` | Committed trip, full onboarding complete | Completing onboarding (new or resumed from draft) | Auto-transition when `startDate` arrives -> `active` |
| `active` | Trip is happening | Auto from planning on startDate | `endDate` passes or manual -> `completed` |
| `completed` | Trip is done | Auto or manual from active | Manual -> `archived` |
| `archived` | Decluttered | Manual from completed | Terminal |

Prisma default stays `@default(draft)` — now intentionally correct.

POST `/api/trips` (called on onboarding completion) keeps setting `status: "planning"`. No change needed.

### State Machine Enforcement (NEW — from reviews)

Server-side transition validator in PATCH handler. Zod schema stays permissive for parsing, handler validates transitions:

```
VALID_TRANSITIONS = {
  draft:     ["planning"],
  planning:  ["active"],
  active:    ["completed"],
  completed: ["archived"],
  archived:  []
}
```

Reject invalid transitions with 409 Conflict.

### Field-Level Write Guards (NEW — from reviews)

PATCH accepts different fields depending on current trip status:

```
WRITABLE_BY_STATUS = {
  draft:     [name, startDate, endDate, mode, presetTemplate, personaSeed, status]
  planning:  [name, status, planningProgress]
  active:    [name, status, planningProgress]
  completed: [status]           // only archive transition
  archived:  []                 // terminal
}
```

Fields not in the writable set for the current status are silently ignored (not rejected — keeps PATCH idempotent).

## Dashboard Card Treatment

Two card types in the Active section:

### Planning/Active: Hero Card (existing `TripHeroCard`)

Full photo, progress bar, member count, mode badge. No changes.

### Draft: Idea Card (new `DraftIdeaCard`)

- No photo, no hero treatment
- `bg-warm-surface` background, `warm-border` border
- City name as primary text (Sora, medium weight)
- Country below (DM Mono, ink-400, small)
- "Continue planning" link-style CTA in terracotta (not a button — low pressure)
- If dates were saved, show them in DM Mono below country
- No progress bar, no member count, no mode badge
- Card links to `/onboarding?resume=<tripId>`

### Ordering

1. Planning/active hero cards first (real trips take priority)
2. Draft idea cards after, in a separate row
3. If ONLY drafts exist (no real trips), drafts still show — no QuickStartGrid

QuickStartGrid only shows when `trips.length === 0` (no trips at all, including drafts).

Dashboard must render `DraftIdeaCard` for `status === "draft"` and `TripHeroCard` for planning/active. Drafts must NEVER link to `/trip/[id]`.

## Draft Creation

**Trigger:** User advances past the dates step (fills dates + clicks Continue). This is the strongest reliable intent signal — they've committed to a city AND dates.

Draft is saved via `POST /api/trips/draft` with:

**Required:** `city`, `country`, `timezone`, `destination`, `startDate`, `endDate`
**Also created:** `TripMember` row with `role: "organizer"`, `status: "joined"` (required for existing auth checks on resume GET)
**Set by API:** `mode: "solo"`, `status: "draft"`
**NOT saved:** template, personaSeed, preferences — completing those IS what promotes to planning

**No duplicate detection.** Users can have multiple drafts for the same city (e.g. Tokyo spring trip vs Tokyo fall trip). Each draft is a separate trip idea.

### Draft Cap (NEW — from reviews)

Per-user draft limit of 10. Reject with 429 if exceeded:
```
const draftCount = await prisma.trip.count({ where: { userId, status: "draft" } });
if (draftCount >= 10) return 429 "Too many saved drafts"
```

### Double-Submit Guard (NEW — from reviews)

Ref-based lock in onboarding to prevent duplicate draft creation:
- `isDraftSaving.current = true` before fetch, cleared on resolve/reject
- `draftIdRef.current` stores the draft ID — second click is a no-op if already set
- Same pattern as existing `didPrefill` ref guard

### Failure Handling

If the draft POST fails mid-onboarding:
- `console.error` + subtle non-blocking toast ("Couldn't save your progress yet")
- Toast uses `data-testid="draft-save-error"` for testability
- User continues through remaining steps normally
- On completion: if `draftIdRef.current` exists, PATCH to promote. If not, fall back to existing full `POST /api/trips` flow. Trip gets created either way.

## Onboarding Resume Flow

URL: `/onboarding?resume=<tripId>`

### Input Validation (NEW — from reviews)

Validate UUID format before making API call:
```
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
if (resumeId && !UUID_RE.test(resumeId)) {
  router.replace("/onboarding", { scroll: false });
  return;
}
```

### Flow

1. Load draft trip data from `GET /api/trips/<tripId>` (works because draft has TripMember row)
2. **Verify `trip.status === "draft"`** (NEW — from reviews). If not draft, redirect to `/trip/<tripId>` instead of loading into onboarding.
3. Pre-fill city and dates, skip those steps
4. Jump to name step (first unfilled step)
5. On completion: `PATCH /api/trips/<tripId>` with name + template + personaSeed + `status: "planning"` (promotes the draft)
6. `router.replace` clears `?resume=` param from URL after loading

### PATCH Endpoint Expansion

Current PATCH only accepts `name`, `status`, `planningProgress`. Must add: `startDate`, `endDate`, `mode`, `presetTemplate`, `personaSeed` to `updateTripSchema`. These fields are only writable per the field-level guards above (draft status only for most).

### Generation on Promotion (NEW — from reviews)

Extract `generateItinerary` call into a shared helper used by both POST and PATCH. When PATCH detects `draft → planning` transition, fire generation after the status update. Response shape must match POST: `{ trip, generated }`.

## Pre-Existing Fix: GET /api/trips List (from reviews)

Add `status: "joined"` filter to the TripMember query in `GET /api/trips`:
```
where: { userId, status: "joined" }
```
Prevents declined/removed memberships from leaking trips into dashboard.

## Pre-Existing Fix: Dashboard `cancelled` References

The enum has `archived`, not `cancelled`. Fix all test mocks and any remaining code references.

## Out of Scope

- **Draft trip detail page** — No browse/preview for drafts. Click goes to onboarding resume only. Revisit when activity data is richer.
- **Draft expiration** — Stale draft cleanup (archive after 90 days). Not MVP.
- **Draft nudge emails** — "You started planning Tokyo 3 days ago" via Resend. Good retention, not now.
- **"Save as idea" from shared trips** — Cool feature, not now.

## Implementation Order (from architect review)

### Phase 1: Foundation (no UI changes)
1. **State machine validator** — `lib/trip-status.ts`: `validateTransition(current, requested) → boolean`, `VALID_TRANSITIONS` map, `WRITABLE_BY_STATUS` map
2. **Wire into PATCH handler** — transition validation + field-level guards
3. **Extract generation helper** — shared `maybeGenerateItinerary()` used by POST and PATCH
4. **Fix GET /api/trips** — add `status: "joined"` filter
5. **Tests** for state machine, PATCH guards, generation trigger

### Phase 2: Draft API
6. **`POST /api/trips/draft`** — creates draft + TripMember, draft cap enforcement
7. **Draft creation Zod schema** — validate required fields
8. **Tests** for draft endpoint

### Phase 3: Dashboard UI
9. **`DraftIdeaCard` component**
10. **Dashboard page** — conditional card rendering, ordering (hero first, drafts after)
11. **Fix `cancelled` → `archived`** in test mocks
12. **Tests** for dashboard with drafts

### Phase 4: Onboarding Integration
13. **Draft save on dates advance** — fetch call in goNext, ref guards, toast on failure
14. **Resume flow** — `?resume=<tripId>`, UUID validation, status check, pre-fill, step skip
15. **Completion branching** — PATCH if draftId exists, POST fallback if not
16. **Tests** for onboarding draft save, resume, fallback

No schema migration needed. `draft` exists in the enum, all saved fields already exist on the Trip model.
