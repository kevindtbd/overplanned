# M-013: API Route Handler Tests

## Description
The trips API route handlers (GET/POST) have zero test coverage beyond Zod schema validation. Auth bypass, database errors, and response shape are all untested. P3 priority.

## Task
Create `apps/web/__tests__/api/trips-route.test.ts` (12 tests):

Mock setup:
- Mock `getServerSession` from `next-auth`
- Mock the Prisma singleton (`@/lib/prisma`) — must mock after M-001 is applied
- Mock `crypto.randomUUID`

GET tests:
- returns 401 when no session
- returns trips for authenticated user (correct Prisma query, response shape)
- returns empty array when user has no trips
- returns 500 when Prisma throws
- orders trips by createdAt desc

POST tests:
- returns 401 when no session
- returns 400 for invalid JSON body
- returns 400 for missing required fields
- creates trip and organizer member on valid input
- returns 201 with created trip
- returns 500 when Prisma throws

Verify: `npx vitest run apps/web/__tests__/api/trips-route.test.ts` — all tests pass.

## Output
apps/web/__tests__/api/trips-route.test.ts

## Zone
test

## Dependencies
M-001, M-007

## Priority
45

## Target Files
- apps/web/__tests__/api/trips-route.test.ts

## Files
- docs/plans/dashboard-audit-compound.md
