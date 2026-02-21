# Dashboard Audit -- Compound Report

> **Source:** Original audit + Architect review + Security review + Test-engineer review
> **Date:** 2026-02-21
> **Status:** CHECKPOINT -- research complete, ready for implementation planning

---

## Executive Summary

Three specialized agents reviewed the dashboard audit independently. Key findings:

- **9 PrismaClient instances** across the codebase (not 1 as originally reported)
- **Member emails exposed** via trip detail API (PII leak)
- **Middleware auth bypass** affects `/dashboard/*` prefix, not just `/dashboard`
- **0% test coverage** on all dashboard components and API route handlers
- **3 dead nav links** (Trips, Explore, Profile point to nonexistent pages)
- **font-lora violations** in 20+ locations (systemic, not isolated)

---

## Consolidated Issue List (De-duped, Re-prioritized)

### P0 -- Before Any Deployment

| # | Issue | Source | Files | Effort |
|---|-------|--------|-------|--------|
| 1 | **PrismaClient singleton** -- 9 separate instances cause connection pool exhaustion | Architect (upgraded from H4) | Create `lib/prisma.ts`, update 9 files | 30 min |
| 2 | **Remove `/dashboard` from PUBLIC_PATHS** -- prefix-match makes `/dashboard/*` public | Security S1 | `middleware.ts` | 5 min |
| 3 | **Stop exposing member emails** -- PII via trip detail API response | Security S3 (NEW) | `api/trips/[id]/route.ts` | 10 min |

### P1 -- Critical UX/Design Fixes

| # | Issue | Source | Files | Effort |
|---|-------|--------|-------|--------|
| 4 | **Fix nav routes** -- Trips -> `/dashboard`, remove dead links | Audit C2+C3, Architect | `MobileNav.tsx`, `DesktopSidebar.tsx` | 15 min |
| 5 | **Add back button to trip detail** | Audit C4 | `trip/[id]/page.tsx` | 10 min |
| 6 | **Replace font-lora in dashboard** -- design system violation | Audit C1 | `EmptyState.tsx`, `AppShell.tsx` | 10 min |
| 7 | **Fix `as never` type casts** -- suppress Prisma enum errors | Audit H7, Security S7 | `api/trips/route.ts`, `api/trips/[id]/route.ts` | 15 min |

### P2 -- Data Integrity & Accessibility

| # | Issue | Source | Files | Effort |
|---|-------|--------|-------|--------|
| 8 | **Extract CITY_PHOTOS to shared util** -- duplicated 3x, inconsistent | Audit H1 | Create `lib/city-photos.ts`, update 3 files | 20 min |
| 9 | **Add ARIA to progress bar** -- WCAG violation | Audit H2 | `TripHeroCard.tsx` | 10 min |
| 10 | **Wire behavioral signals** -- console.log placeholder | Audit C5 | `trip/[id]/page.tsx` | 20 min |
| 11 | **Constrain personaSeed JSON** -- unbounded arbitrary object | Security S5 (NEW) | `lib/validations/trip.ts` | 5 min |

### P3 -- Test Coverage (currently 0%)

| # | Issue | Source | Files | Effort |
|---|-------|--------|-------|--------|
| 12 | **Dashboard page tests** -- loading/error/success states, trip partitioning | Test-engineer | Create `__tests__/dashboard/DashboardPage.test.tsx` | 1 hr |
| 13 | **Component tests** -- TripHeroCard, PastTripRow, EmptyState, ErrorState | Test-engineer | Create 4 test files | 1.5 hr |
| 14 | **API route handler tests** -- GET/POST with mocked Prisma + session | Test-engineer | Create `__tests__/api/trips-route.test.ts` | 1 hr |
| 15 | **Edge case tests** -- NaN progress, null dates, missing trips key | Test-engineer | Create `__tests__/dashboard/edge-cases.test.tsx` | 45 min |

### P4 -- Architectural Improvements (Backlog)

| # | Issue | Source | Files | Effort |
|---|-------|--------|-------|--------|
| 16 | **Add error.tsx boundaries** | Architect (MISSED) | Create `dashboard/error.tsx`, `trip/[id]/error.tsx` | 20 min |
| 17 | **Layout refactor (route groups)** | Architect | Multiple files, restructure dirs | 2-3 hr |
| 18 | **Rate limiting on POST endpoints** | Security S6 (NEW) | API routes or infra layer | 1 hr |
| 19 | **Shared type contracts** between API and client | Architect (MISSED) | Create types files | 1-2 hr |
| 20 | **Throttle session DB writes** -- `lastActiveAt` on every request | Security S11 (NEW) | `lib/auth/config.ts` | 15 min |
| 21 | **Document middleware as UX-only, not security boundary** | Security S2 | Add comment/docs | 10 min |

---

## New Issues Found by Reviewers (Not in Original Audit)

| # | Issue | Reviewer | Severity |
|---|-------|----------|----------|
| S3 | Member emails exposed in trip detail API | Security | HIGH |
| S5 | `personaSeed` accepts unbounded arbitrary JSON | Security | MEDIUM |
| S6 | No rate limiting on any API endpoint | Security | MEDIUM |
| S8 | CSP `unsafe-inline` in production | Security | MEDIUM |
| S11 | Session callback writes to DB on every request | Security | LOW |
| MISSED-1 | No React Error Boundaries (`error.tsx`) anywhere | Architect | MEDIUM-HIGH |
| MISSED-2 | No `dashboard/layout.tsx` for persistent chrome | Architect | MEDIUM |
| MISSED-4 | Type mismatch between API response and client types | Architect | MEDIUM |
| MISSED-5 | Calendar page uses PrismaClient directly in page component | Architect | HIGH |
| MISSED-6 | Middleware prefix-match affects `/s/*` and `/invite/*` too | Security S9 | MEDIUM |

---

## Positive Findings (Things Done Well)

- IDOR prevention on trip detail (membership check, 404 not 403)
- Organizer role required for PATCH mutations
- Zod validation on all POST/PATCH inputs
- Database sessions (not JWT) with 30d max / 7d idle
- Concurrent session limiting (max 5)
- Full security header suite (HSTS, X-Frame-Options, nosniff, strict referrer)
- Environment validation via Zod at startup
- Parameterized queries throughout (no raw SQL)

---

## Test Coverage Summary

| Area | Current Coverage | Priority Tests |
|------|-----------------|----------------|
| Dashboard page | 0% | 13 tests (loading/error/success/partitioning) |
| TripHeroCard | 0% | 12 tests (rendering, progress, photos, a11y) |
| PastTripRow | 0% | 7 tests (rendering, fallbacks) |
| EmptyState | 0% | 5 tests (rendering, action, a11y) |
| ErrorState | 0% | 5 tests (rendering, retry, role) |
| API route handlers | 0% (only Zod schemas) | 12 tests (auth, CRUD, errors) |
| Edge cases | 0% | 12 tests (NaN, null dates, malformed responses) |
| **Total needed** | **0%** | **~66 tests** |

---

## Severity Adjustments from Original Audit

| Original | Adjusted | Reason |
|----------|----------|--------|
| H4 (PrismaClient at module scope) | **P0 CRITICAL** | 9 instances, not 1. Systemic connection exhaustion risk. |
| C2+C3 (Nav routes broken) | **P1 CRITICAL-BLOCKING** | Target pages don't exist. Mobile nav is 3/4 dead links. |
| H6 (CSR for dashboard) | **MEDIUM** | Acceptable for beta. Prisma singleton is the real perf win. |
| M8 (Accent color discrepancy) | **LOW/NON-ISSUE** | CLAUDE.md is canonical. HTML doc needs update, not the app. |

---

## Next Steps

When ready to implement, the recommended approach is:

1. **P0 fixes first** (items 1-3) -- 45 min total, eliminates deployment blockers
2. **P1 UX fixes** (items 4-7) -- 50 min total, fixes broken navigation
3. **P2 data/a11y** (items 8-11) -- 55 min total, fixes accessibility and data integrity
4. **P3 test coverage** (items 12-15) -- 4.25 hr total, establishes safety net
5. **P4 architecture** (items 16-21) -- backlog, do incrementally

*End of compound report.*
