# Group Mode UX Design

**Date**: 2026-02-23
**Status**: Approved (post-review v2)

## Problem

Group mode is fundamentally broken. There's no way to select it during onboarding (hardcoded to "solo"), the settings toggle silently drops the mode change for planning trips, and even when group mode is active there's no visual payoff — no invite prompt, no badge, no feedback.

## Design

### 1. Onboarding — Mode Toggle in Name Step

Inline solo/group toggle at the bottom of the existing name step (no separate step). Two large cards: Solo (default, pre-selected) and Group. Group card subtext: "Friends can vote on activities and suggest changes."

State: `const [tripMode, setTripMode] = useState<"solo" | "group">("solo")` — default is `"solo"` string, NOT null.

Step order unchanged: `fork → backfill → destination → dates → legReview → name → dna → template`

The `tripMode` value replaces the hardcoded `"solo"` in `handleComplete()` payloads (both draft promotion PATCH at line 472 and fresh POST at line 493).

**Files**: `apps/web/app/onboarding/page.tsx` (no new component file)

### 2. Trip Detail — Invite Crew Card

New `InviteCrewCard` component renders after WelcomeCard, before the day header `<div>` (line 528 area). NOT before DayNavigation — WelcomeCard is already below DayNavigation in the DOM.

Conditions:
- `trip.mode === "group"`
- `myRole === "organizer"`
- Fewer than 2 joined members (filter `trip.members` by `status === "joined"`)
- Not dismissed in sessionStorage (`dismiss-invite-${tripId}`)

Contents:
- Heading: "Invite your crew"
- Subtext: "Share a link so friends can vote on activities and suggest changes."
- "Copy invite link" CTA — calls `POST /api/trips/{id}/invite`, copies URL, shows "Copied!" for 2s
- Error state: if API fails, show "Could not create invite link" in red text below button
- Clipboard fallback: if `navigator.clipboard.writeText` fails, show the URL as selectable text
- Dismiss X — stores in sessionStorage (`dismiss-invite-${tripId}`)

Design tokens: `warm-surface` bg, `warm-border`, `font-heading` title (use `font-sora`), `font-dm-mono` subtext, `bg-accent text-white` CTA button.

**Files**: new `apps/web/components/trip/InviteCrewCard.tsx`, edit `apps/web/app/trip/[id]/page.tsx`

### 3. Settings Mode Switch — Toast Feedback via onTripUpdate

When TripSettings saves a mode change:
1. Settings panel closes (existing)
2. Toast appears: "Switched to group mode" / "Switched to solo mode". Auto-dismisses after 3s.
3. Trip re-fetches, page re-renders with group features visible/hidden.
4. sessionStorage dismiss flag (`dismiss-invite-${tripId}`) is cleared on mode change.

**Callback pattern** (per architect review): NO separate `onModeChange` callback. Instead, modify `onTripUpdate` to accept optional dirty fields:

```typescript
onTripUpdate: (dirtyFields?: Record<string, string>) => void
```

TripSettings calls `onTripUpdate(dirty)` instead of `onTripUpdate()`. Page inspects `dirtyFields?.mode` to trigger toast and clear dismiss flag. TripSettings stays agnostic to toast concerns.

Toast: simple local-state component in page.tsx. Fixed position bottom, fade in/out, 3s auto-dismiss. No library.

**Files**: edit `apps/web/components/trip/TripSettings.tsx`, edit `apps/web/app/trip/[id]/page.tsx`

### 4. Header Group Badge

When `trip.mode === "group"`, prepend a "Group" pill badge to the header subline. `bg-accent text-white font-dm-mono text-[10px] uppercase rounded-full px-2 py-0.5`.

```
Solo:  Tokyo, Japan | 3 days | 2/12 confirmed
Group: [Group] · Tokyo, Japan | 3 days | 2/12 confirmed
```

**Files**: edit `apps/web/app/trip/[id]/page.tsx`

### 5. Bug Fix — Writable Fields (already applied)

Added `"mode"` to `WRITABLE_BY_STATUS.planning` in `lib/trip-status.ts`. Without this, PATCH silently dropped mode changes for planning trips.

### 6. Security Fix — Invite URL Origin (pre-existing, from security review)

The invite route constructs URLs from `req.headers.get("origin")` which is attacker-controllable. Fix: use `process.env.NEXT_PUBLIC_APP_URL` instead.

**Files**: edit `apps/web/app/api/trips/[id]/invite/route.ts`

## Scope

- 6 touchpoints (5 planned + 1 security fix)
- No new API endpoints
- No schema changes
- 1 new component (InviteCrewCard)
- 1 new inline component (Toast, in page.tsx)
- 4 edited files (onboarding page, trip detail page, TripSettings, invite route)

## Test Plan

### Onboarding (5 new tests in existing file)
1. Default mode is "solo" in PATCH/POST payload
2. Toggle to group — payload contains `mode: "group"`
3. Toggle back to solo — payload contains `mode: "solo"`
4. Solo card is pre-selected visually on mount
5. Group card becomes selected on click

### TripSettings (4 new tests in existing file)
1. `onTripUpdate` called with dirty fields including `mode` when mode changes
2. `onTripUpdate` called WITHOUT mode in dirty fields when only name changes
3. Cancel does not call `onTripUpdate`
4. Component renders and saves correctly when `onTripUpdate` ignores dirty fields

### GroupMode.test.tsx (16 new tests)
**InviteCrewCard rendering (5):**
1. Shows for group + organizer + <2 joined members
2. Hides for solo mode
3. Hides for non-organizer
4. Hides when 2+ joined members
5. Hides when dismissed in sessionStorage

**InviteCrewCard behavior (4):**
6. CTA calls POST invite API
7. Shows "Copied!" after success
8. Shows error on API failure
9. Dismiss X writes sessionStorage and hides card

**Group badge (2):**
10. Badge renders for group mode
11. Badge absent for solo mode

**Toast (4):**
13. Toast renders after mode change
14. Toast auto-dismisses after 3s
15. Correct text for solo/group
16. Dismiss flag cleared on mode change

### Test setup notes
- Mock `navigator.clipboard.writeText` in beforeEach for invite CTA tests
- Member shape: `{ id, userId, role, status: "joined", user: { id, name, avatarUrl } }`
- Use `vi.useFakeTimers()` for toast and "Copied!" auto-dismiss tests

## Out of Scope

- Onboarding invite step (decided against — inline card is sufficient)
- Confirmation dialog before mode switch (toast is the feedback)
- Group-specific onboarding DNA questions
