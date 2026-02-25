-- ============================================================================
-- Catchup migration: bring production DB in sync with current Prisma schema
-- Covers: new enums, new enum values, new columns on existing tables,
--         21 new tables, all missing indexes and foreign keys
-- ============================================================================

-- ============================================================================
-- SECTION 1: New Enums
-- ============================================================================

-- CreateEnum
DO $$ BEGIN
  CREATE TYPE "ConfidenceTier" AS ENUM ('tier_2', 'tier_3', 'tier_4');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- CreateEnum
DO $$ BEGIN
  CREATE TYPE "BackfillStatus" AS ENUM ('processing', 'extracting', 'resolving', 'checking', 'complete', 'rejected', 'quarantined', 'archived');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- CreateEnum
DO $$ BEGIN
  CREATE TYPE "TripContext" AS ENUM ('solo', 'partner', 'family', 'friends', 'work');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- CreateEnum
DO $$ BEGIN
  CREATE TYPE "SlotCompletionSignal" AS ENUM ('confirmed_attended', 'likely_attended', 'confirmed_skipped', 'pivot_replaced', 'no_show_ambiguous');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- CreateEnum
DO $$ BEGIN
  CREATE TYPE "ImportJobStatus" AS ENUM ('pending', 'processing', 'complete', 'failed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- CreateEnum
DO $$ BEGIN
  CREATE TYPE "CorpusIngestionStatus" AS ENUM ('pending', 'matched', 'unmatched', 'rejected');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================================
-- SECTION 2: New SignalType enum values
-- (init had 31 values, schema now has 45 — adding 14 new values)
-- ============================================================================

-- Feature units signals
ALTER TYPE "SignalType" ADD VALUE IF NOT EXISTS 'trip_vibe_rating';
ALTER TYPE "SignalType" ADD VALUE IF NOT EXISTS 'vote_cast';
ALTER TYPE "SignalType" ADD VALUE IF NOT EXISTS 'invite_accepted';
ALTER TYPE "SignalType" ADD VALUE IF NOT EXISTS 'invite_declined';
ALTER TYPE "SignalType" ADD VALUE IF NOT EXISTS 'trip_shared';
ALTER TYPE "SignalType" ADD VALUE IF NOT EXISTS 'trip_imported';
ALTER TYPE "SignalType" ADD VALUE IF NOT EXISTS 'packing_checked';
ALTER TYPE "SignalType" ADD VALUE IF NOT EXISTS 'packing_unchecked';
ALTER TYPE "SignalType" ADD VALUE IF NOT EXISTS 'mood_reported';
ALTER TYPE "SignalType" ADD VALUE IF NOT EXISTS 'slot_moved';

-- V2 ML signals
ALTER TYPE "SignalType" ADD VALUE IF NOT EXISTS 'post_disambiguation';
ALTER TYPE "SignalType" ADD VALUE IF NOT EXISTS 'negative_preference';
ALTER TYPE "SignalType" ADD VALUE IF NOT EXISTS 'rejection_recovery_trigger';

-- ============================================================================
-- SECTION 3: New columns on existing tables
-- ============================================================================

-- User: add "image" column (was added manually per user note, but ensure it exists)
ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "image" TEXT;

-- Trip: add new columns that exist in schema but not in init migration
ALTER TABLE "Trip" ADD COLUMN IF NOT EXISTS "name" TEXT;
ALTER TABLE "Trip" ADD COLUMN IF NOT EXISTS "currency" TEXT NOT NULL DEFAULT 'USD';
ALTER TABLE "Trip" ADD COLUMN IF NOT EXISTS "packingList" JSONB;
ALTER TABLE "Trip" ADD COLUMN IF NOT EXISTS "reflectionData" JSONB;

-- Trip: drop columns that were in init but removed from schema (moved to TripLeg)
-- Using IF EXISTS for safety
ALTER TABLE "Trip" DROP COLUMN IF EXISTS "destination";
ALTER TABLE "Trip" DROP COLUMN IF EXISTS "city";
ALTER TABLE "Trip" DROP COLUMN IF EXISTS "country";
ALTER TABLE "Trip" DROP COLUMN IF EXISTS "timezone";

-- ItinerarySlot: add tripLegId, ownerTip, assignedTo, completionSignal
ALTER TABLE "ItinerarySlot" ADD COLUMN IF NOT EXISTS "tripLegId" TEXT;
ALTER TABLE "ItinerarySlot" ADD COLUMN IF NOT EXISTS "ownerTip" TEXT;
ALTER TABLE "ItinerarySlot" ADD COLUMN IF NOT EXISTS "assignedTo" TEXT[] DEFAULT ARRAY[]::TEXT[];
ALTER TABLE "ItinerarySlot" ADD COLUMN IF NOT EXISTS "completionSignal" "SlotCompletionSignal";

-- BehavioralSignal: add V2 ML columns (subflow, signal_weight, source)
ALTER TABLE "BehavioralSignal" ADD COLUMN IF NOT EXISTS "subflow" TEXT;
ALTER TABLE "BehavioralSignal" ADD COLUMN IF NOT EXISTS "signal_weight" DOUBLE PRECISION NOT NULL DEFAULT 1.0;
ALTER TABLE "BehavioralSignal" ADD COLUMN IF NOT EXISTS "source" TEXT NOT NULL DEFAULT 'user_behavioral';

-- ActivityNode: add V2 ML scoring + feedback loop columns
ALTER TABLE "ActivityNode" ADD COLUMN IF NOT EXISTS "tourist_score" DOUBLE PRECISION;
ALTER TABLE "ActivityNode" ADD COLUMN IF NOT EXISTS "tourist_local_divergence" DOUBLE PRECISION;
ALTER TABLE "ActivityNode" ADD COLUMN IF NOT EXISTS "impression_count" INTEGER NOT NULL DEFAULT 0;
ALTER TABLE "ActivityNode" ADD COLUMN IF NOT EXISTS "acceptance_count" INTEGER NOT NULL DEFAULT 0;
ALTER TABLE "ActivityNode" ADD COLUMN IF NOT EXISTS "behavioral_quality_score" DOUBLE PRECISION NOT NULL DEFAULT 0.5;
ALTER TABLE "ActivityNode" ADD COLUMN IF NOT EXISTS "llm_served_count" INTEGER NOT NULL DEFAULT 0;
ALTER TABLE "ActivityNode" ADD COLUMN IF NOT EXISTS "ml_served_count" INTEGER NOT NULL DEFAULT 0;

-- ============================================================================
-- SECTION 4: Missing indexes on existing tables
-- ============================================================================

-- TripMember: compound index on [tripId, status] (missing from init)
CREATE INDEX IF NOT EXISTS "TripMember_tripId_status_idx" ON "TripMember"("tripId", "status");

-- ItinerarySlot: index on tripLegId
CREATE INDEX IF NOT EXISTS "ItinerarySlot_tripLegId_idx" ON "ItinerarySlot"("tripLegId");

-- BehavioralSignal: updated compound index with source (V2)
-- The old index BehavioralSignal_userId_tripId_signalType_idx exists from init
-- Add the new 4-column version
CREATE INDEX IF NOT EXISTS "BehavioralSignal_userId_tripId_signalType_source_idx" ON "BehavioralSignal"("userId", "tripId", "signalType", "source");

-- ============================================================================
-- SECTION 5: New tables (21 tables)
-- Note: FK constraints for existing tables referencing new tables are added
--       AFTER the referenced table is created.
-- ============================================================================

-- CreateTable: TripLeg
CREATE TABLE IF NOT EXISTS "TripLeg" (
    "id" TEXT NOT NULL,
    "tripId" TEXT NOT NULL,
    "position" INTEGER NOT NULL,
    "city" TEXT NOT NULL,
    "country" TEXT NOT NULL,
    "timezone" TEXT,
    "destination" TEXT NOT NULL,
    "startDate" TIMESTAMP(3) NOT NULL,
    "endDate" TIMESTAMP(3) NOT NULL,
    "arrivalTime" TEXT,
    "departureTime" TEXT,
    "transitMode" TEXT,
    "transitDurationMin" INTEGER,
    "transitCostHint" TEXT,
    "transitConfirmed" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "TripLeg_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "TripLeg_tripId_position_key" ON "TripLeg"("tripId", "position");
CREATE INDEX IF NOT EXISTS "TripLeg_tripId_idx" ON "TripLeg"("tripId");
CREATE INDEX IF NOT EXISTS "TripLeg_city_idx" ON "TripLeg"("city");

ALTER TABLE "TripLeg" ADD CONSTRAINT "TripLeg_tripId_fkey" FOREIGN KEY ("tripId") REFERENCES "Trip"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- ItinerarySlot -> TripLeg FK (deferred from Section 4 — TripLeg must exist first)
ALTER TABLE "ItinerarySlot" ADD CONSTRAINT "ItinerarySlot_tripLegId_fkey" FOREIGN KEY ("tripLegId") REFERENCES "TripLeg"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- CreateTable: Message
CREATE TABLE IF NOT EXISTS "Message" (
    "id" TEXT NOT NULL,
    "tripId" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "body" TEXT NOT NULL,
    "slotRefId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Message_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "Message_tripId_createdAt_idx" ON "Message"("tripId", "createdAt");

ALTER TABLE "Message" ADD CONSTRAINT "Message_tripId_fkey" FOREIGN KEY ("tripId") REFERENCES "Trip"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Message" ADD CONSTRAINT "Message_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "Message" ADD CONSTRAINT "Message_slotRefId_fkey" FOREIGN KEY ("slotRefId") REFERENCES "ItinerarySlot"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- CreateTable: Expense
CREATE TABLE IF NOT EXISTS "Expense" (
    "id" TEXT NOT NULL,
    "tripId" TEXT NOT NULL,
    "paidById" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "amountCents" INTEGER NOT NULL,
    "splitWith" TEXT[],
    "slotId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Expense_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "Expense_tripId_createdAt_idx" ON "Expense"("tripId", "createdAt");

ALTER TABLE "Expense" ADD CONSTRAINT "Expense_tripId_fkey" FOREIGN KEY ("tripId") REFERENCES "Trip"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Expense" ADD CONSTRAINT "Expense_paidById_fkey" FOREIGN KEY ("paidById") REFERENCES "User"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- CreateTable: CityVibeProfile
CREATE TABLE IF NOT EXISTS "CityVibeProfile" (
    "id" TEXT NOT NULL,
    "city" TEXT NOT NULL,
    "country" TEXT NOT NULL,
    "vibeKey" TEXT NOT NULL,
    "score" DOUBLE PRECISION NOT NULL,
    "nodeCount" INTEGER NOT NULL,
    "catCount" INTEGER NOT NULL,
    "imageUrl" TEXT,
    "tagline" TEXT,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "CityVibeProfile_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "CityVibeProfile_city_vibeKey_key" ON "CityVibeProfile"("city", "vibeKey");
CREATE INDEX IF NOT EXISTS "CityVibeProfile_vibeKey_score_idx" ON "CityVibeProfile"("vibeKey", "score");
CREATE INDEX IF NOT EXISTS "CityVibeProfile_city_idx" ON "CityVibeProfile"("city");

-- CreateTable: PersonaDimension
CREATE TABLE IF NOT EXISTS "PersonaDimension" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "dimension" TEXT NOT NULL,
    "value" TEXT NOT NULL,
    "confidence" DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    "source" TEXT NOT NULL DEFAULT 'onboarding',
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "PersonaDimension_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "PersonaDimension_userId_dimension_key" ON "PersonaDimension"("userId", "dimension");
CREATE INDEX IF NOT EXISTS "PersonaDimension_userId_idx" ON "PersonaDimension"("userId");
CREATE INDEX IF NOT EXISTS "PersonaDimension_dimension_value_idx" ON "PersonaDimension"("dimension", "value");

-- CreateTable: RankingEvent
CREATE TABLE IF NOT EXISTS "RankingEvent" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "tripId" TEXT NOT NULL,
    "sessionId" TEXT,
    "dayNumber" INTEGER NOT NULL,
    "modelName" TEXT NOT NULL,
    "modelVersion" TEXT NOT NULL,
    "candidateIds" TEXT[],
    "rankedIds" TEXT[],
    "selectedIds" TEXT[],
    "surface" TEXT NOT NULL,
    "shadowModelName" TEXT,
    "shadowModelVersion" TEXT,
    "shadowRankedIds" TEXT[],
    "latencyMs" INTEGER,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "RankingEvent_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "RankingEvent_userId_createdAt_idx" ON "RankingEvent"("userId", "createdAt");
CREATE INDEX IF NOT EXISTS "RankingEvent_tripId_dayNumber_idx" ON "RankingEvent"("tripId", "dayNumber");
CREATE INDEX IF NOT EXISTS "RankingEvent_modelName_modelVersion_idx" ON "RankingEvent"("modelName", "modelVersion");

-- CreateTable: ArbitrationEvent
CREATE TABLE IF NOT EXISTS "ArbitrationEvent" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "tripId" TEXT NOT NULL,
    "mlTop3" TEXT[],
    "llmTop3" TEXT[],
    "arbitrationRule" TEXT NOT NULL,
    "servedSource" TEXT NOT NULL,
    "accepted" BOOLEAN,
    "agreementScore" DOUBLE PRECISION,
    "contextSnapshot" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ArbitrationEvent_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "ArbitrationEvent_userId_createdAt_idx" ON "ArbitrationEvent"("userId", "createdAt");
CREATE INDEX IF NOT EXISTS "ArbitrationEvent_tripId_idx" ON "ArbitrationEvent"("tripId");
CREATE INDEX IF NOT EXISTS "ArbitrationEvent_arbitrationRule_idx" ON "ArbitrationEvent"("arbitrationRule");

ALTER TABLE "ArbitrationEvent" ADD CONSTRAINT "ArbitrationEvent_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- CreateTable: ImportJob
CREATE TABLE IF NOT EXISTS "ImportJob" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "status" "ImportJobStatus" NOT NULL DEFAULT 'pending',
    "parserVersion" TEXT,
    "conversationsFound" INTEGER NOT NULL DEFAULT 0,
    "travelConversations" INTEGER NOT NULL DEFAULT 0,
    "signalsExtracted" INTEGER NOT NULL DEFAULT 0,
    "errorMessage" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ImportJob_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "ImportJob_userId_status_idx" ON "ImportJob"("userId", "status");

ALTER TABLE "ImportJob" ADD CONSTRAINT "ImportJob_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- CreateTable: ImportPreferenceSignal
CREATE TABLE IF NOT EXISTS "ImportPreferenceSignal" (
    "id" TEXT NOT NULL,
    "importJobId" TEXT NOT NULL,
    "dimension" TEXT NOT NULL,
    "direction" TEXT NOT NULL,
    "confidence" DOUBLE PRECISION NOT NULL,
    "sourceText" TEXT,
    "piiScrubbed" BOOLEAN NOT NULL DEFAULT false,
    "sourceTextExpiresAt" TIMESTAMP(3),
    "trainingExcluded" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ImportPreferenceSignal_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "ImportPreferenceSignal_importJobId_idx" ON "ImportPreferenceSignal"("importJobId");
CREATE INDEX IF NOT EXISTS "ImportPreferenceSignal_dimension_direction_idx" ON "ImportPreferenceSignal"("dimension", "direction");

ALTER TABLE "ImportPreferenceSignal" ADD CONSTRAINT "ImportPreferenceSignal_importJobId_fkey" FOREIGN KEY ("importJobId") REFERENCES "ImportJob"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- CreateTable: CorpusIngestionRequest
CREATE TABLE IF NOT EXISTS "CorpusIngestionRequest" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "tripId" TEXT,
    "rawPlaceName" TEXT NOT NULL,
    "source" TEXT NOT NULL,
    "status" "CorpusIngestionStatus" NOT NULL DEFAULT 'pending',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "CorpusIngestionRequest_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "CorpusIngestionRequest_userId_idx" ON "CorpusIngestionRequest"("userId");
CREATE INDEX IF NOT EXISTS "CorpusIngestionRequest_status_idx" ON "CorpusIngestionRequest"("status");

ALTER TABLE "CorpusIngestionRequest" ADD CONSTRAINT "CorpusIngestionRequest_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- CreateTable: WriteBackRun
CREATE TABLE IF NOT EXISTS "WriteBackRun" (
    "id" TEXT NOT NULL,
    "runDate" TIMESTAMP(3) NOT NULL,
    "status" TEXT NOT NULL,
    "rowsUpdated" INTEGER NOT NULL DEFAULT 0,
    "durationMs" INTEGER,
    "errorMessage" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "WriteBackRun_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "WriteBackRun_runDate_key" ON "WriteBackRun"("runDate");

-- CreateTable: BackfillTrip
CREATE TABLE IF NOT EXISTS "BackfillTrip" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "startDate" TIMESTAMP(3),
    "endDate" TIMESTAMP(3),
    "confidenceTier" "ConfidenceTier" NOT NULL,
    "source" TEXT NOT NULL DEFAULT 'freeform',
    "rawSubmission" TEXT NOT NULL,
    "contextTag" "TripContext",
    "tripNote" TEXT,
    "status" "BackfillStatus" NOT NULL DEFAULT 'processing',
    "rejectionReason" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "BackfillTrip_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "BackfillTrip_userId_status_idx" ON "BackfillTrip"("userId", "status");

ALTER TABLE "BackfillTrip" ADD CONSTRAINT "BackfillTrip_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- CreateTable: BackfillLeg
CREATE TABLE IF NOT EXISTS "BackfillLeg" (
    "id" TEXT NOT NULL,
    "backfillTripId" TEXT NOT NULL,
    "position" INTEGER NOT NULL,
    "city" TEXT NOT NULL,
    "country" TEXT NOT NULL,
    "timezone" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "BackfillLeg_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "BackfillLeg_backfillTripId_position_key" ON "BackfillLeg"("backfillTripId", "position");
CREATE INDEX IF NOT EXISTS "BackfillLeg_backfillTripId_idx" ON "BackfillLeg"("backfillTripId");

ALTER TABLE "BackfillLeg" ADD CONSTRAINT "BackfillLeg_backfillTripId_fkey" FOREIGN KEY ("backfillTripId") REFERENCES "BackfillTrip"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- CreateTable: BackfillVenue
CREATE TABLE IF NOT EXISTS "BackfillVenue" (
    "id" TEXT NOT NULL,
    "backfillTripId" TEXT NOT NULL,
    "backfillLegId" TEXT,
    "activityNodeId" TEXT,
    "extractedName" TEXT NOT NULL,
    "extractedCategory" TEXT,
    "extractedDate" TEXT,
    "extractedSentiment" TEXT,
    "latitude" DOUBLE PRECISION,
    "longitude" DOUBLE PRECISION,
    "resolutionScore" DOUBLE PRECISION,
    "isResolved" BOOLEAN NOT NULL DEFAULT false,
    "isQuarantined" BOOLEAN NOT NULL DEFAULT false,
    "quarantineReason" TEXT,
    "wouldReturn" BOOLEAN,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "BackfillVenue_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "BackfillVenue_backfillTripId_idx" ON "BackfillVenue"("backfillTripId");
CREATE INDEX IF NOT EXISTS "BackfillVenue_activityNodeId_idx" ON "BackfillVenue"("activityNodeId");

ALTER TABLE "BackfillVenue" ADD CONSTRAINT "BackfillVenue_backfillTripId_fkey" FOREIGN KEY ("backfillTripId") REFERENCES "BackfillTrip"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "BackfillVenue" ADD CONSTRAINT "BackfillVenue_backfillLegId_fkey" FOREIGN KEY ("backfillLegId") REFERENCES "BackfillLeg"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "BackfillVenue" ADD CONSTRAINT "BackfillVenue_activityNodeId_fkey" FOREIGN KEY ("activityNodeId") REFERENCES "ActivityNode"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- CreateTable: BackfillPhoto
CREATE TABLE IF NOT EXISTS "BackfillPhoto" (
    "id" TEXT NOT NULL,
    "backfillVenueId" TEXT NOT NULL,
    "gcsPath" TEXT NOT NULL,
    "originalFilename" TEXT NOT NULL,
    "mimeType" TEXT NOT NULL,
    "exifLat" DOUBLE PRECISION,
    "exifLng" DOUBLE PRECISION,
    "exifTimestamp" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "BackfillPhoto_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "BackfillPhoto_backfillVenueId_idx" ON "BackfillPhoto"("backfillVenueId");

ALTER TABLE "BackfillPhoto" ADD CONSTRAINT "BackfillPhoto_backfillVenueId_fkey" FOREIGN KEY ("backfillVenueId") REFERENCES "BackfillVenue"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- CreateTable: TripPhoto
CREATE TABLE IF NOT EXISTS "TripPhoto" (
    "id" TEXT NOT NULL,
    "tripId" TEXT NOT NULL,
    "slotId" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "gcsPath" TEXT NOT NULL,
    "originalFilename" TEXT NOT NULL,
    "mimeType" TEXT NOT NULL,
    "sizeBytes" INTEGER,
    "exifLat" DOUBLE PRECISION,
    "exifLng" DOUBLE PRECISION,
    "exifTimestamp" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "TripPhoto_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "TripPhoto_tripId_idx" ON "TripPhoto"("tripId");
CREATE INDEX IF NOT EXISTS "TripPhoto_slotId_idx" ON "TripPhoto"("slotId");
CREATE INDEX IF NOT EXISTS "TripPhoto_userId_idx" ON "TripPhoto"("userId");

ALTER TABLE "TripPhoto" ADD CONSTRAINT "TripPhoto_tripId_fkey" FOREIGN KEY ("tripId") REFERENCES "Trip"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "TripPhoto" ADD CONSTRAINT "TripPhoto_slotId_fkey" FOREIGN KEY ("slotId") REFERENCES "ItinerarySlot"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "TripPhoto" ADD CONSTRAINT "TripPhoto_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- CreateTable: BackfillSignal
CREATE TABLE IF NOT EXISTS "BackfillSignal" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "backfillTripId" TEXT NOT NULL,
    "backfillVenueId" TEXT,
    "signalType" TEXT NOT NULL,
    "signalValue" DOUBLE PRECISION NOT NULL,
    "confidenceTier" "ConfidenceTier" NOT NULL,
    "weight" DOUBLE PRECISION NOT NULL,
    "earnedOut" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "BackfillSignal_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "BackfillSignal_userId_createdAt_idx" ON "BackfillSignal"("userId", "createdAt");
CREATE INDEX IF NOT EXISTS "BackfillSignal_backfillTripId_idx" ON "BackfillSignal"("backfillTripId");

ALTER TABLE "BackfillSignal" ADD CONSTRAINT "BackfillSignal_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "BackfillSignal" ADD CONSTRAINT "BackfillSignal_backfillTripId_fkey" FOREIGN KEY ("backfillTripId") REFERENCES "BackfillTrip"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- CreateTable: PersonaDelta
CREATE TABLE IF NOT EXISTS "PersonaDelta" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "backfillSignalId" TEXT NOT NULL,
    "dimensionName" TEXT NOT NULL,
    "personaScore" DOUBLE PRECISION NOT NULL,
    "backfillImpliedScore" DOUBLE PRECISION NOT NULL,
    "delta" DOUBLE PRECISION NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "PersonaDelta_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "PersonaDelta_userId_dimensionName_idx" ON "PersonaDelta"("userId", "dimensionName");
CREATE INDEX IF NOT EXISTS "PersonaDelta_backfillSignalId_idx" ON "PersonaDelta"("backfillSignalId");

ALTER TABLE "PersonaDelta" ADD CONSTRAINT "PersonaDelta_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "PersonaDelta" ADD CONSTRAINT "PersonaDelta_backfillSignalId_fkey" FOREIGN KEY ("backfillSignalId") REFERENCES "BackfillSignal"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- CreateTable: UserPreference
CREATE TABLE IF NOT EXISTS "UserPreference" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "dietary" TEXT[],
    "mobility" TEXT[],
    "languages" TEXT[],
    "travelFrequency" TEXT,
    "vibePreferences" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "travelStyleNote" TEXT,
    "budgetComfort" TEXT,
    "spendingPriorities" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "accommodationTypes" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "transitModes" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "preferencesNote" TEXT,
    "distanceUnit" TEXT NOT NULL DEFAULT 'mi',
    "temperatureUnit" TEXT NOT NULL DEFAULT 'F',
    "dateFormat" TEXT NOT NULL DEFAULT 'MM/DD/YYYY',
    "timeFormat" TEXT NOT NULL DEFAULT '12h',
    "theme" TEXT NOT NULL DEFAULT 'system',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "UserPreference_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "UserPreference_userId_key" ON "UserPreference"("userId");

ALTER TABLE "UserPreference" ADD CONSTRAINT "UserPreference_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- CreateTable: NotificationPreference
CREATE TABLE IF NOT EXISTS "NotificationPreference" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "tripReminders" BOOLEAN NOT NULL DEFAULT true,
    "morningBriefing" BOOLEAN NOT NULL DEFAULT true,
    "groupActivity" BOOLEAN NOT NULL DEFAULT true,
    "postTripPrompt" BOOLEAN NOT NULL DEFAULT true,
    "citySeeded" BOOLEAN NOT NULL DEFAULT true,
    "inspirationNudges" BOOLEAN NOT NULL DEFAULT false,
    "productUpdates" BOOLEAN NOT NULL DEFAULT false,
    "checkinReminder" BOOLEAN NOT NULL DEFAULT false,
    "preTripDaysBefore" INTEGER NOT NULL DEFAULT 3,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "NotificationPreference_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "NotificationPreference_userId_key" ON "NotificationPreference"("userId");

ALTER TABLE "NotificationPreference" ADD CONSTRAINT "NotificationPreference_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- CreateTable: DataConsent
CREATE TABLE IF NOT EXISTS "DataConsent" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "modelTraining" BOOLEAN NOT NULL DEFAULT false,
    "anonymizedResearch" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "DataConsent_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "DataConsent_userId_key" ON "DataConsent"("userId");

ALTER TABLE "DataConsent" ADD CONSTRAINT "DataConsent_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- ============================================================================
-- SECTION 7: Constraints mentioned in schema comments
-- ============================================================================

-- BehavioralSignal.signal_weight CHECK constraint: [-1.0, 3.0]
-- Use DO block to avoid error if constraint already exists
DO $$ BEGIN
  ALTER TABLE "BehavioralSignal" ADD CONSTRAINT "BehavioralSignal_signal_weight_check"
    CHECK ("signal_weight" >= -1.0 AND "signal_weight" <= 3.0);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ArbitrationEvent.contextSnapshot size constraint: pg_column_size < 65536
DO $$ BEGIN
  ALTER TABLE "ArbitrationEvent" ADD CONSTRAINT "ArbitrationEvent_contextSnapshot_size_check"
    CHECK ("contextSnapshot" IS NULL OR pg_column_size("contextSnapshot") < 65536);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================================
-- SECTION 8: Drop old BehavioralSignal 3-column index, replaced by 4-column
-- (keeping both is fine for backward compat, but schema only defines 4-col now)
-- ============================================================================

-- The init migration created BehavioralSignal_userId_tripId_signalType_idx
-- The schema now defines [userId, tripId, signalType, source]
-- Drop the old 3-column index since the 4-column one covers those queries
DROP INDEX IF EXISTS "BehavioralSignal_userId_tripId_signalType_idx";
