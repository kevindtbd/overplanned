# JWT Callback + Dev-Login Fix

**Date**: 2026-02-25
**Status**: Approved
**Bug**: All dashboard API routes return 401 after logout + re-login

## Root Causes

### 1. JWT callback doesn't fetch custom user fields
`lib/auth/config.ts` jwt callback does `token.subscriptionTier = user.subscriptionTier`
but PrismaAdapter only passes standard OAuth fields (id, name, email, image).
Custom fields are undefined in the token -> `hasAccess(undefined)` fails -> 401.

### 2. dev-login creates database sessions but app uses JWT strategy
`app/api/auth/dev-login/route.ts` writes a UUID to the Session table and sets it
as a cookie. But `strategy: "jwt"` means NextAuth expects a signed JWT in the cookie,
not a UUID. Verification fails -> null session -> 401.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| JWT callback DB fetch | First sign-in only | Tier changes are rare (manual SQL). 30-day JWT expiry is natural refresh. No extra DB query per request |
| Dev-login fix | Mint real JWT via NextAuth encode() | Matches production JWT strategy. No session table needed |

## Changes

### File 1: `apps/web/lib/auth/config.ts`
- In `jwt` callback, when `user` is present (first sign-in), fetch full user record from DB
- Assign `subscriptionTier` and `systemRole` from the DB record, not the adapter's user object

### File 2: `apps/web/app/api/auth/dev-login/route.ts`
- Remove: `prisma.session.create()` (wrong for JWT strategy)
- Add: Import `encode` from `next-auth/jwt`
- Create a proper JWT payload with id, subscriptionTier, systemRole, email, name
- Encode it with `NEXTAUTH_SECRET`
- Set the encoded JWT as the `next-auth.session-token` cookie
