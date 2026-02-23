# Dashboard Fixes — CHANGELOG

## Initialized
- 14 migrations created from compound audit report
- Zones: infra (1), security (2), ui (5), api (2), test (3)
- Source: docs/plans/dashboard-audit-compound.md

## [M-006] COMMIT - 2026-02-20 23:05:41
Removed font-lora violations from dashboard components, replaced with font-sora for all headings per locked design system
### Verified
- [x] apps/web/components/states/EmptyState.tsx
- [x] apps/web/components/layout/AppShell.tsx

## [M-002] COMMIT - 2026-02-20 23:05:45
P0 security fix: removed public access to all /dashboard/* routes in production while preserving dev-mode convenience
### Verified
- [x] apps/web/middleware.ts

## [M-005] COMMIT - 2026-02-20 23:05:51
Added Back to trips navigation link to resolve P1 stranded user issue
### Verified
- [x] apps/web/app/trip/[id]/page.tsx

## [M-004] COMMIT - 2026-02-20 23:06:20
Fixed P1 navigation bug: replaced dead links (/trips, /explore, /profile) with /dashboard in both MobileNav and DesktopSidebar. All 4 nav items now point to existing route.
### Verified
- [x] apps/web/components/nav/MobileNav.tsx
- [x] apps/web/components/nav/DesktopSidebar.tsx

## [M-001] COMMIT - 2026-02-20 23:06:39
Eliminated connection pool exhaustion risk by consolidating 9 separate PrismaClient instances into a single Next.js-compliant singleton with hot-reload support
### Verified
- [x] apps/web/lib/prisma.ts
- [x] apps/web/lib/auth/session.ts
- [x] apps/web/lib/auth/config.ts
- [x] apps/web/app/api/events/raw/route.ts
- [x] apps/web/app/api/discover/feed/route.ts
- [x] apps/web/app/api/signals/behavioral/route.ts
- [x] apps/web/app/api/slots/[slotId]/swap/route.ts
- [x] apps/web/app/trip/[id]/calendar/page.tsx
- [x] apps/web/app/api/trips/[id]/route.ts
- [x] apps/web/app/api/trips/route.ts

## [M-010] COMMIT - 2026-02-20 23:07:02
Added 10KB size limit validation to personaSeed field to prevent oversized payload attacks
### Verified
- [x] apps/web/lib/validations/trip.ts

## [M-003] COMMIT_CONFLICT - 2026-02-20 23:07:10
Removed PII exposure by excluding email from trip member API response and updating client-side type to match
### Verified
- [x] apps/web/app/api/trips/[id]/route.ts
- [x] apps/web/app/trip/[id]/page.tsx
### CONFLICT (claimed by another task)
- [!] apps/web/app/api/trips/[id]/route.ts
- [!] apps/web/app/trip/[id]/page.tsx

## [M-009] COMMIT - 2026-02-20 23:07:18
Fixed WCAG violations in TripHeroCard: progress bar now has proper ARIA attributes for screen readers, Link has descriptive label, and focus-visible zoom matches hover behavior
### Verified
- [x] apps/web/components/dashboard/TripHeroCard.tsx

## [M-011] COMMIT - 2026-02-20 23:07:29
Created Next.js 14 App Router error boundaries for dashboard and trip routes using design system tokens (bg-base, ink-100, font-sora, error/error-bg). Both show error icon, message, Try again button calling reset(), and back navigation links.
### Verified
- [x] apps/web/app/dashboard/error.tsx
- [x] apps/web/app/trip/[id]/error.tsx

## [M-012] COMMIT - 2026-02-20 23:09:10
Created comprehensive test suite for dashboard components (EmptyState, ErrorState, TripHeroCard, PastTripRow) with 23 passing tests covering rendering, user interactions, edge cases, and variant states
### Verified
- [x] apps/web/__tests__/dashboard/EmptyState.test.tsx
- [x] apps/web/__tests__/dashboard/ErrorState.test.tsx
- [x] apps/web/__tests__/dashboard/TripHeroCard.test.tsx
- [x] apps/web/__tests__/dashboard/PastTripRow.test.tsx

## [M-007] COMMIT_CONFLICT - 2026-02-20 23:10:33
Removed all `as never` type suppressions from trips API routes. Fixed critical bug where TripMember.status was set to 'active' (doesn't exist in MemberStatus enum) - corrected to 'joined'. TypeScript now validates enum assignments at compile time instead of deferring to runtime.
### Verified
- [x] apps/web/app/api/trips/route.ts
- [x] apps/web/app/api/trips/[id]/route.ts
### CONFLICT (claimed by another task)
- [!] apps/web/app/api/trips/route.ts
- [!] apps/web/app/api/trips/[id]/route.ts

## [M-008] COMMIT_CONFLICT - 2026-02-20 23:10:56
Extracted duplicated CITY_PHOTOS map to single source of truth at apps/web/lib/city-photos.ts. All three components (TripHeroCard, PastTripRow, trip detail page) now import getCityPhoto from shared utility. Superset includes all required cities (15 total) with configurable width parameter for different use cases.
### Verified
- [x] apps/web/lib/city-photos.ts
- [x] apps/web/components/dashboard/TripHeroCard.tsx
- [x] apps/web/components/dashboard/PastTripRow.tsx
- [x] apps/web/app/trip/[id]/page.tsx
### CONFLICT (claimed by another task)
- [!] apps/web/components/dashboard/TripHeroCard.tsx
- [!] apps/web/app/trip/[id]/page.tsx

## [M-014] COMMIT - 2026-02-20 23:12:17
Documented and tested known fragile paths including NaN progress, null dates, missing trips key, and malformed API responses. All tests pass including edge cases.
### Verified
- [x] apps/web/__tests__/dashboard/edge-cases.test.tsx
- [x] apps/web/__tests__/dashboard/DashboardPage.test.tsx

## [M-013] COMMIT - 2026-02-20 23:12:56
All 12 route handler tests passing - comprehensive coverage of auth bypass, validation, database errors, and success paths for both GET and POST endpoints
### Verified
- [x] apps/web/__tests__/api/trips-route.test.ts
- [x] apps/web/vitest.config.ts
