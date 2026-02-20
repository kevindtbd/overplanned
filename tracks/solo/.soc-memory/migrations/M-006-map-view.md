# M-006: Map View

## Description
Map visualization of itinerary slots. Desktop sidebar + canvas, mobile full-screen with bottom sheet.

## Task
Create apps/web/components/map/MapView.tsx:
- Desktop: sidebar list (left) + map canvas (right)
- Mobile: full-screen map with bottom sheet for slot details
- Pins colored by slotType (dining=red, culture=blue, outdoors=green, etc.)
- Pin tap → slot detail popup (reuses SlotCard component)
- Day filter: show only current day's slots
- Use a lightweight map library (Mapbox GL JS or Leaflet)

Note: This is the last "core component" that Track 4 and 5 depend on.

## Output
apps/web/components/map/MapView.tsx

## Zone
ui-components

## Dependencies
- M-005

## Priority
65

## Target Files
- apps/web/components/map/MapView.tsx
- apps/web/components/map/MapPin.tsx
- apps/web/components/map/SlotBottomSheet.tsx
- apps/web/app/trip/[id]/map/page.tsx

## Files
- docs/overplanned-design-v4.html
- docs/plans/vertical-plans-v2.md
