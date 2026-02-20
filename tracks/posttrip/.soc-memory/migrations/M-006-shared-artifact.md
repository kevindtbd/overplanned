# M-006: Shared Trip Artifact

## Description
Public memory page using SharedTripToken infrastructure.

## Task
1. Extends SharedTripToken (Track 4) or creates new token for solo trips
2. Public page: photo strip + itinerary + highlights
3. Same security as Track 4 M-006 (XSS prevention, CSP, rate limiting)

## Output
apps/web/app/memory/[token]/page.tsx

## Zone
sharing

## Dependencies
- M-005

## Priority
50

## Target Files
- apps/web/app/memory/[token]/page.tsx

## Files
- apps/web/app/s/[token]/page.tsx
- docs/plans/vertical-plans-v2.md
