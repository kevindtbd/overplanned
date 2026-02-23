# Server / Pivot

## Routes
- `app/api/trips/[id]/pivot/route.ts` — Create pivot event
- `app/api/trips/[id]/pivot/[pivotId]/route.ts` — Resolve pivot

## Patterns
- 5 trigger types: weather, venue closed, time overrun, user mood, manual
- Scoring system for alternative selection
- Active cap: 3 max active pivots per trip
- Vote state reset on swap (clears stale votes from replaced slot)
- Cascade evaluation: selective downstream re-solve

## Learnings
- (space for future compound learnings)
