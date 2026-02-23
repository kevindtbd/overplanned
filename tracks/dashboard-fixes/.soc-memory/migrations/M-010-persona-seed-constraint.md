# M-010: Constrain personaSeed JSON Size

## Description
The `personaSeed` field in trip creation accepts arbitrary JSON with no size limit. An attacker could send multi-megabyte payloads. P2 priority.

## Task
Edit `apps/web/lib/validations/trip.ts`:
- Add a size constraint to the `personaSeed` field:
  ```typescript
  personaSeed: z.record(z.unknown())
    .refine(
      (val) => JSON.stringify(val).length <= 10_000,
      { message: "personaSeed must be under 10KB" }
    )
    .optional(),
  ```

Verify: Creating a trip with a small personaSeed works. Creating a trip with a >10KB personaSeed returns a 400 validation error. Existing tests pass.

## Output
apps/web/lib/validations/trip.ts

## Zone
api

## Dependencies
none

## Priority
60

## Target Files
- apps/web/lib/validations/trip.ts

## Files
- docs/plans/dashboard-audit-compound.md
