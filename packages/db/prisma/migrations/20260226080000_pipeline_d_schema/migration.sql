-- CreateEnum
CREATE TYPE "ResearchJobStatus" AS ENUM ('QUEUED', 'ASSEMBLING_BUNDLE', 'RUNNING_PASS_A', 'RUNNING_PASS_B', 'VALIDATING', 'RESOLVING', 'CROSS_REFERENCING', 'WRITING_BACK', 'COMPLETE', 'VALIDATION_FAILED', 'ERROR');

-- CreateEnum
CREATE TYPE "ResearchTrigger" AS ENUM ('admin_seed', 'tier2_graduation', 'on_demand_fallback');

-- CreateEnum
CREATE TYPE "KnowledgeSource" AS ENUM ('bundle_primary', 'training_prior', 'both', 'neither');

-- AlterTable: ActivityNode - Pipeline D columns
ALTER TABLE "activity_nodes" ADD COLUMN "researchSynthesisId" TEXT,
ADD COLUMN "pipelineDConfidence" DOUBLE PRECISION,
ADD COLUMN "pipelineCConfidence" DOUBLE PRECISION,
ADD COLUMN "crossRefAgreementScore" DOUBLE PRECISION,
ADD COLUMN "sourceAmplificationFlag" BOOLEAN NOT NULL DEFAULT false,
ADD COLUMN "signalConflictFlag" BOOLEAN NOT NULL DEFAULT false,
ADD COLUMN "pipelineDTemporalNotes" TEXT;

-- AlterTable: RankingEvent - Pipeline D cross-reference training features
ALTER TABLE "ranking_events" ADD COLUMN "hasDSignal" BOOLEAN,
ADD COLUMN "hasCSignal" BOOLEAN,
ADD COLUMN "dCAgreement" DOUBLE PRECISION,
ADD COLUMN "signalConflictAtServe" BOOLEAN,
ADD COLUMN "dKnowledgeSource" TEXT,
ADD COLUMN "rankPipelineDConfidence" DOUBLE PRECISION;

-- CreateTable
CREATE TABLE "research_jobs" (
    "id" TEXT NOT NULL,
    "cityId" TEXT NOT NULL,
    "status" "ResearchJobStatus" NOT NULL DEFAULT 'QUEUED',
    "triggeredBy" "ResearchTrigger" NOT NULL,
    "modelVersion" TEXT NOT NULL,
    "passATokens" INTEGER NOT NULL DEFAULT 0,
    "passBTokens" INTEGER NOT NULL DEFAULT 0,
    "totalCostUsd" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "venuesResearched" INTEGER NOT NULL DEFAULT 0,
    "venuesResolved" INTEGER NOT NULL DEFAULT 0,
    "venuesUnresolved" INTEGER NOT NULL DEFAULT 0,
    "validationWarnings" JSONB,
    "errorMessage" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "completedAt" TIMESTAMP(3),

    CONSTRAINT "research_jobs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "city_research_syntheses" (
    "id" TEXT NOT NULL,
    "researchJobId" TEXT NOT NULL,
    "cityId" TEXT NOT NULL,
    "neighborhoodCharacter" JSONB NOT NULL,
    "temporalPatterns" JSONB NOT NULL,
    "peakAndDeclineFlags" JSONB NOT NULL,
    "sourceAmplificationFlags" JSONB NOT NULL,
    "divergenceSignals" JSONB NOT NULL,
    "synthesisConfidence" DOUBLE PRECISION NOT NULL,
    "modelVersion" TEXT NOT NULL,
    "generatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "city_research_syntheses_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "venue_research_signals" (
    "id" TEXT NOT NULL,
    "researchJobId" TEXT NOT NULL,
    "cityResearchSynthesisId" TEXT,
    "activityNodeId" TEXT,
    "venueNameRaw" TEXT NOT NULL,
    "resolutionMatchType" TEXT,
    "resolutionConfidence" DOUBLE PRECISION,
    "vibeTags" TEXT[],
    "touristScore" DOUBLE PRECISION,
    "temporalNotes" TEXT,
    "sourceAmplification" BOOLEAN NOT NULL DEFAULT false,
    "localVsTouristSignalConflict" BOOLEAN NOT NULL DEFAULT false,
    "researchConfidence" DOUBLE PRECISION,
    "knowledgeSource" "KnowledgeSource",
    "notes" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "venue_research_signals_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "unresolved_research_signals" (
    "id" TEXT NOT NULL,
    "venueResearchSignalId" TEXT NOT NULL,
    "cityId" TEXT NOT NULL,
    "venueNameRaw" TEXT NOT NULL,
    "resolutionAttempts" INTEGER NOT NULL DEFAULT 0,
    "lastAttemptAt" TIMESTAMP(3),
    "resolvedAt" TIMESTAMP(3),
    "resolvedToActivityNodeId" TEXT,

    CONSTRAINT "unresolved_research_signals_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "cross_reference_results" (
    "id" TEXT NOT NULL,
    "activityNodeId" TEXT NOT NULL,
    "cityId" TEXT NOT NULL,
    "researchJobId" TEXT NOT NULL,
    "hasPipelineDSignal" BOOLEAN NOT NULL DEFAULT false,
    "hasPipelineCSignal" BOOLEAN NOT NULL DEFAULT false,
    "dOnly" BOOLEAN NOT NULL DEFAULT false,
    "cOnly" BOOLEAN NOT NULL DEFAULT false,
    "bothAgree" BOOLEAN NOT NULL DEFAULT false,
    "bothConflict" BOOLEAN NOT NULL DEFAULT false,
    "tagAgreementScore" DOUBLE PRECISION,
    "touristScoreDelta" DOUBLE PRECISION,
    "signalConflict" BOOLEAN NOT NULL DEFAULT false,
    "mergedVibeTags" TEXT[],
    "mergedTouristScore" DOUBLE PRECISION,
    "mergedConfidence" DOUBLE PRECISION,
    "resolvedBy" TEXT,
    "resolvedAt" TIMESTAMP(3),
    "resolutionAction" TEXT,
    "previousValues" JSONB,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "cross_reference_results_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "research_jobs_cityId_createdAt_idx" ON "research_jobs"("cityId", "createdAt");

-- CreateIndex
CREATE INDEX "research_jobs_status_idx" ON "research_jobs"("status");

-- CreateIndex
CREATE UNIQUE INDEX "city_research_syntheses_researchJobId_key" ON "city_research_syntheses"("researchJobId");

-- CreateIndex
CREATE INDEX "city_research_syntheses_cityId_idx" ON "city_research_syntheses"("cityId");

-- CreateIndex
CREATE INDEX "venue_research_signals_researchJobId_idx" ON "venue_research_signals"("researchJobId");

-- CreateIndex
CREATE INDEX "venue_research_signals_activityNodeId_idx" ON "venue_research_signals"("activityNodeId");

-- CreateIndex
CREATE UNIQUE INDEX "unresolved_research_signals_venueResearchSignalId_key" ON "unresolved_research_signals"("venueResearchSignalId");

-- CreateIndex
CREATE INDEX "unresolved_research_signals_cityId_resolvedAt_idx" ON "unresolved_research_signals"("cityId", "resolvedAt");

-- CreateIndex
CREATE UNIQUE INDEX "cross_reference_results_activityNodeId_researchJobId_key" ON "cross_reference_results"("activityNodeId", "researchJobId");

-- CreateIndex
CREATE INDEX "cross_reference_results_cityId_idx" ON "cross_reference_results"("cityId");

-- CreateIndex
CREATE INDEX "cross_reference_results_signalConflict_idx" ON "cross_reference_results"("signalConflict");

-- AddForeignKey
ALTER TABLE "city_research_syntheses" ADD CONSTRAINT "city_research_syntheses_researchJobId_fkey" FOREIGN KEY ("researchJobId") REFERENCES "research_jobs"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "venue_research_signals" ADD CONSTRAINT "venue_research_signals_researchJobId_fkey" FOREIGN KEY ("researchJobId") REFERENCES "research_jobs"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "venue_research_signals" ADD CONSTRAINT "venue_research_signals_cityResearchSynthesisId_fkey" FOREIGN KEY ("cityResearchSynthesisId") REFERENCES "city_research_syntheses"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "unresolved_research_signals" ADD CONSTRAINT "unresolved_research_signals_venueResearchSignalId_fkey" FOREIGN KEY ("venueResearchSignalId") REFERENCES "venue_research_signals"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "cross_reference_results" ADD CONSTRAINT "cross_reference_results_researchJobId_fkey" FOREIGN KEY ("researchJobId") REFERENCES "research_jobs"("id") ON DELETE CASCADE ON UPDATE CASCADE;
