# M-008: Extract CITY_PHOTOS to Shared Utility

## Description
CITY_PHOTOS map is duplicated in 3 files with inconsistent city counts (TripHeroCard: 13, PastTripRow: 10, trip detail: varies). Extract to single source of truth. P2 priority.

## Task
Create `apps/web/lib/city-photos.ts`:
- Export a `CITY_PHOTOS` record mapping city names to Unsplash URLs
- Merge all cities from all 3 current copies (superset)
- Export helper: `getCityPhoto(city: string, width?: number): string` that returns the URL with `w=` param, falling back to a generic travel photo
- Default width: 800

Update these files to import from the shared util:
1. `apps/web/components/dashboard/TripHeroCard.tsx` — remove local CITY_PHOTOS, import `getCityPhoto`
2. `apps/web/components/dashboard/PastTripRow.tsx` — remove local CITY_PHOTOS, import `getCityPhoto`
3. `apps/web/app/trip/[id]/page.tsx` — remove local CITY_PHOTOS, import `getCityPhoto`

Verify: All three components render city photos correctly. The superset includes at minimum: Tokyo, Kyoto, Seoul, Bangkok, Lisbon, Barcelona, Paris, London, Rome, Istanbul, Taipei, Mexico City, New York. TypeScript compiles clean.

## Output
apps/web/lib/city-photos.ts

## Zone
ui

## Dependencies
none

## Priority
70

## Target Files
- apps/web/lib/city-photos.ts
- apps/web/components/dashboard/TripHeroCard.tsx
- apps/web/components/dashboard/PastTripRow.tsx
- apps/web/app/trip/[id]/page.tsx

## Files
- docs/plans/dashboard-audit-compound.md
