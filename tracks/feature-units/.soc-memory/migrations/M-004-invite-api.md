# M-004: Invite API Routes

## Description
Track 1 backend: Create all 3 invite endpoints + Zod validation schema + tests.

## Task

### 1. Zod Schema (`apps/web/lib/validations/invite.ts`)
```typescript
import { z } from "zod";

export const inviteCreateSchema = z.object({
  maxUses: z.number().int().min(1).max(100).default(10),
  expiresInDays: z.number().int().min(1).max(30).default(7),
});

export const joinQuerySchema = z.object({
  token: z.string().min(10).max(64).regex(/^[A-Za-z0-9_-]+$/),
});
```

### 2. GET /api/invites/preview/[token]/route.ts (public)
- Validate token format (regex + 64 char max)
- Look up `InviteToken` including `trip` relation (select: destination, city, country, startDate, endDate)
- Check: not expired (`expiresAt > now()`), not revoked (`revokedAt === null`), `usedCount < maxUses`
- Count trip members: `prisma.tripMember.count({ where: { tripId, status: "joined" } })`
- Get organizer name: `prisma.tripMember.findFirst({ where: { tripId, role: "organizer" }, include: { user: { select: { name: true } } } })`
- Return flat JSON: `{ tripId, destination, city, country, startDate, endDate, memberCount, valid: true, organizerName }`
- If token invalid/expired: return `{ valid: false }` with 200 (not 404 — don't leak existence)
- Apply rate limiter: public tier (30 req/min by IP)

### 3. POST /api/trips/[id]/join/route.ts (auth required)
- Read token from query param: `new URL(request.url).searchParams.get("token")`
- Auth: `getServerSession` -> 401 if null
- **Atomic accept (V1 TOCTOU fix):** Inside `prisma.$transaction`:
  ```typescript
  const updated = await prisma.$queryRaw`
    UPDATE "InviteToken" SET "usedCount" = "usedCount" + 1
    WHERE token = ${token} AND "usedCount" < "maxUses"
    AND "revokedAt" IS NULL AND "expiresAt" > NOW()
    AND "tripId" = ${tripId}
    RETURNING *
  `;
  ```
  If no rows returned -> 409 (token exhausted/expired/wrong trip)
- Check user not already a TripMember for this trip -> 409 if exists
- Create TripMember: `{ tripId, userId, role: inviteToken.role, status: "joined", joinedAt: new Date() }`
- Log BehavioralSignal: `invite_accepted` (tripPhase from trip.status)
- Return: `{ tripId }`
- **Token security (V2):** Token generation uses `crypto.randomBytes(32).toString('base64url')`

### 4. POST /api/trips/[id]/invite/route.ts (auth required, organizer only)
- Auth: session + membership check (organizer + joined)
- Validate trip mode is "group" -> 400 if solo
- Parse body with `inviteCreateSchema`
- Generate token: `crypto.randomBytes(32).toString('base64url')`
- Create InviteToken: `{ tripId, token, createdBy: userId, maxUses, expiresAt, role: "member" }`
- Return: `{ token, inviteUrl: \`${baseUrl}/invite/${token}\`, expiresAt }`

### 5. Tests (`apps/web/__tests__/api/invite.test.ts`)
Write tests using the auth factory from M-003:
- Preview: valid token returns trip info, expired token returns `valid: false`, rate limiting works
- Join: auth required, token validation, atomic accept (can't exceed maxUses), duplicate member check, signal logging
- Create invite: organizer only, group mode only, token format validation
- Target: 20-25 tests

## Output
apps/web/lib/validations/invite.ts
apps/web/app/api/invites/preview/[token]/route.ts
apps/web/app/api/trips/[id]/join/route.ts
apps/web/app/api/trips/[id]/invite/route.ts
apps/web/__tests__/api/invite.test.ts

## Zone
api

## Dependencies
M-002, M-003

## Priority
80

## Target Files
- apps/web/lib/validations/invite.ts
- apps/web/app/api/invites/preview/[token]/route.ts
- apps/web/app/api/trips/[id]/join/route.ts
- apps/web/app/api/trips/[id]/invite/route.ts
- apps/web/__tests__/api/invite.test.ts

## Files
- docs/plans/2026-02-22-feature-units-sprint.md (Track 1 spec)
- docs/plans/2026-02-22-feature-units-review-notes.md (V1, V2 security fixes)
- apps/web/app/api/trips/[id]/route.ts (auth pattern reference)
- apps/web/app/invite/[token]/InviteJoinButton.tsx (existing UI — uses POST /api/trips/${tripId}/join?token=...)
