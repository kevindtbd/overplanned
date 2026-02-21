-- CreateEnum
CREATE TYPE "SubscriptionTier" AS ENUM ('free', 'beta', 'pro', 'lifetime');

-- CreateEnum
CREATE TYPE "SystemRole" AS ENUM ('user', 'admin');

-- CreateEnum
CREATE TYPE "TripMode" AS ENUM ('solo', 'group');

-- CreateEnum
CREATE TYPE "TripStatus" AS ENUM ('draft', 'planning', 'active', 'completed', 'archived');

-- CreateEnum
CREATE TYPE "TripRole" AS ENUM ('organizer', 'member');

-- CreateEnum
CREATE TYPE "MemberStatus" AS ENUM ('invited', 'joined', 'declined');

-- CreateEnum
CREATE TYPE "SlotType" AS ENUM ('anchor', 'flex', 'meal', 'rest', 'transit');

-- CreateEnum
CREATE TYPE "SlotStatus" AS ENUM ('proposed', 'voted', 'confirmed', 'active', 'completed', 'skipped');

-- CreateEnum
CREATE TYPE "ActivityCategory" AS ENUM ('dining', 'drinks', 'culture', 'outdoors', 'active', 'entertainment', 'shopping', 'experience', 'nightlife', 'group_activity', 'wellness');

-- CreateEnum
CREATE TYPE "NodeStatus" AS ENUM ('pending', 'approved', 'flagged', 'archived');

-- CreateEnum
CREATE TYPE "SignalType" AS ENUM ('slot_view', 'slot_tap', 'slot_confirm', 'slot_skip', 'slot_swap', 'slot_complete', 'slot_dwell', 'discover_swipe_right', 'discover_swipe_left', 'discover_shortlist', 'discover_remove', 'vibe_select', 'vibe_deselect', 'vibe_implicit', 'post_loved', 'post_skipped', 'post_missed', 'post_disliked', 'pivot_accepted', 'pivot_rejected', 'pivot_initiated', 'dwell_time', 'scroll_depth', 'return_visit', 'share_action', 'considered_not_chosen', 'soft_positive', 'category_preference', 'time_preference', 'geographic_preference', 'pace_signal');

-- CreateEnum
CREATE TYPE "TripPhase" AS ENUM ('pre_trip', 'active', 'post_trip');

-- CreateEnum
CREATE TYPE "IntentClass" AS ENUM ('explicit', 'implicit', 'contextual');

-- CreateEnum
CREATE TYPE "ModelStage" AS ENUM ('staging', 'ab_test', 'production', 'archived');

-- CreateEnum
CREATE TYPE "PivotTrigger" AS ENUM ('weather_change', 'venue_closed', 'time_overrun', 'user_mood', 'user_request');

-- CreateEnum
CREATE TYPE "PivotStatus" AS ENUM ('proposed', 'accepted', 'rejected', 'expired');

-- CreateTable
CREATE TABLE "User" (
    "id" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "name" TEXT,
    "avatarUrl" TEXT,
    "googleId" TEXT,
    "emailVerified" TIMESTAMP(3),
    "subscriptionTier" "SubscriptionTier" NOT NULL DEFAULT 'beta',
    "systemRole" "SystemRole" NOT NULL DEFAULT 'user',
    "featureFlags" JSONB,
    "accessCohort" TEXT,
    "stripeCustomerId" TEXT,
    "stripeSubId" TEXT,
    "stripePriceId" TEXT,
    "onboardingComplete" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "lastActiveAt" TIMESTAMP(3),

    CONSTRAINT "User_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Session" (
    "id" TEXT NOT NULL,
    "sessionToken" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "expires" TIMESTAMP(3) NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Session_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Account" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "provider" TEXT NOT NULL,
    "providerAccountId" TEXT NOT NULL,
    "refresh_token" TEXT,
    "access_token" TEXT,
    "expires_at" INTEGER,
    "token_type" TEXT,
    "scope" TEXT,
    "id_token" TEXT,
    "session_state" TEXT,

    CONSTRAINT "Account_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "VerificationToken" (
    "identifier" TEXT NOT NULL,
    "token" TEXT NOT NULL,
    "expires" TIMESTAMP(3) NOT NULL
);

-- CreateTable
CREATE TABLE "Trip" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "mode" "TripMode" NOT NULL,
    "status" "TripStatus" NOT NULL DEFAULT 'draft',
    "destination" TEXT NOT NULL,
    "city" TEXT NOT NULL,
    "country" TEXT NOT NULL,
    "timezone" TEXT NOT NULL,
    "startDate" TIMESTAMP(3) NOT NULL,
    "endDate" TIMESTAMP(3) NOT NULL,
    "groupId" TEXT,
    "memberCount" INTEGER,
    "planningProgress" DOUBLE PRECISION,
    "presetTemplate" TEXT,
    "personaSeed" JSONB,
    "fairnessState" JSONB,
    "affinityMatrix" JSONB,
    "logisticsState" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "activatedAt" TIMESTAMP(3),
    "completedAt" TIMESTAMP(3),

    CONSTRAINT "Trip_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "TripMember" (
    "id" TEXT NOT NULL,
    "tripId" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "role" "TripRole" NOT NULL,
    "status" "MemberStatus" NOT NULL DEFAULT 'invited',
    "personaSeed" JSONB,
    "energyProfile" JSONB,
    "joinedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "TripMember_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ItinerarySlot" (
    "id" TEXT NOT NULL,
    "tripId" TEXT NOT NULL,
    "activityNodeId" TEXT,
    "dayNumber" INTEGER NOT NULL,
    "sortOrder" INTEGER NOT NULL,
    "slotType" "SlotType" NOT NULL,
    "status" "SlotStatus" NOT NULL DEFAULT 'proposed',
    "startTime" TIMESTAMP(3),
    "endTime" TIMESTAMP(3),
    "durationMinutes" INTEGER,
    "isLocked" BOOLEAN NOT NULL DEFAULT false,
    "voteState" JSONB,
    "isContested" BOOLEAN NOT NULL DEFAULT false,
    "swappedFromId" TEXT,
    "pivotEventId" TEXT,
    "wasSwapped" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ItinerarySlot_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ActivityNode" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "slug" TEXT NOT NULL,
    "canonicalName" TEXT NOT NULL,
    "city" TEXT NOT NULL,
    "country" TEXT NOT NULL,
    "neighborhood" TEXT,
    "latitude" DOUBLE PRECISION NOT NULL,
    "longitude" DOUBLE PRECISION NOT NULL,
    "category" "ActivityCategory" NOT NULL,
    "subcategory" TEXT,
    "priceLevel" INTEGER,
    "hours" JSONB,
    "address" TEXT,
    "phoneNumber" TEXT,
    "websiteUrl" TEXT,
    "foursquareId" TEXT,
    "googlePlaceId" TEXT,
    "primaryImageUrl" TEXT,
    "imageSource" TEXT,
    "imageValidated" BOOLEAN NOT NULL DEFAULT false,
    "sourceCount" INTEGER NOT NULL DEFAULT 0,
    "convergenceScore" DOUBLE PRECISION,
    "authorityScore" DOUBLE PRECISION,
    "descriptionShort" TEXT,
    "descriptionLong" TEXT,
    "contentHash" TEXT,
    "lastScrapedAt" TIMESTAMP(3),
    "lastValidatedAt" TIMESTAMP(3),
    "status" "NodeStatus" NOT NULL DEFAULT 'pending',
    "flagReason" TEXT,
    "resolvedToId" TEXT,
    "isCanonical" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ActivityNode_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "VibeTag" (
    "id" TEXT NOT NULL,
    "slug" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "category" TEXT NOT NULL,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "sortOrder" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "VibeTag_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ActivityNodeVibeTag" (
    "id" TEXT NOT NULL,
    "activityNodeId" TEXT NOT NULL,
    "vibeTagId" TEXT NOT NULL,
    "score" DOUBLE PRECISION NOT NULL,
    "source" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ActivityNodeVibeTag_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ActivityAlias" (
    "id" TEXT NOT NULL,
    "activityNodeId" TEXT NOT NULL,
    "alias" TEXT NOT NULL,
    "source" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ActivityAlias_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "QualitySignal" (
    "id" TEXT NOT NULL,
    "activityNodeId" TEXT NOT NULL,
    "sourceName" TEXT NOT NULL,
    "sourceUrl" TEXT,
    "sourceAuthority" DOUBLE PRECISION NOT NULL,
    "signalType" TEXT NOT NULL,
    "rawExcerpt" TEXT,
    "extractedAt" TIMESTAMP(3) NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "QualitySignal_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "BehavioralSignal" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "tripId" TEXT,
    "slotId" TEXT,
    "activityNodeId" TEXT,
    "signalType" "SignalType" NOT NULL,
    "signalValue" DOUBLE PRECISION NOT NULL,
    "tripPhase" "TripPhase" NOT NULL,
    "rawAction" TEXT NOT NULL,
    "weatherContext" TEXT,
    "modelVersion" TEXT,
    "promptVersion" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "BehavioralSignal_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "IntentionSignal" (
    "id" TEXT NOT NULL,
    "behavioralSignalId" TEXT NOT NULL,
    "rawEventId" TEXT,
    "userId" TEXT NOT NULL,
    "intentionType" TEXT NOT NULL,
    "confidence" DOUBLE PRECISION NOT NULL,
    "source" TEXT NOT NULL,
    "userProvided" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "IntentionSignal_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "RawEvent" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "sessionId" TEXT NOT NULL,
    "tripId" TEXT,
    "activityNodeId" TEXT,
    "clientEventId" TEXT,
    "eventType" TEXT NOT NULL,
    "intentClass" "IntentClass" NOT NULL,
    "surface" TEXT,
    "payload" JSONB NOT NULL,
    "platform" TEXT,
    "screenWidth" INTEGER,
    "networkType" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "RawEvent_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ModelRegistry" (
    "id" TEXT NOT NULL,
    "modelName" TEXT NOT NULL,
    "modelVersion" TEXT NOT NULL,
    "stage" "ModelStage" NOT NULL,
    "modelType" TEXT NOT NULL,
    "description" TEXT,
    "artifactPath" TEXT,
    "artifactHash" TEXT,
    "configSnapshot" JSONB,
    "metrics" JSONB,
    "evaluatedAt" TIMESTAMP(3),
    "trainingDataRange" JSONB,
    "parentVersionId" TEXT,
    "promotedAt" TIMESTAMP(3),
    "promotedBy" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ModelRegistry_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "PivotEvent" (
    "id" TEXT NOT NULL,
    "tripId" TEXT NOT NULL,
    "slotId" TEXT NOT NULL,
    "triggerType" "PivotTrigger" NOT NULL,
    "triggerPayload" JSONB,
    "originalNodeId" TEXT NOT NULL,
    "alternativeIds" TEXT[],
    "selectedNodeId" TEXT,
    "status" "PivotStatus" NOT NULL DEFAULT 'proposed',
    "resolvedAt" TIMESTAMP(3),
    "responseTimeMs" INTEGER,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "PivotEvent_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "AuditLog" (
    "id" TEXT NOT NULL,
    "actorId" TEXT NOT NULL,
    "action" TEXT NOT NULL,
    "targetType" TEXT NOT NULL,
    "targetId" TEXT NOT NULL,
    "before" JSONB,
    "after" JSONB,
    "ipAddress" TEXT NOT NULL,
    "userAgent" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "AuditLog_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "SharedTripToken" (
    "id" TEXT NOT NULL,
    "tripId" TEXT NOT NULL,
    "token" TEXT NOT NULL,
    "createdBy" TEXT NOT NULL,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "revokedAt" TIMESTAMP(3),
    "viewCount" INTEGER NOT NULL DEFAULT 0,
    "importCount" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "SharedTripToken_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "InviteToken" (
    "id" TEXT NOT NULL,
    "tripId" TEXT NOT NULL,
    "token" TEXT NOT NULL,
    "createdBy" TEXT NOT NULL,
    "maxUses" INTEGER NOT NULL DEFAULT 1,
    "usedCount" INTEGER NOT NULL DEFAULT 0,
    "role" "TripRole" NOT NULL DEFAULT 'member',
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "revokedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "InviteToken_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "User_email_key" ON "User"("email");

-- CreateIndex
CREATE UNIQUE INDEX "User_googleId_key" ON "User"("googleId");

-- CreateIndex
CREATE UNIQUE INDEX "User_stripeCustomerId_key" ON "User"("stripeCustomerId");

-- CreateIndex
CREATE UNIQUE INDEX "Session_sessionToken_key" ON "Session"("sessionToken");

-- CreateIndex
CREATE UNIQUE INDEX "Account_provider_providerAccountId_key" ON "Account"("provider", "providerAccountId");

-- CreateIndex
CREATE UNIQUE INDEX "VerificationToken_token_key" ON "VerificationToken"("token");

-- CreateIndex
CREATE UNIQUE INDEX "VerificationToken_identifier_token_key" ON "VerificationToken"("identifier", "token");

-- CreateIndex
CREATE UNIQUE INDEX "TripMember_tripId_userId_key" ON "TripMember"("tripId", "userId");

-- CreateIndex
CREATE UNIQUE INDEX "ActivityNode_slug_key" ON "ActivityNode"("slug");

-- CreateIndex
CREATE UNIQUE INDEX "ActivityNode_foursquareId_key" ON "ActivityNode"("foursquareId");

-- CreateIndex
CREATE UNIQUE INDEX "ActivityNode_googlePlaceId_key" ON "ActivityNode"("googlePlaceId");

-- CreateIndex
CREATE UNIQUE INDEX "VibeTag_slug_key" ON "VibeTag"("slug");

-- CreateIndex
CREATE UNIQUE INDEX "ActivityNodeVibeTag_activityNodeId_vibeTagId_source_key" ON "ActivityNodeVibeTag"("activityNodeId", "vibeTagId", "source");

-- CreateIndex
CREATE INDEX "ActivityAlias_alias_idx" ON "ActivityAlias"("alias");

-- CreateIndex
CREATE INDEX "ActivityAlias_activityNodeId_idx" ON "ActivityAlias"("activityNodeId");

-- CreateIndex
CREATE INDEX "QualitySignal_activityNodeId_sourceName_idx" ON "QualitySignal"("activityNodeId", "sourceName");

-- CreateIndex
CREATE INDEX "BehavioralSignal_userId_createdAt_idx" ON "BehavioralSignal"("userId", "createdAt");

-- CreateIndex
CREATE INDEX "BehavioralSignal_userId_tripId_signalType_idx" ON "BehavioralSignal"("userId", "tripId", "signalType");

-- CreateIndex
CREATE INDEX "BehavioralSignal_activityNodeId_signalType_idx" ON "BehavioralSignal"("activityNodeId", "signalType");

-- CreateIndex
CREATE INDEX "IntentionSignal_behavioralSignalId_idx" ON "IntentionSignal"("behavioralSignalId");

-- CreateIndex
CREATE INDEX "IntentionSignal_userId_intentionType_idx" ON "IntentionSignal"("userId", "intentionType");

-- CreateIndex
CREATE INDEX "RawEvent_userId_eventType_createdAt_idx" ON "RawEvent"("userId", "eventType", "createdAt");

-- CreateIndex
CREATE INDEX "RawEvent_userId_activityNodeId_idx" ON "RawEvent"("userId", "activityNodeId");

-- CreateIndex
CREATE INDEX "RawEvent_sessionId_idx" ON "RawEvent"("sessionId");

-- CreateIndex
CREATE INDEX "RawEvent_createdAt_idx" ON "RawEvent"("createdAt");

-- CreateIndex
CREATE INDEX "RawEvent_intentClass_eventType_idx" ON "RawEvent"("intentClass", "eventType");

-- CreateIndex
CREATE UNIQUE INDEX "RawEvent_userId_clientEventId_key" ON "RawEvent"("userId", "clientEventId");

-- CreateIndex
CREATE INDEX "ModelRegistry_modelName_stage_idx" ON "ModelRegistry"("modelName", "stage");

-- CreateIndex
CREATE UNIQUE INDEX "ModelRegistry_modelName_modelVersion_key" ON "ModelRegistry"("modelName", "modelVersion");

-- CreateIndex
CREATE INDEX "PivotEvent_tripId_createdAt_idx" ON "PivotEvent"("tripId", "createdAt");

-- CreateIndex
CREATE INDEX "PivotEvent_status_idx" ON "PivotEvent"("status");

-- CreateIndex
CREATE INDEX "AuditLog_actorId_createdAt_idx" ON "AuditLog"("actorId", "createdAt");

-- CreateIndex
CREATE INDEX "AuditLog_targetType_targetId_idx" ON "AuditLog"("targetType", "targetId");

-- CreateIndex
CREATE UNIQUE INDEX "SharedTripToken_token_key" ON "SharedTripToken"("token");

-- CreateIndex
CREATE INDEX "SharedTripToken_token_idx" ON "SharedTripToken"("token");

-- CreateIndex
CREATE UNIQUE INDEX "InviteToken_token_key" ON "InviteToken"("token");

-- CreateIndex
CREATE INDEX "InviteToken_token_idx" ON "InviteToken"("token");

-- AddForeignKey
ALTER TABLE "Session" ADD CONSTRAINT "Session_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Account" ADD CONSTRAINT "Account_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TripMember" ADD CONSTRAINT "TripMember_tripId_fkey" FOREIGN KEY ("tripId") REFERENCES "Trip"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TripMember" ADD CONSTRAINT "TripMember_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ItinerarySlot" ADD CONSTRAINT "ItinerarySlot_tripId_fkey" FOREIGN KEY ("tripId") REFERENCES "Trip"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ItinerarySlot" ADD CONSTRAINT "ItinerarySlot_activityNodeId_fkey" FOREIGN KEY ("activityNodeId") REFERENCES "ActivityNode"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ActivityNodeVibeTag" ADD CONSTRAINT "ActivityNodeVibeTag_activityNodeId_fkey" FOREIGN KEY ("activityNodeId") REFERENCES "ActivityNode"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ActivityNodeVibeTag" ADD CONSTRAINT "ActivityNodeVibeTag_vibeTagId_fkey" FOREIGN KEY ("vibeTagId") REFERENCES "VibeTag"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ActivityAlias" ADD CONSTRAINT "ActivityAlias_activityNodeId_fkey" FOREIGN KEY ("activityNodeId") REFERENCES "ActivityNode"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "QualitySignal" ADD CONSTRAINT "QualitySignal_activityNodeId_fkey" FOREIGN KEY ("activityNodeId") REFERENCES "ActivityNode"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "SharedTripToken" ADD CONSTRAINT "SharedTripToken_tripId_fkey" FOREIGN KEY ("tripId") REFERENCES "Trip"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "InviteToken" ADD CONSTRAINT "InviteToken_tripId_fkey" FOREIGN KEY ("tripId") REFERENCES "Trip"("id") ON DELETE CASCADE ON UPDATE CASCADE;
