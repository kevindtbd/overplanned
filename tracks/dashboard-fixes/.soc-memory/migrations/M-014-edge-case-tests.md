# M-014: Edge Case and Integration Tests

## Description
Document and test known fragile paths: NaN progress, null dates, missing trips key, malformed API responses. P3 priority.

## Task
Create `apps/web/__tests__/dashboard/edge-cases.test.tsx` (8 tests):
- dashboard handles API returning object without trips key
- dashboard handles API returning non-array trips value
- TripHeroCard renders when planningProgress is undefined (defaults to 0)
- TripHeroCard renders when startDate is invalid ISO string
- TripHeroCard renders when name and destination are both empty strings
- PastTripRow renders when city has special characters
- formatDateRange handles same start and end date
- trips with unexpected status values appear in neither section

Create `apps/web/__tests__/dashboard/DashboardPage.test.tsx` (8 tests):
- renders loading skeletons on initial mount
- renders error state when fetch rejects
- renders error state when API returns non-OK status
- renders empty state when API returns zero trips
- renders active trips as TripHeroCards
- renders past trips as PastTripRows
- partitions mixed trip list correctly
- retry button re-fetches trips

Mock setup: global `fetch` mock, `next/navigation` useRouter mock, `AppShell` wrapper mock.

Verify: `npx vitest run apps/web/__tests__/dashboard/` — all tests pass including edge cases.

## Output
apps/web/__tests__/dashboard/edge-cases.test.tsx
apps/web/__tests__/dashboard/DashboardPage.test.tsx

## Zone
test

## Dependencies
M-012, M-013

## Priority
40

## Target Files
- apps/web/__tests__/dashboard/edge-cases.test.tsx
- apps/web/__tests__/dashboard/DashboardPage.test.tsx

## Files
- docs/plans/dashboard-audit-compound.md
