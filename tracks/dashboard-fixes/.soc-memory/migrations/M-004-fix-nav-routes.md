# M-004: Fix Navigation Routes

## Description
Fix broken navigation links in MobileNav and DesktopSidebar. "Trips" points to `/trips` (doesn't exist), "Home" points to `/` (landing page). 3 out of 4 mobile nav items are dead links. P1 priority.

## Task
Edit `apps/web/components/nav/MobileNav.tsx`:
- Change "Home" href from `/` to `/dashboard`
- Change "Trips" href from `/trips` to `/dashboard`
- For "Explore" (`/explore`) and "Profile" (`/profile`): these pages don't exist yet. Either remove these nav items entirely, or add `aria-disabled="true"` and muted styling with a "Coming soon" tooltip. Prefer removal to avoid dead links.

Edit `apps/web/components/nav/DesktopSidebar.tsx`:
- Apply the same route fixes as MobileNav
- "Trips" href: `/trips` -> `/dashboard`
- Evaluate whether "Home" should exist separately or be merged with "Trips"

Verify: All nav links point to existing pages. Clicking "Trips" in both mobile and desktop nav navigates to `/dashboard`. No 404s from nav interaction.

## Output
apps/web/components/nav/MobileNav.tsx
apps/web/components/nav/DesktopSidebar.tsx

## Zone
ui

## Dependencies
none

## Priority
90

## Target Files
- apps/web/components/nav/MobileNav.tsx
- apps/web/components/nav/DesktopSidebar.tsx

## Files
- docs/plans/dashboard-audit-compound.md
