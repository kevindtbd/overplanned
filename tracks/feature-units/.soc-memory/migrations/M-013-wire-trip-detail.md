# M-013: Wire Trip Detail Page

## Description
Phase 2 UI wiring: Single sequential pass to wire VotePanel, PackingList, and mood trigger into trip detail page. This is the merge-conflict-prone file that must be edited in one pass.

## Task

### 1. Wire VotePanel (`apps/web/app/trip/[id]/page.tsx`)
- When `trip.mode === "group"`:
  - For each slot in voting/proposed state, render `<VotePanel>` component
  - Import VotePanel from `@/components/group/voting/VotePanel`
  - Map props from trip data:
    - `slotId`: slot.id
    - `voteState`: slot.voteState (parsed JSON)
    - `memberVotes`: map voteState.votes userId keys to member names/avatars from trip.members
    - `currentUserId`: session.user.id (from useTripDetail hook)
    - `isComplete`: voteState.state === "confirmed" || "contested"
  - `onVote` handler: POST to `/api/slots/${slotId}/vote` with `{ vote }`, then refetch trip data
- Only show for group mode trips

### 2. Wire PackingList
- Import PackingList from `@/components/trip/PackingList`
- Render below slots section, above settings
- Only visible for planning/active trips
- Pass: `tripId`, `packingList: trip.packingList`, `isOrganizer: myRole === "organizer"`

### 3. Wire Mood Trigger
- For active trips, add a "Not feeling it?" button on each confirmed slot card
- Button triggers: POST `/api/trips/${tripId}/pivot` with `{ slotId, trigger: "user_mood" }`
- On success: open PivotDrawer with the returned alternatives
- Import PivotDrawer if not already imported
- Only show for active trips, only on confirmed/active slots

### 4. Wire Invite + Share Buttons
- Add "Invite" button in trip header:
  - Only visible for organizer + group mode
  - POST `/api/trips/${tripId}/invite` -> show share sheet with invite URL
- Add "Share" button in trip header:
  - Only visible for organizer
  - POST `/api/trips/${tripId}/share` -> show share sheet with share URL

### 5. Important Notes
- This file was already refactored to use `useTripDetail` hook — leverage existing state management
- Keep the file organized: imports at top, hooks, then render sections
- Follow existing slot card rendering pattern for vote/mood additions
- Do NOT break existing functionality (FAB, WelcomeCard, day nav, progress counter)

## Output
apps/web/app/trip/[id]/page.tsx

## Zone
ui

## Dependencies
M-005, M-008, M-009

## Priority
50

## Target Files
- apps/web/app/trip/[id]/page.tsx

## Files
- apps/web/components/group/voting/VotePanel.tsx (component interface reference)
- apps/web/components/trip/PackingList.tsx (component interface reference — created in M-008)
- apps/web/lib/hooks/useTripDetail.ts (existing hook with trip state)
