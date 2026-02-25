# Auth / Beta Gate Flow Fix

**Date**: 2026-02-25
**Status**: Approved
**Bug**: Beta code -> Google login -> OAuth callback -> loops back to beta modal

## Root Cause

`betaValidated` state in `SignInContent` is `useState(false)` with no persistence.
When Google OAuth completes and redirects back to `/auth/signin`, React re-mounts,
state resets to `false`, beta modal reappears.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Pre-login persistence | localStorage `beta_validated` | Survives OAuth redirect. Not a security boundary — real access control is DB tier + JWT |
| Returning user with session | Auto-redirect to /dashboard | Standard pattern. No reason to show signin to authenticated users |
| Expired session (30d JWT) | Skip beta gate via localStorage | Already proved beta access on this device |
| Logout behavior | Keep localStorage | Logout = end session, not revoke beta. DB tier is the real gate |

## Changes

**Single file**: `apps/web/app/auth/signin/page.tsx`

1. Add `useSession` + `useRouter` imports
2. Add `useEffect` to auto-redirect authenticated users to `/dashboard`
3. Initialize `betaValidated` from localStorage (not bare `false`)
4. Persist `beta_validated` to localStorage on successful code entry

## Flow Map

- **First visit, no account**: middleware -> /auth/signin -> beta gate -> code validates -> localStorage set -> Google OAuth -> create user -> /dashboard
- **Returning, valid session**: /auth/signin -> useSession detects auth -> redirect /dashboard
- **Returning, expired session**: middleware -> /auth/signin -> localStorage has beta_validated -> skip gate -> Google OAuth -> /dashboard
- **After logout**: same as expired — localStorage persists, skip gate
- **New device**: full flow (no localStorage), set it again after beta code
- **Dev mode**: auto-bypass (unchanged)
