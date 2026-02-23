# M-005: Vote API Route

## Description
Track 2 backend: Create vote endpoint + Zod schema + tests.

## Task

### 1. Zod Schema (`apps/web/lib/validations/vote.ts`)
```typescript
import { z } from "zod";

export const voteSchema = z.object({
  vote: z.enum(["yes", "no", "maybe"]),
});
```

### 2. POST /api/slots/[slotId]/vote/route.ts (auth required, joined member)
- **Auth pattern (V4):** Resolve slot -> trip from DB using nested query (copy from slot status route):
  ```typescript
  const slot = await prisma.itinerarySlot.findUnique({
    where: { id: slotId },
    include: { trip: { include: { members: { where: { userId, status: "joined" } } } } },
  });
  ```
  401 if no session, 404 if slot not found or user not a joined member
- Parse body with `voteSchema`
- **Serializable transaction (V10):** All vote logic inside `prisma.$transaction`:
  1. Read current `voteState` (or initialize: `{ state: "voting", votes: {}, updatedAt: new Date().toISOString() }`)
  2. Set `voteState.votes[userId] = vote`
  3. Set `voteState.updatedAt = new Date().toISOString()`
  4. If first vote and state was null/proposed: set `voteState.state = "voting"`
  5. Count quorum: `prisma.tripMember.count({ where: { tripId: slot.tripId, status: "joined" } })`
  6. Count votes cast: `Object.keys(voteState.votes).length`
  7. If all voted:
     - Count yes votes: votes where value === "yes"
     - **Threshold: 70% means yes-only.** `yesCount / totalMembers >= 0.7`
     - If >= 70%: set `voteState.state = "confirmed"`, update `slot.status = "confirmed"`
     - If < 70%: set `voteState.state = "contested"`, update `slot.isContested = true`
  8. Update slot with new voteState
  9. Log BehavioralSignal: `vote_cast` with signalValue (yes=1.0, maybe=0.5, no=-1.0)
- **Response wrapper (C1):** Return `{ success: true, data: { voteState, slotStatus: slot.status } }` (matches slot-family convention)

### 3. Tests (`apps/web/__tests__/api/vote.test.ts`)
Using auth factory from M-003:
- Auth: no session -> 401, not member -> 404, not joined -> 404
- Validation: invalid vote value -> 400
- Vote logic: first vote initializes state, subsequent votes update, overwrites previous vote by same user
- Quorum: doesn't auto-confirm until ALL members voted
- Threshold: 2/3 yes with 3 members = 66.7% -> contested (not >= 70%)
- Threshold: 3/4 yes with 4 members = 75% -> confirmed (>= 70%)
- Maybe handling: 2 yes + 1 maybe with 3 members = 66.7% yes -> contested (maybe doesn't count as yes)
- Signal logging: vote_cast logged with correct signalValue
- Target: 20-25 tests

## Output
apps/web/lib/validations/vote.ts
apps/web/app/api/slots/[slotId]/vote/route.ts
apps/web/__tests__/api/vote.test.ts

## Zone
api

## Dependencies
M-002, M-003

## Priority
80

## Target Files
- apps/web/lib/validations/vote.ts
- apps/web/app/api/slots/[slotId]/vote/route.ts
- apps/web/__tests__/api/vote.test.ts

## Files
- docs/plans/2026-02-22-feature-units-sprint.md (Track 2 spec)
- docs/plans/2026-02-22-feature-units-review-notes.md (V4, V10, C1, threshold decision)
- apps/web/app/api/slots/[slotId]/status/route.ts (auth pattern reference — copy the nested trip.members query)
- apps/web/app/api/slots/[slotId]/swap/route.ts (response wrapper reference — uses { success: true, data })
