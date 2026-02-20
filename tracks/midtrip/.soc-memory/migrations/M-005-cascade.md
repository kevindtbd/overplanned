# M-005: Cascade Evaluation

## Description
When a slot changes, evaluate impact on same-day downstream slots.

## Task
1. Scope: same-day slots AFTER the changed slot ONLY
2. Cross-day impact = new PivotEvent, NOT automatic cascade
3. Selective re-solve: update sortOrder and startTime for affected slots
4. Timezone-aware calculations using Trip.timezone

## Output
services/api/pivot/cascade.py

## Zone
cascade

## Dependencies
- M-004

## Priority
60

## Target Files
- services/api/pivot/cascade.py

## Files
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
