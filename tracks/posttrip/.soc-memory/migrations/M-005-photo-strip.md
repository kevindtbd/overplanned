# M-005: Photo Strip + Memory Layer

## Description
Photo upload per slot with visited map.

## Task
1. Photo upload: server-generated signed GCS URL for direct upload
2. Max 10MB, image/jpeg + image/png + image/webp only
3. Visited map: read-only map of completed slots
4. Trip summary card

## Output
apps/web/components/posttrip/PhotoStrip.tsx

## Zone
media

## Dependencies
- M-002

## Priority
60

## Target Files
- apps/web/components/posttrip/PhotoStrip.tsx
- apps/web/components/posttrip/VisitedMap.tsx
- apps/web/components/posttrip/TripSummary.tsx
- services/api/routers/upload.py

## Files
- docs/overplanned-design-v4.html
- docs/plans/vertical-plans-v2.md
