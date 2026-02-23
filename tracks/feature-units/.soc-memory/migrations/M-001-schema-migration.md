# M-001: Schema Migration

## Description
Add new fields, enum values, and indexes to Prisma schema for the feature units sprint. This is the GATE migration — nothing else runs until this completes.

## Task
Edit `prisma/schema.prisma` to add:

1. **New fields on Trip model** (after `completedAt`):
   ```prisma
   packingList     Json?      // LLM-generated checklist
   reflectionData  Json?      // Post-trip ratings + feedback, keyed by userId
   ```

2. **New field on ItinerarySlot model** (after `wasSwapped`):
   ```prisma
   ownerTip        String?    // LLM-generated local tip (migrated from voteState.narrativeHint)
   ```

3. **New index on TripMember model** (after the @@unique):
   ```prisma
   @@index([tripId, status])
   ```

4. **New SignalType enum values** (add at end of enum, before closing brace):
   ```prisma
   // Feature units
   vote_cast
   invite_accepted
   invite_declined
   trip_shared
   trip_imported
   packing_checked
   packing_unchecked
   mood_reported
   slot_moved
   ```

5. Run migration:
   ```bash
   cd /home/pogchamp/Desktop/overplanned && npx prisma migrate dev --name feature-units-schema
   ```

6. Verify `npx prisma generate` succeeds and `npx tsc --noEmit` passes.

## Output
prisma/schema.prisma
prisma/migrations/YYYYMMDD_feature_units_schema/migration.sql

## Zone
schema

## Dependencies
none

## Priority
100

## Target Files
- prisma/schema.prisma
