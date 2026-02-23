# M-007: Fix `as never` Type Casts in API Routes

## Description
Multiple `as never` casts suppress TypeScript enum validation in trips API routes. If Prisma enums drift from Zod schemas, errors surface at runtime instead of compile time. P1 priority.

## Task
Edit `apps/web/app/api/trips/route.ts`:
- Lines 66, 73, 74: Remove `as never` casts on `mode`, `role`, and `status`
- Import the Prisma enum types: `import { TripMode, TripMemberRole, TripStatus } from "@prisma/client"`
- Cast properly: `mode as TripMode`, `"organizer" as TripMemberRole`, `"active" as TripStatus`
- OR: update the Zod schema to use the Prisma enum values directly so no cast is needed

Edit `apps/web/app/api/trips/[id]/route.ts`:
- Line 144: Remove `as never` on `status`
- Use `status as TripStatus` or align Zod enum with Prisma enum

Check which Prisma enum names are correct by reading `prisma/schema.prisma` for the enum definitions.

Verify: `npx tsc --noEmit` passes without the `as never` casts. All existing tests pass.

## Output
apps/web/app/api/trips/route.ts
apps/web/app/api/trips/[id]/route.ts

## Zone
api

## Dependencies
M-001

## Priority
75

## Target Files
- apps/web/app/api/trips/route.ts
- apps/web/app/api/trips/[id]/route.ts
- prisma/schema.prisma

## Files
- docs/plans/dashboard-audit-compound.md
