# M-003: Stop Exposing Member Emails in Trip API

## Description
Remove `email: true` from the trip detail API member select. Any trip member can currently see all other members' email addresses — PII exposure. P0 priority.

## Task
Edit `apps/web/app/api/trips/[id]/route.ts`:
- In the GET handler's Prisma query, change the `user` select within `members` to remove `email: true`
- Keep: `id: true`, `name: true`, `image: true`
- Remove: `email: true`

Then update the client-side type in `apps/web/app/trip/[id]/page.tsx`:
- Find the `ApiTrip` interface's member user type
- Remove `email: string` from the user shape
- Check if email is used anywhere in the component's JSX — if so, remove those references

Verify: `GET /api/trips/[id]` response no longer contains member email addresses. TypeScript compiles clean. Trip detail page renders without errors.

## Output
apps/web/app/api/trips/[id]/route.ts

## Zone
security

## Dependencies
M-001

## Priority
95

## Target Files
- apps/web/app/api/trips/[id]/route.ts
- apps/web/app/trip/[id]/page.tsx

## Files
- docs/plans/dashboard-audit-compound.md
