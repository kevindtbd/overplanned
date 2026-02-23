# M-012: Dashboard Component Tests

## Description
Dashboard has 0% test coverage. Write unit tests for all dashboard components and state components. P3 priority.

## Task
Create test infrastructure:
- `mockTrip` factory function returning valid `TripSummary` with overrides
- `fetch` mock utility for dashboard page tests
- `next/navigation` mock for `useRouter`

Create `apps/web/__tests__/dashboard/EmptyState.test.tsx` (5 tests):
- renders icon, title, and description
- renders action button when action prop provided
- does not render button when action prop omitted
- calls onClick when action button clicked
- icon container is aria-hidden

Create `apps/web/__tests__/dashboard/ErrorState.test.tsx` (5 tests):
- renders default message when no message prop
- renders custom message
- renders retry button when onRetry provided
- calls onRetry when retry button clicked
- has role="alert" for accessibility

Create `apps/web/__tests__/dashboard/TripHeroCard.test.tsx` (8 tests):
- renders trip name / falls back to destination
- renders city and country
- links to /trip/{id}
- renders progress bar only for planning status
- clamps progress between 0 and 100
- renders member count only when > 1
- uses fallback photo for unknown city
- renders mode badge

Create `apps/web/__tests__/dashboard/PastTripRow.test.tsx` (5 tests):
- renders trip name / falls back to destination
- renders city and country
- links to /trip/{id}
- uses fallback photo for unknown city
- renders date range

Verify: `npx vitest run apps/web/__tests__/dashboard/` — all tests pass.

## Output
apps/web/__tests__/dashboard/EmptyState.test.tsx
apps/web/__tests__/dashboard/ErrorState.test.tsx
apps/web/__tests__/dashboard/TripHeroCard.test.tsx
apps/web/__tests__/dashboard/PastTripRow.test.tsx

## Zone
test

## Dependencies
M-006, M-008, M-009

## Priority
50

## Target Files
- apps/web/__tests__/dashboard/EmptyState.test.tsx
- apps/web/__tests__/dashboard/ErrorState.test.tsx
- apps/web/__tests__/dashboard/TripHeroCard.test.tsx
- apps/web/__tests__/dashboard/PastTripRow.test.tsx

## Files
- docs/plans/dashboard-audit-compound.md
