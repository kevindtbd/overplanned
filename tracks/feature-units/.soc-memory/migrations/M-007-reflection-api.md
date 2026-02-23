# M-007: Reflection API Route

## Description
Track 4 backend: Create reflection submit endpoint + Zod schema + tests.

## Task

### 1. Zod Schema (`apps/web/lib/validations/reflection.ts`)
```typescript
import { z } from "zod";

const stripHtml = (val: string) => val.replace(/<[^>]*>/g, "").trim();

export const reflectionSchema = z.object({
  ratings: z.array(
    z.object({
      slotId: z.string().uuid(),
      rating: z.enum(["loved", "skipped", "missed"]),
    })
  ).min(1).max(100),
  feedback: z.string().max(500).transform(stripHtml).optional(),
});
```

### 2. POST /api/trips/[id]/reflection/route.ts (auth required, joined member)
- Auth: session + membership (joined member, any role)
- Validate trip status: must be "completed" or "active" -> 409 if not
- Parse body with `reflectionSchema` (V7: HTML stripped via Zod transform)
- **UserId from session (V8):** Key is ALWAYS `session.user.id`, never from request body
- **Read-merge-write (test risk #2):** Inside `prisma.$transaction`:
  1. Read current `trip.reflectionData` (may be null)
  2. Parse as object (or initialize `{}`)
  3. Merge: `reflectionData[userId] = { ratings: body.ratings, feedback: body.feedback, submittedAt: new Date().toISOString() }`
  4. Update trip: `prisma.trip.update({ where: { id: tripId }, data: { reflectionData: merged } })`
  5. Log BehavioralSignals for each rating:
     - loved -> `post_loved` (signalValue: 1.0)
     - skipped -> `post_skipped` (signalValue: -0.5)
     - missed -> `post_missed` (signalValue: 0.8)
     Each signal includes `activityNodeId` from the slot's linked node
- Return flat JSON: `{ submitted: true }`

### 3. Tests (`apps/web/__tests__/api/reflection.test.ts`)
- Auth: no session -> 401, not member -> 404
- Status: draft trip -> 409, planning trip -> 409, active -> 200, completed -> 200
- Validation: empty ratings -> 400, HTML in feedback stripped, oversized feedback -> 400
- **Critical: Multi-user merge** — first user submits, second user submits, both preserved
- **Critical: Same user re-submits** — overwrites their own entry, doesn't affect others
- Signal logging: correct signal types + values for each rating
- UserId from session: body with different userId key is ignored
- Target: 15-20 tests

## Output
apps/web/lib/validations/reflection.ts
apps/web/app/api/trips/[id]/reflection/route.ts
apps/web/__tests__/api/reflection.test.ts

## Zone
api

## Dependencies
M-002, M-003

## Priority
80

## Target Files
- apps/web/lib/validations/reflection.ts
- apps/web/app/api/trips/[id]/reflection/route.ts
- apps/web/__tests__/api/reflection.test.ts

## Files
- docs/plans/2026-02-22-feature-units-sprint.md (Track 4 spec)
- docs/plans/2026-02-22-feature-units-review-notes.md (V7, V8, test risk #2)
- apps/web/app/api/trips/[id]/route.ts (auth pattern reference)
