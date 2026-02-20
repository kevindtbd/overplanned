# M-004: Day View

## Description
Timeline layout showing one day of the itinerary.

## Task
Create apps/web/components/trip/DayView.tsx:
- Timeline layout per day
- Slot cards arranged vertically with time markers
- Day navigation: swipe (mobile) or tabs (desktop)
- Status indicators per slot: confirmed (green), proposed (amber), completed (grey)
- Time display respects Trip.timezone
- Empty state for days with no slots

Create apps/web/app/trip/[id]/page.tsx — main trip view that shows DayView.

## Output
apps/web/components/trip/DayView.tsx

## Zone
ui-components

## Dependencies
- M-003

## Priority
75

## Target Files
- apps/web/components/trip/DayView.tsx
- apps/web/components/trip/DayNavigation.tsx
- apps/web/app/trip/[id]/page.tsx

## Files
- docs/overplanned-design-v4.html
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
