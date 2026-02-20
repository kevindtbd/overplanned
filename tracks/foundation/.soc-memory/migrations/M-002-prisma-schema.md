# M-002: Prisma Schema (22 models)

## Description
Define the complete database schema as Prisma models. This is the single source of truth for all data contracts. Split into logical sub-migrations for clarity but delivered as one schema.prisma file.

## Task
Create prisma/schema.prisma with all 22 models:

**Core (002a):** User, Session, Account, VerificationToken, Trip (with timezone String), TripMember, ItinerarySlot

**World Knowledge (002b):** ActivityNode (with coarse ActivityCategory enum + subcategory String?, foursquareId, googlePlaceId, canonicalName, resolvedToId, isCanonical, convergenceScore, authorityScore), VibeTag (slug, name, category, isActive, sortOrder), ActivityNodeVibeTag (junction with source + score), ActivityAlias, QualitySignal (per-source, rawExcerpt with 30-day purge)

**Signals (002c):** BehavioralSignal (with composite indexes on userId+createdAt, userId+tripId+signalType, activityNodeId+signalType, weatherContext Json?), IntentionSignal (separate from actions, source field, confidence), RawEvent (append-only firehose, clientEventId for dedup, intentClass enum, extracted queryable columns, @@unique on userId+clientEventId)

**ML + Admin (002d):** ModelRegistry (with artifactHash), PivotEvent, AuditLog (append-only, indexes on actorId+createdAt and targetType+targetId)

**Tokens (002e):** SharedTripToken (crypto random, 90-day expiry, view/import counts), InviteToken (single-use default, 7-day expiry, role: member only, never organizer)

Enums: TripRole (organizer, member), TripStatus, SlotType, SlotStatus, ActivityCategory (11 coarse: dining, drinks, culture, outdoors, active, entertainment, shopping, experience, nightlife, group_activity, wellness), SignalType, IntentClass (explicit, implicit, contextual), ModelType, ModelStage, PivotTriggerType, PivotStatus

Create prisma/seed.ts:
- 42 vibe tags from a vibe-tags.json constant
- 1 test user (beta tier)
- 1 test admin (systemRole: admin)

Run `npx prisma migrate dev` and `npx prisma db seed`.

Reference memory files for exact field definitions:
- Read /home/pogchamp/.claude/projects/-home-pogchamp-Desktop-overplanned/memory/schema-contracts.md
- Read /home/pogchamp/.claude/projects/-home-pogchamp-Desktop-overplanned/memory/schema-revisions.md

Deliverable: `npx prisma studio` shows all 22 tables with seed data.

## Output
prisma/schema.prisma

## Zone
schema

## Dependencies
- M-001

## Priority
90

## Target Files
- prisma/schema.prisma
- prisma/seed.ts
- prisma/migrations/

## Files
- docs/plans/vertical-plans-v2.md
