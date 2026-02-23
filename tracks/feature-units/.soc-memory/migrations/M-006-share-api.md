# M-006: Share API Routes

## Description
Track 3 backend: Create all 3 share endpoints + Zod schema + tests.

## Task

### 1. Zod Schema (`apps/web/lib/validations/share.ts`)
```typescript
import { z } from "zod";

export const shareCreateSchema = z.object({
  expiresInDays: z.number().int().min(1).max(90).default(30),
});

export const importSchema = z.object({}).optional(); // No body needed, just auth
```

### 2. GET /api/shared/[token]/route.ts (public)
- Validate token format (regex + 64 char max)
- Look up `SharedTripToken` including trip + slots:
  ```typescript
  const token = await prisma.sharedTripToken.findUnique({
    where: { token: safeToken },
    include: {
      trip: {
        include: {
          slots: {
            include: { activityNode: true },
            orderBy: [{ dayNumber: "asc" }, { sortOrder: "asc" }],
          },
        },
      },
    },
  });
  ```
- Check: not expired, not revoked
- Increment `viewCount`: `prisma.sharedTripToken.update({ where: { id }, data: { viewCount: { increment: 1 } } })`
- Build response: group slots by dayNumber, strip PII (no member data, no voteState, no behavioral data)
- Return flat JSON: `{ trip: { name, destination, city, country, startDate, endDate }, slotsByDay: { "1": [...] } }`
- Apply rate limiter: public tier (30 req/min by IP)

### 3. POST /api/shared/[token]/import/route.ts (auth required)
- Auth: `getServerSession` -> 401
- Look up SharedTripToken + full trip data
- **Import limit (V9):** Check if user already imported from this token. Query trips where source metadata matches. Return 409 if already imported.
- Create new Trip (new UUID) with:
  - `userId: session.user.id`
  - `mode: "solo"` (always — imported trips start solo)
  - `status: "planning"`
  - Copy: name (append " (imported)"), destination, city, country, timezone, startDate, endDate, presetTemplate, personaSeed
  - Do NOT copy: members, groupId, fairnessState, affinityMatrix
- Create TripMember for importer: `{ role: "organizer", status: "joined", joinedAt: now() }`
- Clone ItinerarySlots: new UUIDs for each, reset `status: "proposed"`, clear `voteState`, `isLocked: false`, `wasSwapped: false`
- Increment `importCount` on SharedTripToken
- Log BehavioralSignal: `trip_imported`
- Return: `{ tripId }`

### 4. POST /api/trips/[id]/share/route.ts (auth required, organizer only)
- Auth: session + membership (organizer + joined)
- Generate token: `crypto.randomBytes(32).toString('base64url')`
- Create SharedTripToken: `{ tripId, token, createdBy: userId, expiresAt }`
- Return: `{ token, shareUrl: \`${baseUrl}/s/${token}\`, expiresAt }`

### 5. Tests (`apps/web/__tests__/api/share.test.ts`)
- View: valid token returns trip data, expired returns 404, strips PII, increments viewCount
- Import: auth required, clones with new UUIDs, mode always solo, import limit enforced, signals logged
- Create share: organizer only, generates secure token
- **Critical test (risk #5):** Cloned trip and all slots have NEW UUIDs (not copied from original)
- Target: 20-25 tests

## Output
apps/web/lib/validations/share.ts
apps/web/app/api/shared/[token]/route.ts
apps/web/app/api/shared/[token]/import/route.ts
apps/web/app/api/trips/[id]/share/route.ts
apps/web/__tests__/api/share.test.ts

## Zone
api

## Dependencies
M-002, M-003

## Priority
80

## Target Files
- apps/web/lib/validations/share.ts
- apps/web/app/api/shared/[token]/route.ts
- apps/web/app/api/shared/[token]/import/route.ts
- apps/web/app/api/trips/[id]/share/route.ts
- apps/web/__tests__/api/share.test.ts

## Files
- docs/plans/2026-02-22-feature-units-sprint.md (Track 3 spec)
- docs/plans/2026-02-22-feature-units-review-notes.md (V9 import limit)
- apps/web/app/api/trips/[id]/route.ts (auth pattern reference)
- apps/web/app/s/[token]/page.tsx (existing UI — data shape reference)
