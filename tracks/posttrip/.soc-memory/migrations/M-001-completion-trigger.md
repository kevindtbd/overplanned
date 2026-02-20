# M-001: Trip Completion Trigger

## Description
Auto-transition trip to completed status when endDate passes in the trip's timezone.

## Task
1. Timezone-aware comparison: convert Trip.endDate to UTC using Trip.timezone, compare to now()
2. Auto-transition: Trip.status → completed, set Trip.completedAt
3. Manual option: user marks trip as done via button
4. Scheduled job: check trips hourly for completion

## Output
services/api/posttrip/completion.py

## Zone
completion

## Dependencies
none

## Priority
100

## Target Files
- services/api/posttrip/completion.py

## Files
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
