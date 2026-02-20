# M-001: Mid-Trip Schema Extension

## Description
Extend ItinerarySlot with pivot tracking fields. PivotEvent table already exists from Foundation.

## Task
Add to Prisma schema:
- ItinerarySlot: swappedFromId String?, pivotEventId String?, wasSwapped Boolean @default(false)

Run prisma migrate dev. Run codegen. Verify existing tests unbroken.

## Output
prisma/schema.prisma

## Zone
schema

## Dependencies
none

## Priority
100

## Target Files
- prisma/schema.prisma
- prisma/migrations/

## Files
- docs/plans/vertical-plans-v2.md
