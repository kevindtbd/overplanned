-- Migration: cold_start_schema_additions
-- Adds cantMiss flag to ActivityNode and negative affinity tracking to PersonaDimension.
-- All additions are backward-compatible (nullable or carry defaults).

-- ===========================================================================
-- PersonaDimension: negativeTagAffinities + version
-- ===========================================================================

ALTER TABLE "PersonaDimension"
  ADD COLUMN IF NOT EXISTS "negativeTagAffinities" JSONB,
  ADD COLUMN IF NOT EXISTS "version" INTEGER NOT NULL DEFAULT 0;

-- ===========================================================================
-- ActivityNode: cantMiss flag
-- ===========================================================================

ALTER TABLE "ActivityNode"
  ADD COLUMN IF NOT EXISTS "cantMiss" BOOLEAN NOT NULL DEFAULT false;

-- Partial index for cantMiss lookups (~0.1% are true — sparse index keeps overhead minimal)
CREATE INDEX IF NOT EXISTS "ActivityNode_cantMiss_idx"
  ON "ActivityNode" ("cantMiss")
  WHERE "cantMiss" = true;
