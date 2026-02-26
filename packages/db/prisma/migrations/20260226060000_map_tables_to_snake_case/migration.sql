-- Rename all tables from PascalCase to snake_case (@@map standardization)
-- ALTER TABLE RENAME is metadata-only in PostgreSQL (instant, no table rewrite)
-- FK constraints, indexes, and sequences automatically track the rename

-- Auth
ALTER TABLE "User" RENAME TO "users";
ALTER TABLE "Session" RENAME TO "sessions";
ALTER TABLE "Account" RENAME TO "accounts";
ALTER TABLE "VerificationToken" RENAME TO "verification_tokens";

-- Trips
ALTER TABLE "Trip" RENAME TO "trips";
ALTER TABLE "TripLeg" RENAME TO "trip_legs";
ALTER TABLE "TripMember" RENAME TO "trip_members";
ALTER TABLE "Message" RENAME TO "messages";
ALTER TABLE "Expense" RENAME TO "expenses";
ALTER TABLE "ItinerarySlot" RENAME TO "itinerary_slots";

-- World Knowledge
ALTER TABLE "ActivityNode" RENAME TO "activity_nodes";
ALTER TABLE "VibeTag" RENAME TO "vibe_tags";
ALTER TABLE "ActivityNodeVibeTag" RENAME TO "activity_node_vibe_tags";
ALTER TABLE "ActivityAlias" RENAME TO "activity_aliases";
ALTER TABLE "QualitySignal" RENAME TO "quality_signals";
ALTER TABLE "CityVibeProfile" RENAME TO "city_vibe_profiles";

-- Signals
ALTER TABLE "BehavioralSignal" RENAME TO "behavioral_signals";
ALTER TABLE "IntentionSignal" RENAME TO "intention_signals";
ALTER TABLE "RawEvent" RENAME TO "raw_events";

-- ML + Admin
ALTER TABLE "ModelRegistry" RENAME TO "model_registry";
ALTER TABLE "PersonaDimension" RENAME TO "persona_dimensions";
ALTER TABLE "RankingEvent" RENAME TO "ranking_events";
ALTER TABLE "PivotEvent" RENAME TO "pivot_events";
ALTER TABLE "ArbitrationEvent" RENAME TO "arbitration_events";
ALTER TABLE "ImportJob" RENAME TO "import_jobs";
ALTER TABLE "ImportPreferenceSignal" RENAME TO "import_preference_signals";
ALTER TABLE "CorpusIngestionRequest" RENAME TO "corpus_ingestion_requests";
ALTER TABLE "WriteBackRun" RENAME TO "write_back_runs";
ALTER TABLE "AuditLog" RENAME TO "audit_logs";

-- Tokens
ALTER TABLE "SharedTripToken" RENAME TO "shared_trip_tokens";
ALTER TABLE "InviteToken" RENAME TO "invite_tokens";

-- Backfill
ALTER TABLE "BackfillTrip" RENAME TO "backfill_trips";
ALTER TABLE "BackfillLeg" RENAME TO "backfill_legs";
ALTER TABLE "BackfillVenue" RENAME TO "backfill_venues";
ALTER TABLE "BackfillPhoto" RENAME TO "backfill_photos";
ALTER TABLE "TripPhoto" RENAME TO "trip_photos";
ALTER TABLE "BackfillSignal" RENAME TO "backfill_signals";
ALTER TABLE "PersonaDelta" RENAME TO "persona_deltas";

-- Settings
ALTER TABLE "UserPreference" RENAME TO "user_preferences";
ALTER TABLE "NotificationPreference" RENAME TO "notification_preferences";
ALTER TABLE "DataConsent" RENAME TO "data_consents";

-- Phantom tables (new in Prisma schema, created by Python CREATE TABLE IF NOT EXISTS)
-- These tables may or may not exist yet depending on which pipeline scripts have run.
-- Use IF EXISTS to avoid errors on fresh databases where they haven't been created.

CREATE TABLE IF NOT EXISTS "ShadowResult" (
    "id" TEXT NOT NULL,
    "modelId" TEXT NOT NULL,
    "modelVersion" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "tripId" TEXT NOT NULL,
    "shadowRankings" JSONB NOT NULL,
    "productionRankings" JSONB NOT NULL,
    "overlapAt5" DOUBLE PRECISION NOT NULL,
    "ndcgAt10" DOUBLE PRECISION NOT NULL,
    "latencyMs" INTEGER NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "ShadowResult_pkey" PRIMARY KEY ("id")
);
ALTER TABLE "ShadowResult" RENAME TO "shadow_results";

CREATE TABLE IF NOT EXISTS "EvalRun" (
    "id" TEXT NOT NULL,
    "modelId" TEXT NOT NULL,
    "modelVersion" TEXT NOT NULL,
    "hrAt5" DOUBLE PRECISION NOT NULL,
    "mrr" DOUBLE PRECISION NOT NULL,
    "ndcgAt10" DOUBLE PRECISION NOT NULL,
    "totalQueries" INTEGER NOT NULL,
    "durationMs" INTEGER NOT NULL,
    "passedGates" BOOLEAN NOT NULL,
    "gateDetails" JSONB NOT NULL DEFAULT '{}',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "EvalRun_pkey" PRIMARY KEY ("id")
);
ALTER TABLE "EvalRun" RENAME TO "eval_runs";

CREATE TABLE IF NOT EXISTS "TrainingExtractRun" (
    "id" TEXT NOT NULL,
    "targetDate" DATE NOT NULL,
    "status" TEXT NOT NULL,
    "rowsExtracted" INTEGER NOT NULL DEFAULT 0,
    "filePath" TEXT,
    "durationMs" INTEGER NOT NULL DEFAULT 0,
    "errorMessage" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "TrainingExtractRun_pkey" PRIMARY KEY ("id")
);
ALTER TABLE "TrainingExtractRun" RENAME TO "training_extract_runs";

CREATE TABLE IF NOT EXISTS "PersonaUpdateRun" (
    "id" SERIAL NOT NULL,
    "runDate" DATE NOT NULL,
    "status" TEXT NOT NULL,
    "usersUpdated" INTEGER NOT NULL DEFAULT 0,
    "dimensionsUpdated" INTEGER NOT NULL DEFAULT 0,
    "durationMs" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "PersonaUpdateRun_pkey" PRIMARY KEY ("id")
);
ALTER TABLE "PersonaUpdateRun" RENAME TO "persona_update_runs";

CREATE TABLE IF NOT EXISTS "PushToken" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "deviceToken" TEXT NOT NULL,
    "deviceId" TEXT NOT NULL,
    "platform" TEXT NOT NULL,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    CONSTRAINT "PushToken_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "PushToken_userId_deviceId_key" ON "PushToken"("userId", "deviceId");
ALTER TABLE "PushToken" RENAME TO "push_tokens";

CREATE TABLE IF NOT EXISTS "EmailPreference" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "category" TEXT NOT NULL,
    "unsubscribed" BOOLEAN NOT NULL DEFAULT false,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    CONSTRAINT "EmailPreference_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "EmailPreference_userId_category_key" ON "EmailPreference"("userId", "category");
ALTER TABLE "EmailPreference" RENAME TO "email_preferences";
