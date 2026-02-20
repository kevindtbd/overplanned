# M-001: Group Trip Schema Extension

## Description
Extend Trip, ItinerarySlot, and TripMember models with group-specific fields. This migration can start immediately after Foundation completes (before Solo).

## Task
Add to Prisma schema:
- Trip: fairnessState Json?, affinityMatrix Json?, logisticsState Json?
- ItinerarySlot: voteState Json?, isContested Boolean @default(false)
- TripMember: personaSeed Json?, energyProfile Json?

Run prisma migrate dev. Run codegen. Verify ALL existing tests still pass (especially Track 3 if it exists).

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
