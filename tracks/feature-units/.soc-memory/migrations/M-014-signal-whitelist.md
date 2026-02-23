# M-014: Update Signal Type Whitelist

## Description
Update the VALID_SIGNAL_TYPES whitelist in the behavioral signal route to include the 9 new enum values.

## Task

### 1. Update whitelist (`apps/web/app/api/signals/behavioral/route.ts`)
- Find the `VALID_SIGNAL_TYPES` array/set (around lines 14-40)
- Add these 9 new values:
  ```typescript
  "vote_cast",
  "invite_accepted",
  "invite_declined",
  "trip_shared",
  "trip_imported",
  "packing_checked",
  "packing_unchecked",
  "mood_reported",
  "slot_moved",
  ```
- Keep existing values untouched
- Maintain alphabetical or grouped ordering consistent with existing style

### 2. Test
- Add a test in `apps/web/__tests__/api/signals-whitelist.test.ts` that verifies `VALID_SIGNAL_TYPES` contains all values from the Prisma SignalType enum
- This is a sync test — if someone adds a new enum value but forgets the whitelist, this test catches it
- Pattern: import the enum values (or hardcode the expected list) and assert containment

## Output
apps/web/app/api/signals/behavioral/route.ts
apps/web/__tests__/api/signals-whitelist.test.ts

## Zone
infra

## Dependencies
M-001

## Priority
70

## Target Files
- apps/web/app/api/signals/behavioral/route.ts
- apps/web/__tests__/api/signals-whitelist.test.ts
