# Trip Date Range Validation

## Context

Trip creation and editing currently has zero cross-field date validation. `endDate` can be before `startDate`, and there's no duration cap. This means:

- Users can create trips that end before they start
- A 365-day trip is technically valid (84-slot worst case becomes 2,190 slots on packed)
- The day-nav UI breaks down past ~14 pills (50% offscreen at 14 days, 77% at 30)

Research showed: 65.5% of travelers take trips of 14 days or less. Cost per trip is negligible ($0.003-$0.011 LLM, pennies for storage). The cap is a product/UI decision, not a cost one. Multi-city legs (max 8, already capped) handle longer journeys by splitting into segments.

## Decision

- **endDate must be strictly after startDate** (minimum 1 night)
- **Maximum 14 nights** per trip (or per leg, once multi-city ships)
- **startDate no more than 2 years in the future** (extreme date defense)
- Enforced at: Zod schema, API route (for PATCH partial updates), and frontend UI

## Constants — `lib/constants/trip.ts` (NEW FILE)

```ts
// Per-leg cap. When multi-city ships, this applies to each leg independently.
// See docs/plans/2026-02-22-multi-city-trip-design.md
export const MAX_TRIP_NIGHTS = 14;
export const MAX_TRIP_ADVANCE_YEARS = 2;
```

## Shared utility — `lib/utils/dates.ts` (NEW FILE)

```ts
/** Count calendar nights between two date strings. Slices to YYYY-MM-DD to avoid DST edge cases. */
export function nightsBetween(startStr: string, endStr: string): number {
  const start = new Date(startStr.slice(0, 10));
  const end = new Date(endStr.slice(0, 10));
  return Math.round((end.getTime() - start.getTime()) / 86_400_000);
}

/** Normalize YYYY-MM-DD or ISO string to UTC midnight ISO. */
export function toMidnightISO(dateStr: string): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
    return `${dateStr}T00:00:00.000Z`;
  }
  return dateStr;
}
```

## Changes

### 1. Zod Schemas — `lib/validations/trip.ts`

Extract shared `validateDateRange` helper, apply `.refine()` to BOTH `createTripSchema` AND `createDraftSchema` (security review caught: draft is a separate schema, missing it = bypass).

Checks: `end > start`, `nights <= MAX_TRIP_NIGHTS`, `start <= 2 years from now`.

`updateTripSchema`: `.superRefine()` only validates range when BOTH dates are present. Single-date PATCHes validated at the route level.

### 2. PATCH Route — `app/api/trips/[id]/route.ts`

- Expand `currentTrip` select to include `startDate, endDate` (currently only selects `status`)
- Gate duration check: `const isDateChange = parsed.data.startDate !== undefined || parsed.data.endDate !== undefined`
- Only when `isDateChange`: merge incoming with existing, validate with `nightsBetween`
- This prevents regression on existing long trips — a user renaming a 20-night trip won't get a 400

### 3. DatesStep UI — `app/onboarding/components/DatesStep.tsx`

- Compute `maxEndDate` = startDate + 14 days, set as `max` on end-date input
- Show inline error when `tripLength > MAX_TRIP_NIGHTS`
- Error text: "Trips can be up to 14 nights. For longer journeys, split into multiple legs."

### 4. Onboarding page — `app/onboarding/page.tsx`

Fix `canAdvance()` for dates step:
- Change `endDate >= startDate` to strict `endDate > startDate` (zero-night trips are invalid)
- Add `nightsBetween(startDate, endDate) <= MAX_TRIP_NIGHTS` check

### 5. TripSettings — `components/trip/TripSettings.tsx`

- Normalize dates to ISO in `getDirtyFields()` using `toMidnightISO()` (fixes existing bug: bare YYYY-MM-DD fails Zod `.datetime()`)
- Add `max` on end-date input based on startDate + 14 days
- Client-side validation before save: compute merged dates, check range
- Show error via existing `error` state

### 6. POST Routes

Schema `.refine()` handles both `POST /api/trips` and `POST /api/trips/draft` — no route-level changes needed.

## Files Modified

| File | Change |
|------|--------|
| `apps/web/lib/constants/trip.ts` | NEW: MAX_TRIP_NIGHTS, MAX_TRIP_ADVANCE_YEARS |
| `apps/web/lib/utils/dates.ts` | NEW: nightsBetween(), toMidnightISO() |
| `apps/web/lib/validations/trip.ts` | Shared refine on all 3 schemas, import constants |
| `apps/web/app/api/trips/[id]/route.ts` | PATCH: expand select, gated merged-date validation |
| `apps/web/app/onboarding/components/DatesStep.tsx` | max attr, error text |
| `apps/web/app/onboarding/page.tsx` | Fix canAdvance(): strict >, add max nights |
| `apps/web/components/trip/TripSettings.tsx` | ISO normalization, max attr, client validation |

## Tests

| File | New Tests |
|------|-----------|
| `__tests__/api/trips.test.ts` | endDate <= startDate rejected, > 14 days rejected, exactly 14 passes, startDate > 2yr rejected |
| `__tests__/api/trips-draft.test.ts` | Same boundary tests (draft schema parity) |
| `__tests__/api/trips-patch.test.ts` | Partial update exceeding 14d rejected, non-date PATCH on existing long trip passes, both dates valid/invalid |
| `__tests__/settings/TripSettings.test.tsx` | Error display on invalid range |

## Review Findings Incorporated

| Source | Finding | Resolution |
|--------|---------|------------|
| Architect | currentTrip only selects status | Expand to include startDate, endDate |
| Architect | String comparison >= allows 0-night | Change to strict > |
| Architect | Constants should be in shared file | lib/constants/trip.ts |
| Architect | Date diff should use YYYY-MM-DD slice | nightsBetween() utility |
| Security | createDraftSchema is separate, needs same refine | Shared validateDateRange helper |
| Security | Existing long trips break on rename PATCH | Gate check behind isDateChange |
| Security | TripSettings sends bare YYYY-MM-DD | toMidnightISO() normalization |
| Security | Extreme future dates | 2-year advance cap |

## Verification

1. `npx vitest run` — all existing + new tests pass
2. Manual: onboarding date picker enforces max, can't advance past 14 nights
3. Manual: TripSettings date edit shows error on invalid range
4. API: `curl` PATCH with 15-day range returns 400
5. API: `curl` PATCH renaming an existing 20-night trip succeeds (no regression)
