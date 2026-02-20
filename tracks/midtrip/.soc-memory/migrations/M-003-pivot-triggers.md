# M-003: Pivot Trigger Detection

## Description
Detect conditions that warrant itinerary changes and create PivotEvents.

## Task
1. Weather trigger: rain/storm + outdoor category slot
2. Venue closure: Google Places hours vs current time
3. Time overrun: slot endTime vs now (timezone-aware via Trip.timezone)
4. User mood: explicit "not feeling it" button
5. Each trigger → PivotEvent with status: proposed + ranked alternatives from ActivitySearchService
6. MAX_PIVOT_DEPTH=1 enforced

## Output
services/api/pivot/triggers.py

## Zone
pivot

## Dependencies
- M-002

## Priority
80

## Target Files
- services/api/pivot/triggers.py
- services/api/pivot/detector.py

## Files
- services/api/weather/service.py
- services/api/search/service.py
- docs/plans/vertical-plans-v2.md
