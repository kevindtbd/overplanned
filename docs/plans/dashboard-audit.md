# Dashboard Audit -- Comprehensive Review

**Auditor:** Claude Opus 4.6
**Date:** 2026-02-20
**Scope:** All dashboard pages, components, API routes, navigation, and shared state components
**Design Reference:** `docs/overplanned-design-v4.html`, `CLAUDE.md` (locked design system)

---

## Table of Contents

1. [File Inventory](#1-file-inventory)
2. [Page-by-Page Analysis](#2-page-by-page-analysis)
3. [Component Analysis](#3-component-analysis)
4. [Design System Compliance](#4-design-system-compliance)
5. [CRUD Operation Inventory](#5-crud-operation-inventory)
6. [User Flow Analysis](#6-user-flow-analysis)
7. [Accessibility Audit](#7-accessibility-audit)
8. [Prioritized Issues](#8-prioritized-issues)
9. [Recommended Fixes](#9-recommended-fixes)
10. [Risks and Gaps](#10-risks-and-gaps)

---

## 1. File Inventory

### Dashboard Pages
| File | Purpose |
|------|---------|
| `apps/web/app/dashboard/page.tsx` | Main dashboard -- lists active and past trips |
| `apps/web/app/trip/[id]/page.tsx` | Trip detail -- day view with slots |
| `apps/web/app/trip/[id]/calendar/page.tsx` | Calendar view for a trip |
| `apps/web/app/trip/[id]/map/page.tsx` | Map view for a trip |
| `apps/web/app/trip/[id]/reflection/page.tsx` | Post-trip reflection |

### Dashboard Components
| File | Purpose |
|------|---------|
| `apps/web/components/dashboard/TripHeroCard.tsx` | Large hero card for active trips |
| `apps/web/components/dashboard/PastTripRow.tsx` | Compact row for completed trips |

### Shared / State Components
| File | Purpose |
|------|---------|
| `apps/web/components/states/CardSkeleton.tsx` | Loading skeleton for cards |
| `apps/web/components/states/EmptyState.tsx` | Empty state with icon, title, CTA |
| `apps/web/components/states/ErrorState.tsx` | Error display with retry button |
| `apps/web/components/states/SlotSkeleton.tsx` | Loading skeleton for slot cards |

### Layout / Navigation
| File | Purpose |
|------|---------|
| `apps/web/components/layout/AppShell.tsx` | Main layout wrapper (sidebar + mobile nav) |
| `apps/web/components/nav/MobileNav.tsx` | Fixed bottom nav (mobile) |
| `apps/web/components/nav/DesktopSidebar.tsx` | Fixed left sidebar (desktop) |

### API Route
| File | Purpose |
|------|---------|
| `apps/web/app/api/trips/route.ts` | GET (list trips) + POST (create trip) |

---

## 2. Page-by-Page Analysis

### 2.1 Dashboard Page (`/dashboard`)

**Purpose:** Entry point after login. Shows user's trips partitioned into "Active" (planning/active) and "Past" (completed/cancelled) sections.

**Architecture:**
- `"use client"` -- client-side data fetching via `useEffect` + `fetch("/api/trips")`
- State machine: `loading | error | success`
- Wraps content in `<AppShell context="app">`

**What it renders:**
- Loading: 2x `CardSkeleton` (h-56)
- Error: `ErrorState` with retry callback
- Empty: `EmptyState` with compass icon + "Plan a trip" CTA -> `/onboarding`
- Active trips: grid of `TripHeroCard` (2-column on sm+)
- Past trips: vertical stack of `PastTripRow`

**HTML/Semantic structure:**
- `<header>` with `<h1>` for page title -- GOOD
- `<section aria-labelledby="...">` for each trip group -- GOOD
- `<h2>` with matching `id` for section headings -- GOOD

**Issues:**
1. **No dashboard layout.tsx** -- no shared layout for dashboard sub-routes
2. **Client-side fetching** -- could be a Server Component with `getServerSession` + direct Prisma query for faster initial paint (no loading spinner, no waterfall)
3. **No trip deletion or archiving** -- Read-only. No way to remove or manage trips from the dashboard
4. **No sorting/filtering** -- trips are displayed in API order (createdAt desc) with no user control
5. **Two skeleton cards always shown** -- doesn't match the likely data shape (user could have 1 or 10 trips)

### 2.2 Trip Detail Page (`/trip/[id]`)

**Purpose:** Shows a single trip's itinerary organized by day. Day navigation strip + slot timeline.

**Architecture:**
- `"use client"` -- client-side fetch to `/api/trips/${tripId}`
- Groups slots by `dayNumber`, renders via `DayNavigation` + `DayView`
- Behavioral signal logging via `handleSlotAction` (console.log only -- not wired to API)

**Issues:**
1. **No back button** -- no way to return to `/dashboard` except browser back or sidebar nav
2. **`trip!` non-null assertions** -- used 6 times after success state guard, but TypeScript still sees `trip` as nullable; fragile pattern
3. **Behavioral signals not posted** -- `handleSlotAction` logs to console, never calls `/api/behavioral-signals`
4. **CITY_PHOTOS duplicated** -- same map appears in TripHeroCard, PastTripRow, and trip detail page (3 copies)
5. **`vibeTags` always empty** -- hardcoded to `[]` with a comment "would need a separate join"
6. **No error recovery for 404/403** -- shows generic error state, no link back to dashboard

---

## 3. Component Analysis

### 3.1 TripHeroCard

**Purpose:** Large photo card for active trips. Links to `/trip/[id]`.

**Design compliance:**
- Font usage: `font-sora` for name (GOOD), `font-dm-mono` for labels (GOOD)
- Photo overlay: uses `photo-overlay-warm` class (GOOD)
- Progress bar uses `bg-accent` (GOOD)
- SVG icons inline (GOOD -- no icon libraries)

**Issues:**
1. **No `aria-label` on the link** -- screen readers will read the entire card content as link text
2. **CITY_PHOTOS is a hardcoded dictionary** -- only 13 cities covered; any other city falls to a generic travel photo
3. **No loading/error state for images** -- `next/image` handles this partially, but broken Unsplash URLs would show nothing
4. **Progress bar has no `role="progressbar"` or `aria-valuenow`** -- invisible to assistive tech
5. **`h-[340px]` is fixed** -- on very small screens this is tall; not responsive

### 3.2 PastTripRow

**Purpose:** Compact row for completed trips. Thumbnail + name + dates + arrow.

**Design compliance:**
- Font usage correct (Sora headings, DM Mono labels)
- Uses design tokens (`border-ink-700`, `bg-surface`)
- Hover state: `hover:border-accent/40` (GOOD)

**Issues:**
1. **CITY_PHOTOS duplicated** from TripHeroCard (different `w=` param but same URLs)
2. **Dates hidden on mobile** (`hidden sm:block`) -- mobile users see no date information
3. **No status indicator** -- "completed" and "cancelled" trips look identical
4. **Missing cities** -- PastTripRow has 10 cities vs TripHeroCard's 13 (missing Taipei, Mexico City, New York)

### 3.3 EmptyState

**Purpose:** Centered empty state with icon, message, and CTA button.

**DESIGN VIOLATION:** Uses `font-lora italic` for the title. The locked design system specifies only Sora (headings) and DM Mono (data/labels). Lora is NOT in the design system spec.

**Issues:**
1. **font-lora violation** -- should be `font-sora`
2. **No `role` attribute** -- should indicate this is a status region
3. **Button uses `btn-primary` class** -- correctly uses accent color, GOOD

### 3.4 ErrorState

**Purpose:** Error display with retry button.

**Design compliance:** GOOD -- uses design tokens for error colors, SVG icon inline, `role="alert"` present.

**Issues:**
1. **Error icon container has same bg as parent** (`bg-error-bg` on `bg-error-bg`) -- icon doesn't visually separate from the background
2. **No "Go back" option** -- only retry, no escape hatch if the error is persistent

### 3.5 CardSkeleton

**Purpose:** Loading placeholder for trip cards.

**Design compliance:** GOOD -- uses `skel` class from globals.css, `bg-surface`, `shadow-card`.

**Issues:**
1. **`aria-busy="true"` and `role="status"`** -- GOOD accessibility
2. **`sr-only` loading text** -- GOOD
3. No issues found.

### 3.6 AppShell

**Purpose:** Main layout wrapper. Desktop sidebar + mobile bottom nav.

**DESIGN VIOLATION:** TripHero sub-component uses `font-lora` for trip name heading.

**Issues:**
1. **`font-lora` in TripHero** -- should be `font-sora` per design system
2. **Avatar placeholder** is a plain div (`w-7 h-7 rounded-full bg-raised`) -- not interactive, no profile link
3. **No `<main>` landmark role** -- uses `<main>` tag which is correct semantically
4. **Padding values differ between trip and app context** -- both use the same padding actually (`px-6 py-12 lg:px-10 lg:py-16`), which is fine

### 3.7 MobileNav

**Design compliance:** GOOD -- inline SVGs, `font-dm-mono` labels, accent color for active state.

**Issues:**
1. **"Trips" links to `/trips`** but the dashboard is at `/dashboard` -- this means the nav "Trips" item would never highlight on the dashboard page
2. **"Home" links to `/`** (landing page) -- after login, "Home" should probably go to `/dashboard`
3. **No "Plan a trip" quick action** -- common mobile pattern for primary action is missing

### 3.8 DesktopSidebar

**Design compliance:** GOOD -- Sora wordmark, DM Mono labels, accent highlight.

**Issues:**
1. **Same nav mismatch as MobileNav** -- "Trips" goes to `/trips`, not `/dashboard`
2. **"Beta" label at bottom** -- uses `label-mono` class, GOOD
3. **No sign-out option** in the sidebar
4. **No user avatar/name** displayed

---

## 4. Design System Compliance

### Checklist

| Rule | Status | Details |
|------|--------|---------|
| Fonts: Sora (headings) | PARTIAL | Used correctly in dashboard, TripHeroCard, PastTripRow. BUT `font-lora` is used in EmptyState title, AppShell TripHero, and SlotCard -- design system says Sora only. |
| Fonts: DM Mono (data/labels) | PASS | Used correctly for dates, labels, badges, progress text |
| Accent: Terracotta #C4694F | PASS | CSS var `--accent: #C4694F` in light theme. Note: design-v4.html uses `#B85C3F` -- discrepancy between CLAUDE.md canonical value and design HTML |
| Warm tokens | PASS | `bg-base`, `bg-surface`, `bg-raised`, `bg-warm` all mapped correctly |
| Icons: SVG only | PASS | All icons are inline SVG. No icon libraries imported |
| No emoji | PASS | Zero emoji found in any dashboard component |
| Images: Unsplash URLs | PASS | All city photos use Unsplash URLs with width/quality params |
| Shadows: warm-tinted | PASS | All shadows use `rgba(28,23,19,...)` in light mode -- warm, not blue |

### Critical Violations

1. **font-lora is not part of the design system.** CLAUDE.md and the design-v4.html specify only Sora + DM Mono. Lora is loaded in `layout.tsx` and used across the app (EmptyState, AppShell TripHero, SlotCard, landing page, auth pages). This is a systemic violation.

2. **Accent color discrepancy.** CLAUDE.md says `#C4694F`. The app's `globals.css` uses `#C4694F` (matches). BUT `docs/overplanned-design-v4.html` uses `#B85C3F` in light mode. The HTML design reference is out of sync with CLAUDE.md.

---

## 5. CRUD Operation Inventory

### Dashboard Page (`/dashboard`)

| Operation | Exists | Endpoint | Notes |
|-----------|--------|----------|-------|
| **Read** trips | YES | `GET /api/trips` | Lists all trips where user is a member |
| **Create** trip | NO (indirect) | -- | CTA in empty state links to `/onboarding`, not a direct create flow |
| **Update** trip | NO | -- | No edit, rename, or status change from dashboard |
| **Delete** trip | NO | -- | No delete or archive capability |

### Trip Detail Page (`/trip/[id]`)

| Operation | Exists | Endpoint | Notes |
|-----------|--------|----------|-------|
| **Read** trip + slots | YES | `GET /api/trips/[id]` | Fetches full trip with slots and members |
| **Update** slot status | NO | -- | `handleSlotAction` logs to console only |
| **Log** behavioral signal | NO | -- | Console.log placeholder, not wired to API |
| **Delete** slot | NO | -- | No slot removal capability |
| **Add** slot | NO | -- | No manual slot addition |
| **Reorder** slots | NO | -- | No drag-and-drop or reordering |

### API Route (`/api/trips`)

| Method | What it does | Auth | Validation |
|--------|--------------|------|------------|
| `GET` | Lists user's trips via TripMember join | Session check | None needed |
| `POST` | Creates trip + organizer TripMember | Session check | Zod schema (`createTripSchema`) |

**API Issues:**
1. **`new PrismaClient()` instantiated at module scope** -- in serverless/edge, this creates a new connection per cold start. Should use a singleton pattern.
2. **No pagination on GET** -- returns all trips. With many trips, this becomes a performance issue.
3. **No `DELETE` or `PATCH` handler** -- trips cannot be updated or removed via API.
4. **Type casting with `as never`** -- `mode: mode as never` and `role: "organizer" as never` are type hacks that suppress TypeScript errors instead of properly typing enum values.

---

## 6. User Flow Analysis

### Primary Flow: New User

```
Landing (/) -> Sign In -> Dashboard (empty state) -> "Plan a trip" -> /onboarding
```

**Issues:**
- After onboarding, where does the user land? Presumably back to `/dashboard`, but this is not verified from the code alone.
- "Home" in nav goes to `/` (landing), not `/dashboard`. Confusing after login.

### Primary Flow: Returning User

```
Landing (/) -> Sign In -> Dashboard (shows trips) -> Click trip -> /trip/[id]
```

**Issues:**
- No way back from `/trip/[id]` to `/dashboard` except sidebar "Trips" (which goes to `/trips`, a different route) or browser back.
- The "Trips" nav item links to `/trips` which is NOT the same as `/dashboard`. There may be a separate `/trips` page or this is a dead link.

### Navigation Dead Ends

1. **`/trip/[id]` has no back button** -- stranded if user arrived via direct link
2. **MobileNav "Trips" -> `/trips`** -- if this page doesn't exist, it's a 404
3. **MobileNav "Explore" -> `/explore`** -- if this page doesn't exist, it's a 404
4. **MobileNav "Profile" -> `/profile`** -- if this page doesn't exist, it's a 404
5. **Dashboard lives at `/dashboard`** but is NOT in the MobileNav -- no way to reach it from nav after navigating away

### Flow Diagram

```
/                   (landing -- public)
  |
/auth/signin        (Google OAuth)
  |
/dashboard          (trip list -- NOT in nav as "Dashboard")
  |
/trip/[id]          (trip detail -- no back to dashboard)
  |--- /trip/[id]/calendar
  |--- /trip/[id]/map
  |--- /trip/[id]/reflection
  |
/onboarding         (trip creation wizard)
  |
/trips/[id]/generating  (itinerary generation loading screen)
```

---

## 7. Accessibility Audit

### Passes
- `<section aria-labelledby>` with matching heading `id` on dashboard
- `aria-hidden="true"` on decorative SVGs and overlay divs
- `role="alert"` on ErrorState
- `role="status"` + `aria-busy` on CardSkeleton
- `aria-current="page"` on active nav items
- `sr-only` text for loading states
- Focus-visible outline using accent color (`*:focus-visible` in globals.css)
- `prefers-reduced-motion` respected for skeleton animation

### Failures
1. **Progress bar** in TripHeroCard -- no `role="progressbar"`, no `aria-valuenow`, no `aria-valuemin/max`. Screen readers cannot perceive planning progress.
2. **TripHeroCard link** -- no `aria-label`. Screen reader will read all text content as one long link label including "solo trip", progress percentage, member count, etc.
3. **PastTripRow link** -- similarly, no `aria-label` for the row link.
4. **EmptyState** -- no `role="status"` to indicate it is informational.
5. **Dashboard page** -- no `<title>` set (relies on root layout "Overplanned" -- should be "Your Trips - Overplanned").
6. **Keyboard navigation** -- TripHeroCard and PastTripRow are `<Link>` elements (focusable), but the hover zoom effect on TripHeroCard (`group-hover:scale-[1.03]`) has no focus equivalent.
7. **Color contrast** -- `text-white/50` and `text-white/60` on photo overlays may not meet WCAG AA 4.5:1 for small text.

---

## 8. Prioritized Issues

### Critical (breaks functionality or violates locked rules)

| # | Issue | File(s) | Impact |
|---|-------|---------|--------|
| C1 | `font-lora` used in headings -- violates locked design system (Sora + DM Mono only) | `EmptyState.tsx`, `AppShell.tsx` | Design system violation |
| C2 | Nav "Trips" links to `/trips`, dashboard is at `/dashboard` -- navigation broken | `MobileNav.tsx`, `DesktopSidebar.tsx` | Users cannot navigate back to dashboard |
| C3 | "Home" nav links to `/` (landing page) instead of `/dashboard` after login | `MobileNav.tsx`, `DesktopSidebar.tsx` | Confusing post-login navigation |
| C4 | No back button on `/trip/[id]` | `app/trip/[id]/page.tsx` | Users are stranded |
| C5 | Behavioral signals not wired -- console.log only | `app/trip/[id]/page.tsx` | Core product feature non-functional |

### High (significant UX or code quality issues)

| # | Issue | File(s) | Impact |
|---|-------|---------|--------|
| H1 | CITY_PHOTOS duplicated 3 times | `TripHeroCard.tsx`, `PastTripRow.tsx`, `trip/[id]/page.tsx` | Maintenance burden, inconsistency (PastTripRow missing 3 cities) |
| H2 | Progress bar not accessible (no ARIA) | `TripHeroCard.tsx` | WCAG violation |
| H3 | No trip CRUD beyond Read -- no edit, delete, archive | Dashboard + API | Incomplete feature set |
| H4 | `new PrismaClient()` at module scope | `api/trips/route.ts` | Connection leak in serverless |
| H5 | No pagination on GET /api/trips | `api/trips/route.ts` | Performance issue at scale |
| H6 | Client-side fetch for dashboard -- SSR would be faster | `app/dashboard/page.tsx` | Unnecessary loading spinner |
| H7 | `as never` type casts hide TypeScript errors | `api/trips/route.ts` | Type safety gap |

### Medium (polish and completeness)

| # | Issue | File(s) | Impact |
|---|-------|---------|--------|
| M1 | Dates hidden on mobile in PastTripRow | `PastTripRow.tsx` | Information loss |
| M2 | No status indicator on past trips (completed vs cancelled) | `PastTripRow.tsx` | User confusion |
| M3 | vibeTags always empty array | `trip/[id]/page.tsx` | Feature gap |
| M4 | No sign-out in sidebar | `DesktopSidebar.tsx` | UX gap |
| M5 | Avatar placeholder not interactive | `AppShell.tsx` | Dead UI element |
| M6 | White text on photo overlay may fail WCAG contrast | `TripHeroCard.tsx` | Accessibility concern |
| M7 | No page title for dashboard (uses generic "Overplanned") | `app/dashboard/page.tsx` | SEO + accessibility |
| M8 | Accent color discrepancy: CLAUDE.md=#C4694F, design-v4.html=#B85C3F | `globals.css` vs `design-v4.html` | Design drift |

### Nice-to-Have

| # | Issue | File(s) | Impact |
|---|-------|---------|--------|
| N1 | No sorting/filtering of trips | `app/dashboard/page.tsx` | Feature gap |
| N2 | No trip search | `app/dashboard/page.tsx` | Feature gap |
| N3 | No loading image fallback for broken Unsplash URLs | `TripHeroCard.tsx`, `PastTripRow.tsx` | Edge case |
| N4 | Focus zoom effect missing (only hover zoom on TripHeroCard) | `TripHeroCard.tsx` | Keyboard UX |

---

## 9. Recommended Fixes

### Fix C1: Remove font-lora from dashboard components
**Files:** `apps/web/components/states/EmptyState.tsx`, `apps/web/components/layout/AppShell.tsx`
**Change:** Replace `font-lora italic` with `font-sora` in heading elements.

### Fix C2 + C3: Fix navigation routes
**Files:** `apps/web/components/nav/MobileNav.tsx`, `apps/web/components/nav/DesktopSidebar.tsx`
**Change:**
- "Home" href: `/` -> `/dashboard` (or conditionally based on auth state)
- "Trips" href: `/trips` -> `/dashboard`
- Or: create a `/trips` page that redirects to `/dashboard`

### Fix C4: Add back button to trip detail
**File:** `apps/web/app/trip/[id]/page.tsx`
**Change:** Add a "Back to trips" link in the header area, using `<Link href="/dashboard">`.

### Fix C5: Wire behavioral signals
**File:** `apps/web/app/trip/[id]/page.tsx`
**Change:** Replace `console.log` with `fetch("/api/behavioral-signals", { method: "POST", ... })`.

### Fix H1: Extract CITY_PHOTOS to shared util
**Create:** `apps/web/lib/city-photos.ts`
**Change:** Single source of truth for city photo URLs. Export `getCityPhoto(city: string, width?: number): string`.

### Fix H2: Add ARIA to progress bar
**File:** `apps/web/components/dashboard/TripHeroCard.tsx`
**Change:** Add `role="progressbar"`, `aria-valuenow={progress}`, `aria-valuemin={0}`, `aria-valuemax={100}`, `aria-label="Planning progress"` to the progress bar container.

### Fix H4: Prisma singleton
**File:** `apps/web/app/api/trips/route.ts`
**Change:** Import from a shared `lib/prisma.ts` singleton instead of `new PrismaClient()`.

---

## 10. Risks and Gaps

### Assumptions Made During This Audit

1. **Assumed `/trips`, `/explore`, `/profile` pages may not exist** -- if they do exist, some navigation issues (C2, C3) may be less severe. Needs verification.
2. **Assumed the API response shape matches `TripSummary` interface** -- the GET /api/trips response returns extra fields (`myRole`, `myStatus`, `joinedAt`, `_count`) that `TripSummary` doesn't declare. This means either the type is incomplete or extra data is silently discarded.
3. **Assumed `createTripSchema` validation is correct** -- did not read the Zod schema. Validation gaps are possible.

### Edge Cases Not Covered

1. **Empty trip name** -- `trip.name` is nullable. `displayName` falls back to `trip.destination`, but what if destination is also empty? Would render blank card.
2. **Invalid dates** -- `formatDateRange` calls `new Date(start)` on strings. If the API returns malformed dates (e.g., null), this produces "Invalid Date".
3. **Very long trip names** -- TripHeroCard does not truncate the name. Long names would overflow the photo card.
4. **Zero-day trips** -- `computeTotalDays` returns `Math.max(diff, 1)` which handles zero but not negative (end before start).
5. **Concurrent trip creation** -- UUID v4 for trip IDs prevents collisions, but there is no optimistic locking on the member count.
6. **Large member counts** -- the dashboard shows `{memberCount} members` but does not handle singular ("1 member" vs "2 members"). Actually, it only shows when `memberCount > 1`, so it would say "2 members" minimum. But edge case: what if a member is removed and count drops to 1 mid-session?
7. **Timezone display** -- no timezone information shown on the dashboard despite being stored. Users in different timezones from the trip could be confused about dates.
8. **Network failures during fetch** -- `fetchTrips` catches errors but does not distinguish between network failures and server errors. No offline indicator.
9. **Session expiry** -- middleware redirects to signin, but the client-side fetch will get a 401. The error state shows "Unauthorized" but doesn't redirect to login.
10. **Photo loading on slow connections** -- TripHeroCard shows a 340px tall image. On 3G, this could take several seconds with no skeleton or blur placeholder.

### What Would Break With Malformed Data

| Data condition | Component | Breakage |
|---------------|-----------|----------|
| `trips` is not an array in API response | Dashboard page | `setTrips` would set non-array, `.filter()` throws |
| `trip.status` is an unexpected value | Dashboard page | Trip would appear in neither active nor past sections (silently hidden) |
| `trip.city` contains special characters | TripHeroCard | Photo lookup returns fallback, but `alt` text could be problematic |
| `trip.planningProgress` is NaN | TripHeroCard | `Math.min(Math.max(NaN, 0), 100)` returns `NaN`, progress bar width is `NaN%` |
| `trip.startDate` is null | TripHeroCard, PastTripRow | `new Date(null)` returns epoch, displays "Jan 1 - ..." |
| API returns 500 | Dashboard page | ErrorState shown with "Internal server error" -- GOOD |
| API returns empty `{ }` (no `trips` key) | Dashboard page | `const { trips: tripList } = ...` sets `tripList` to `undefined`, `setTrips(undefined)` would break |

### Systemic Risks

1. **font-lora is deeply embedded** -- it is used in 15+ locations across the app (landing, auth, slots, dashboard). Removing it is not a trivial find-and-replace; each instance needs design review for what replaces it.
2. **CITY_PHOTOS pattern doesn't scale** -- hardcoded maps for 10-13 cities. The product vision supports any destination. Needs a dynamic photo solution (Unsplash API, user uploads, or city photo API).
3. **Client-side-only data fetching** -- the entire dashboard depends on a waterfall: page load -> JS load -> hydrate -> fetch -> render. This adds 1-3 seconds of blank/loading state. Server Components would eliminate this.
4. **No error boundaries** -- a JS error in TripHeroCard would crash the entire dashboard. React Error Boundaries are not used.
5. **No data revalidation** -- if user creates a trip in another tab, the dashboard won't update. No SWR/react-query/polling/websocket pattern.

---

## Middleware Change Applied

Added `/dashboard` and `/dashboard/` to `PUBLIC_PATHS` in `apps/web/middleware.ts` to allow unauthenticated local dev access to the dashboard.

**Note:** This should be removed or gated behind `NODE_ENV === 'development'` before production deployment. Currently, anyone can access `/dashboard` without auth (though the API call to `/api/trips` will return 401, so they would see an error state).

---

*End of audit.*
