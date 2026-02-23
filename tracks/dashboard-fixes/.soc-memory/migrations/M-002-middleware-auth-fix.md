# M-002: Fix Middleware Auth Bypass

## Description
Remove `/dashboard` and `/dashboard/` from PUBLIC_PATHS in middleware. The prefix-match logic makes all `/dashboard/*` sub-routes public. Critical security fix — P0 priority.

## Task
Edit `apps/web/middleware.ts`:
- Remove `"/dashboard"` and `"/dashboard/"` from the `PUBLIC_PATHS` array
- These were added for local dev auth bypass but are a production security risk
- The prefix-match logic (`p.endsWith("/") && pathname.startsWith(p)`) means `/dashboard/` would make ALL future sub-routes public

If dev-mode access is needed, gate it:
```typescript
...(process.env.NODE_ENV === 'development' ? ['/dashboard', '/dashboard/'] : [])
```

Verify: The middleware still redirects unauthenticated users away from `/dashboard`. Existing public paths (`/`, `/auth/signin`, `/api/auth/`, `/s/`, `/invite/`) still work.

## Output
apps/web/middleware.ts

## Zone
security

## Dependencies
none

## Priority
100

## Target Files
- apps/web/middleware.ts

## Files
- docs/plans/dashboard-audit-compound.md
