# M-009: Pivot API Routes

## Description
Track 6 backend: Create pivot creation + resolution endpoints, Zod schemas, and tests.

## Task

### 1. Zod Schemas (`apps/web/lib/validations/pivot.ts`)
```typescript
import { z } from "zod";

export const pivotCreateSchema = z.object({
  slotId: z.string().uuid(),
  trigger: z.enum(["user_mood", "user_request"]),
  reason: z.string().max(200).optional(),
});

export const pivotResolveSchema = z.object({
  outcome: z.enum(["accepted", "rejected"]),
  selectedNodeId: z.string().uuid().optional(),
});
```

### 2. POST /api/trips/[id]/pivot/route.ts (auth required, joined member)
- Auth: session + membership (joined member)
- Parse body with `pivotCreateSchema`
- Validate: trip status is "active" -> 409 if not
- Validate: slot belongs to trip, slot is confirmed or active -> 409 if not
- **Pivot caps (V11):** Count active pivots (status: "proposed"):
  - Max 3 per trip -> 409 "Too many active pivots"
  - Max 1 per slot -> 409 "Pivot already active for this slot"
- Fetch alternative ActivityNodes:
  ```typescript
  const alternatives = await prisma.activityNode.findMany({
    where: {
      city: trip.city,
      category: slot.activityNode.category, // same or adjacent
      status: "approved",
      id: { notIn: existingSlotNodeIds }, // not already in trip
    },
    take: 10, // fetch more than needed for scoring
  });
  ```
- Score alternatives:
  - `authorityScore * 0.4` + vibe tag overlap with `trip.personaSeed` * 0.4 + `Math.random() * 0.2`
  - Return top 3
  - Empty array is fine for unseeded cities
- Create PivotEvent: `{ tripId, slotId, triggerType: body.trigger, originalNodeId: slot.activityNodeId, alternativeIds: top3.map(a => a.id), status: "proposed" }`
- Log BehavioralSignal: `mood_reported`
- Return: `{ pivotEvent, alternatives }` (alternatives include: id, name, category, authorityScore, descriptionShort)

### 3. PATCH /api/trips/[id]/pivot/[pivotId]/route.ts (auth required, joined member)
- Auth: session + membership
- Parse body with `pivotResolveSchema`
- Look up PivotEvent: must belong to trip, status must be "proposed" -> 404/409
- **Validate selectedNodeId (test risk #4):** If outcome is "accepted", `selectedNodeId` must exist in `pivotEvent.alternativeIds` -> 400 if not
- Calculate `responseTimeMs`: `Date.now() - pivotEvent.createdAt.getTime()`
- Inside `prisma.$transaction`:
  - Update PivotEvent: `{ status: outcome, resolvedAt: new Date(), responseTimeMs, selectedNodeId }`
  - If accepted:
    - Update ItinerarySlot: `{ activityNodeId: selectedNodeId, wasSwapped: true, swappedFromId: pivotEvent.originalNodeId, pivotEventId: pivotEvent.id }`
    - **Reset voteState:** If slot had voting, set `voteState: null, isContested: false` (pivot on voted slot resets votes)
  - Log BehavioralSignal: `pivot_accepted` or `pivot_rejected`
- Return: `{ pivotEvent, updatedSlot }` (updatedSlot only if accepted)

### 4. Tests (`apps/web/__tests__/api/pivot.test.ts`)
- Auth: standard guards
- Create: validates trip is active, slot belongs to trip, pivot caps enforced (3 per trip, 1 per slot)
- Scoring: returns top 3, excludes nodes already in trip, handles zero alternatives
- Resolve: validates selectedNodeId against alternativeIds, calculates responseTimeMs
- Accept: swaps slot, resets voteState, logs pivot_accepted
- Reject: doesn't swap, logs pivot_rejected
- Target: 20-25 tests

## Output
apps/web/lib/validations/pivot.ts
apps/web/app/api/trips/[id]/pivot/route.ts
apps/web/app/api/trips/[id]/pivot/[pivotId]/route.ts
apps/web/__tests__/api/pivot.test.ts

## Zone
api

## Dependencies
M-002, M-003

## Priority
75

## Target Files
- apps/web/lib/validations/pivot.ts
- apps/web/app/api/trips/[id]/pivot/route.ts
- apps/web/app/api/trips/[id]/pivot/[pivotId]/route.ts
- apps/web/__tests__/api/pivot.test.ts

## Files
- docs/plans/2026-02-22-feature-units-sprint.md (Track 6 spec)
- docs/plans/2026-02-22-feature-units-review-notes.md (V11 pivot caps, test risk #4)
- apps/web/app/api/slots/[slotId]/status/route.ts (slot auth pattern reference)
