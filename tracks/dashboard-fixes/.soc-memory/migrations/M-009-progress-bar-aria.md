# M-009: Add ARIA to Progress Bar

## Description
TripHeroCard progress bar has no `role="progressbar"`, no `aria-valuenow`, no `aria-valuemin/max`. Invisible to screen readers — WCAG violation. P2 priority.

## Task
Edit `apps/web/components/dashboard/TripHeroCard.tsx`:
- Find the progress bar container div
- Add these attributes:
  - `role="progressbar"`
  - `aria-valuenow={clampedProgress}` (the 0-100 clamped value)
  - `aria-valuemin={0}`
  - `aria-valuemax={100}`
  - `aria-label="Planning progress"`
- Also add focus-visible zoom effect to the TripHeroCard link (currently only hover has zoom):
  - Add `focus-visible:scale-[1.03]` alongside the existing `group-hover:scale-[1.03]`

Also add `aria-label` to the TripHeroCard `<Link>` element:
- `aria-label={`View trip to ${displayName}`}`

Verify: Screen reader announces progress bar value. TripHeroCard link has descriptive label. Focus-visible zoom matches hover zoom.

## Output
apps/web/components/dashboard/TripHeroCard.tsx

## Zone
ui

## Dependencies
none

## Priority
65

## Target Files
- apps/web/components/dashboard/TripHeroCard.tsx

## Files
- docs/plans/dashboard-audit-compound.md
