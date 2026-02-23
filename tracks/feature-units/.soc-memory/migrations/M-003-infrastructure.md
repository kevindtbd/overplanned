# M-003: Rate Limiter + Auth Hardening + Test Helpers

## Description
Infrastructure work from Track 0: rate limiting middleware, NextAuth redirect callback fix, and shared test helpers.

## Task

### 1. Rate Limiter (`apps/web/lib/rate-limit.ts`)
Create a basic in-memory rate limiter (no Redis needed for beta):
- Token bucket or sliding window algorithm using a `Map<string, { count: number, resetAt: number }>`
- Export `rateLimit(key: string, limit: number, windowMs: number): { allowed: boolean, remaining: number, resetAt: number }`
- Three tiers:
  - Public: 30 req/min (invite preview, shared trip view)
  - Authenticated writes: 10 req/min
  - LLM calls: 3 req/hour (packing generation)
- Export helper `rateLimitResponse()` that returns a `NextResponse` with 429 status + `Retry-After` header
- Clean up expired entries periodically (every 60s) to prevent memory leak
- Key by IP for public endpoints, by userId for authenticated endpoints

### 2. NextAuth Redirect Callback (`apps/web/lib/auth/config.ts`)
Add a `redirect` callback to the NextAuth config that validates redirect URLs:
```typescript
redirect: async ({ url, baseUrl }) => {
  // Allow relative URLs
  if (url.startsWith("/")) return `${baseUrl}${url}`;
  // Allow same-origin URLs
  if (new URL(url).origin === baseUrl) return url;
  // Default to base
  return baseUrl;
},
```

### 3. Test Helpers
Create `apps/web/__tests__/helpers/transaction-mock.ts`:
- Export `mockTransaction()` that creates a mock `prisma.$transaction` that executes callbacks immediately
- Handle both array and callback transaction styles

Create `apps/web/__tests__/helpers/auth-factory.ts`:
- Export `mockAuthSession(userId?: string)` — returns a mock session object
- Export `mockMembership(overrides?: Partial<TripMember>)` — returns a mock TripMember
- Export `setupAuthMocks(session, membership)` — configures `getServerSession` + `prisma.tripMember.findUnique` mocks

### 4. Verify
- `npx tsc --noEmit` passes
- Existing tests still pass: `npx vitest run`

## Output
apps/web/lib/rate-limit.ts
apps/web/lib/auth/config.ts
apps/web/__tests__/helpers/transaction-mock.ts
apps/web/__tests__/helpers/auth-factory.ts

## Zone
infra

## Dependencies
M-001

## Priority
95

## Target Files
- apps/web/lib/rate-limit.ts
- apps/web/lib/auth/config.ts
- apps/web/__tests__/helpers/transaction-mock.ts
- apps/web/__tests__/helpers/auth-factory.ts
