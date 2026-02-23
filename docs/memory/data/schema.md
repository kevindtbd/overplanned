# Data / Schema & Prisma

## Current State
- 34+ Prisma models
- Key additions: TripLeg, BackfillLeg, expanded UserPreference/NotificationPreference

## Key Schema Decisions
- Trip lost destination/city/country/timezone (moved to TripLeg)
- TripLeg: position-ordered, @@unique([tripId, position]), transit fields
- ItinerarySlot gained tripLegId FK
- ownerTip on ItinerarySlot (separated from voteState per architect review)
- @@index([tripId, status]) on TripMember (security performance)
- `@auth/prisma-adapter` expects `image` on User (adapter writes `image`, app reads `avatarUrl`)

## Core Tables
users, trips, trip_legs, itinerary_slots, activity_nodes, behavioral_signals,
intention_signals, raw_events, vibe_tags, quality_signals, model_registry,
pivot_events, trip_members, packing_lists, backfill_legs, user_preferences,
notification_preferences, share_tokens, invite_tokens

## Debugging Patterns
- Prisma select fields are runtime-fragile — check ALL select/include blocks when schema changes
- Raw SQL tables must be in Prisma schema or `prisma db push` drops them
- Non-UUID test IDs fail Zod before business logic — always use valid UUIDs

## See Also
- Detailed schema contracts: legacy `memory/schema-contracts.md`
- Schema revisions: legacy `memory/schema-revisions.md`
