-- Migration: prelaunch_behavioral_scaffolding
-- Pre-launch schema additions for behavioral data capture.
-- All new columns are nullable or carry defaults (backward compatible).
-- IMPORTANT: metadata column on BehavioralSignal uses ADD COLUMN IF NOT EXISTS
-- because that column already exists in production (SA model maps signal_metadata -> metadata).

-- ===========================================================================
-- BehavioralSignal: candidateSetId, candidateIds, metadata (reconcile), index
-- ===========================================================================

ALTER TABLE "BehavioralSignal"
  ADD COLUMN IF NOT EXISTS "candidateSetId" TEXT,
  ADD COLUMN IF NOT EXISTS "candidateIds"   TEXT[]  NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS "metadata"       JSONB;

-- candidateSetId lookup index (for join to RankingEvent)
CREATE INDEX IF NOT EXISTS "BehavioralSignal_candidateSetId_idx"
  ON "BehavioralSignal" ("candidateSetId");

-- ===========================================================================
-- ActivityNode: behavioralUpdatedAt
-- ===========================================================================

ALTER TABLE "ActivityNode"
  ADD COLUMN IF NOT EXISTS "behavioralUpdatedAt" TIMESTAMP(3);

-- ===========================================================================
-- RawEvent: trainingExtracted, extractedAt, compound index
-- ===========================================================================

ALTER TABLE "RawEvent"
  ADD COLUMN IF NOT EXISTS "trainingExtracted" BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS "extractedAt"       TIMESTAMP(3);

-- Compound index for training extraction pipeline scans
CREATE INDEX IF NOT EXISTS "RawEvent_trainingExtracted_createdAt_idx"
  ON "RawEvent" ("trainingExtracted", "createdAt");

-- ===========================================================================
-- RankingEvent: acceptedId, rejectedIds, viewedIds, viewDurations,
--               weatherContext, personaSnapshot, candidateSetId (unique)
-- ===========================================================================

ALTER TABLE "RankingEvent"
  ADD COLUMN IF NOT EXISTS "acceptedId"      TEXT,
  ADD COLUMN IF NOT EXISTS "rejectedIds"     TEXT[]  NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS "viewedIds"       TEXT[]  NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS "viewDurations"   JSONB,
  ADD COLUMN IF NOT EXISTS "weatherContext"  JSONB,
  ADD COLUMN IF NOT EXISTS "personaSnapshot" JSONB,
  ADD COLUMN IF NOT EXISTS "candidateSetId"  TEXT;

-- Unique constraint: one RankingEvent per candidate set presentation
CREATE UNIQUE INDEX IF NOT EXISTS "RankingEvent_candidateSetId_key"
  ON "RankingEvent" ("candidateSetId");

-- ===========================================================================
-- SignalType enum: add new pre-trip slot lifecycle values
-- ALTER TYPE ... ADD VALUE cannot run inside a transaction block.
-- Prisma Migrate wraps DDL in a transaction, but ALTER TYPE ADD VALUE is
-- auto-committed by PostgreSQL before the transaction commits — this is safe.
-- ===========================================================================

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_enum
    WHERE enumlabel = 'pre_trip_slot_swap'
      AND enumtypid = '"SignalType"'::regtype
  ) THEN
    ALTER TYPE "SignalType" ADD VALUE 'pre_trip_slot_swap';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_enum
    WHERE enumlabel = 'pre_trip_slot_removed'
      AND enumtypid = '"SignalType"'::regtype
  ) THEN
    ALTER TYPE "SignalType" ADD VALUE 'pre_trip_slot_removed';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_enum
    WHERE enumlabel = 'pre_trip_slot_added'
      AND enumtypid = '"SignalType"'::regtype
  ) THEN
    ALTER TYPE "SignalType" ADD VALUE 'pre_trip_slot_added';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_enum
    WHERE enumlabel = 'pre_trip_reorder'
      AND enumtypid = '"SignalType"'::regtype
  ) THEN
    ALTER TYPE "SignalType" ADD VALUE 'pre_trip_reorder';
  END IF;
END
$$;

-- ===========================================================================
-- QualitySignal: extractionMetadata (seeding pipeline provenance)
-- ===========================================================================

ALTER TABLE "QualitySignal"
  ADD COLUMN IF NOT EXISTS "extractionMetadata" JSONB;
