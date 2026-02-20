# M-009: Calendar View + .ics Export

## Description
Calendar grid view with .ics download for native calendar integration.

## Task
1. Calendar grid (apps/web/app/trip/[id]/calendar/page.tsx):
   - Month view showing trip days highlighted
   - Day cells show slot count + first slot name
   - Tap day → navigate to day view

2. .ics generation (services/api/routers/calendar.py):
   - GET /trips/{id}/calendar.ics
   - Generate iCal file with correct VTIMEZONE (from Trip.timezone)
   - Each ItinerarySlot = one VEVENT
   - Include: summary (activity name), location (lat/lng), dtstart/dtend, description

Deliverable: view trip as calendar, download .ics opens correctly in Apple Calendar / Google Calendar.

## Output
apps/web/app/trip/[id]/calendar/page.tsx

## Zone
calendar

## Dependencies
- M-004

## Priority
40

## Target Files
- apps/web/app/trip/[id]/calendar/page.tsx
- services/api/routers/calendar.py

## Files
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
