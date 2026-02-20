# M-004: Auth + Session Management

## Description
Implement NextAuth.js with Google OAuth and database-backed sessions. No JWT. Sessions stored in Postgres with idle timeout and concurrent session limits.

## Task
1. Install next-auth and @auth/prisma-adapter

2. Configure NextAuth:
   - Provider: Google OAuth only
   - Adapter: Prisma adapter (uses Session, Account, User, VerificationToken tables)
   - Session strategy: "database" (NOT "jwt")
   - Session config: maxAge 30 days, updateAge (idle reset) 7 days

3. Implement concurrent session limit: max 5 sessions per user
   - On new session creation, if user has 5+ active sessions, delete the oldest
   - Query Session table by userId, order by createdAt

4. Create getEffectiveTier() utility:
   - Returns user's access tier based on role field
   - Access check: ['beta', 'lifetime', 'pro'].includes(user.role)

5. Create FEATURE_GATES config constant:
   - Maps feature names to required tiers
   - All features accessible to beta/lifetime/pro for now (beta mode)

6. Auth middleware for Next.js API routes:
   - Verify session on every protected route
   - Update User.lastActiveAt on every authenticated request

7. Protected route wrapper component for client-side route protection

8. Google OAuth callback must create User row with role: 'beta' on first login

Deliverable: Google login → session row in DB → user row with beta tier → session expires correctly → concurrent limit works.

## Output
apps/web/app/api/auth/[...nextauth]/route.ts

## Zone
auth

## Dependencies
- M-002

## Priority
80

## Target Files
- apps/web/app/api/auth/[...nextauth]/route.ts
- apps/web/lib/auth/config.ts
- apps/web/lib/auth/session.ts
- apps/web/lib/auth/gates.ts
- apps/web/middleware.ts
- apps/web/components/auth/ProtectedRoute.tsx

## Files
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
