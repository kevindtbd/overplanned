"""
SQLAlchemy DeclarativeBase models -- read-only mirrors of the Prisma schema subset
that the Python service touches.

Column names use camelCase to match the actual PostgreSQL column names.
Prisma uses camelCase in the DB; prisma-client-py auto-converted to snake_case
Python attributes, but SA does NOT do this conversion.

IMPORTANT: These models are NOT used for migrations. Prisma Migrate on the
JS side remains the migration tool. These are read-only mirrors.
"""

import uuid as _uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, Float, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# PostgreSQL enum types — declared here so SA knows to cast properly.
# Values sourced from live DB (SELECT unnest(enum_range(...))).
# create_type=False: Prisma Migrate owns the DDL, SA just reads.
NodeStatusEnum = Enum("pending", "approved", "flagged", "archived", name="NodeStatus", create_type=False)
ActivityCategoryEnum = Enum(
    "dining", "drinks", "culture", "outdoors", "active", "entertainment",
    "shopping", "experience", "nightlife", "group_activity", "wellness",
    name="ActivityCategory", create_type=False,
)
ModelStageEnum = Enum("staging", "ab_test", "production", "archived", name="ModelStage", create_type=False)
SignalTypeEnum = Enum(
    "slot_view", "slot_tap", "slot_confirm", "slot_skip", "slot_swap",
    "slot_complete", "slot_dwell", "discover_swipe_right", "discover_swipe_left",
    "discover_shortlist", "discover_remove", "vibe_select", "vibe_deselect",
    "vibe_implicit", "post_loved", "post_skipped", "post_missed", "post_disliked",
    "pivot_accepted", "pivot_rejected", "pivot_initiated", "dwell_time",
    "scroll_depth", "return_visit", "share_action", "considered_not_chosen",
    "soft_positive", "category_preference", "time_preference",
    "geographic_preference", "pace_signal", "vote_cast", "invite_accepted",
    "invite_declined", "trip_shared", "trip_imported", "packing_checked",
    "packing_unchecked", "mood_reported", "slot_moved", "trip_vibe_rating",
    "post_disambiguation", "negative_preference", "rejection_recovery_trigger",
    "pre_trip_slot_swap", "pre_trip_slot_removed", "pre_trip_slot_added",
    "pre_trip_reorder", "preset_selected", "preset_hovered",
    "preset_all_skipped", "pre_trip_slot_removed_reason",
    name="SignalType", create_type=False,
)
TripPhaseEnum = Enum("pre_trip", "active", "post_trip", name="TripPhase", create_type=False)
SlotTypeEnum = Enum("anchor", "flex", "meal", "rest", "transit", name="SlotType", create_type=False)
SlotStatusEnum = Enum("proposed", "voted", "confirmed", "active", "completed", "skipped", name="SlotStatus", create_type=False)
MemberStatusEnum = Enum("invited", "joined", "declined", name="MemberStatus", create_type=False)
TripRoleEnum = Enum("organizer", "member", name="TripRole", create_type=False)
TripStatusEnum = Enum("draft", "planning", "active", "completed", "archived", name="TripStatus", create_type=False)
TripModeEnum = Enum("solo", "group", name="TripMode", create_type=False)
SystemRoleEnum = Enum("user", "admin", name="SystemRole", create_type=False)
SubscriptionTierEnum = Enum("free", "beta", "pro", "lifetime", name="SubscriptionTier", create_type=False)
IntentClassEnum = Enum("explicit", "implicit", "contextual", name="IntentClass", create_type=False)


class Base(DeclarativeBase):
    pass


class AuditLog(Base):
    """Append-only audit log. NEVER update or delete rows from this table."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    actorId: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    targetType: Mapped[str] = mapped_column(String)
    targetId: Mapped[str] = mapped_column(String)
    before: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    after: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ipAddress: Mapped[str] = mapped_column(String)
    userAgent: Mapped[str] = mapped_column(String)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    userId: Mapped[str] = mapped_column(String)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    mode: Mapped[str] = mapped_column(TripModeEnum)
    status: Mapped[str] = mapped_column(TripStatusEnum)
    startDate: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    endDate: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    groupId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    memberCount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completedAt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    activatedAt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # These columns are accessed by production code (reengagement, shared_trips, invites)
    # They exist on the Trip table even though TripLeg also has them (multi-city migration)
    destination: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    currency: Mapped[str] = mapped_column(String, default="USD")
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updatedAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TripMember(Base):
    __tablename__ = "trip_members"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    tripId: Mapped[str] = mapped_column(String)
    userId: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(TripRoleEnum)
    status: Mapped[str] = mapped_column(MemberStatusEnum)
    joinedAt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InviteToken(Base):
    __tablename__ = "invite_tokens"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    tripId: Mapped[str] = mapped_column(String)
    token: Mapped[str] = mapped_column(String, unique=True)
    createdBy: Mapped[str] = mapped_column(String)
    maxUses: Mapped[int] = mapped_column(Integer, default=1)
    usedCount: Mapped[int] = mapped_column(Integer, default=0)
    role: Mapped[str] = mapped_column(TripRoleEnum)
    expiresAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revokedAt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SharedTripToken(Base):
    __tablename__ = "shared_trip_tokens"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    tripId: Mapped[str] = mapped_column(String)
    token: Mapped[str] = mapped_column(String, unique=True)
    createdBy: Mapped[str] = mapped_column(String)
    expiresAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revokedAt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    viewCount: Mapped[int] = mapped_column(Integer, default=0)
    importCount: Mapped[int] = mapped_column(Integer, default=0)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ItinerarySlot(Base):
    __tablename__ = "itinerary_slots"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    tripId: Mapped[str] = mapped_column(String)
    tripLegId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    activityNodeId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    dayNumber: Mapped[int] = mapped_column(Integer)
    sortOrder: Mapped[int] = mapped_column(Integer)
    slotType: Mapped[str] = mapped_column(SlotTypeEnum)
    status: Mapped[str] = mapped_column(SlotStatusEnum)
    startTime: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    endTime: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    durationMinutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    isLocked: Mapped[bool] = mapped_column(Boolean, default=False)
    pivotEventId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    wasSwapped: Mapped[bool] = mapped_column(Boolean, default=False)
    completionSignal: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updatedAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BehavioralSignal(Base):
    __tablename__ = "behavioral_signals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    userId: Mapped[str] = mapped_column(String)
    tripId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    slotId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    activityNodeId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    signalType: Mapped[str] = mapped_column(SignalTypeEnum)
    signalValue: Mapped[float] = mapped_column(Float)
    tripPhase: Mapped[str] = mapped_column(TripPhaseEnum)
    rawAction: Mapped[str] = mapped_column(String)
    weatherContext: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    modelVersion: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    promptVersion: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    subflow: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    signal_weight: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String, default="user_behavioral")
    # NOTE: "metadata" is a reserved attr name in DeclarativeBase — use signal_metadata
    # as the Python attr name with an explicit column("metadata") mapping.
    signal_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    # Pre-launch behavioral scaffolding
    candidateSetId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    candidateIds: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IntentionSignal(Base):
    __tablename__ = "intention_signals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    behavioralSignalId: Mapped[str] = mapped_column(String)
    rawEventId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    userId: Mapped[str] = mapped_column(String)
    intentionType: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String)
    userProvided: Mapped[bool] = mapped_column(Boolean, default=False)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RankingEvent(Base):
    __tablename__ = "ranking_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    userId: Mapped[str] = mapped_column(String)
    tripId: Mapped[str] = mapped_column(String)
    sessionId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    dayNumber: Mapped[int] = mapped_column(Integer)
    modelName: Mapped[str] = mapped_column(String)
    modelVersion: Mapped[str] = mapped_column(String)
    candidateIds: Mapped[list[str]] = mapped_column(ARRAY(String))
    rankedIds: Mapped[list[str]] = mapped_column(ARRAY(String))
    selectedIds: Mapped[list[str]] = mapped_column(ARRAY(String))
    surface: Mapped[str] = mapped_column(String)
    shadowModelName: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    shadowModelVersion: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    shadowRankedIds: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    latencyMs: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Pre-launch behavioral scaffolding
    acceptedId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rejectedIds: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    viewedIds: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    viewDurations: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    weatherContext: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    personaSnapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    candidateSetId: Mapped[Optional[str]] = mapped_column(String, nullable=True, unique=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    email: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    image: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    avatarUrl: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    googleId: Mapped[Optional[str]] = mapped_column(String, nullable=True, unique=True)
    emailVerified: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    subscriptionTier: Mapped[str] = mapped_column(SubscriptionTierEnum, default="beta")
    systemRole: Mapped[str] = mapped_column(SystemRoleEnum, default="user")
    featureFlags: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    accessCohort: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    stripeCustomerId: Mapped[Optional[str]] = mapped_column(String, nullable=True, unique=True)
    stripeSubId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    stripePriceId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    onboardingComplete: Mapped[bool] = mapped_column(Boolean, default=False)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updatedAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lastActiveAt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ModelRegistry(Base):
    __tablename__ = "model_registry"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    modelName: Mapped[str] = mapped_column(String)
    modelVersion: Mapped[str] = mapped_column(String)
    stage: Mapped[str] = mapped_column(ModelStageEnum)
    modelType: Mapped[str] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    artifactPath: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    artifactHash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    configSnapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    evaluatedAt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    trainingDataRange: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    parentVersionId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    promotedAt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    promotedBy: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updatedAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ActivityNode(Base):
    __tablename__ = "activity_nodes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    name: Mapped[str] = mapped_column(String)
    slug: Mapped[str] = mapped_column(String, unique=True)
    canonicalName: Mapped[str] = mapped_column(String)
    city: Mapped[str] = mapped_column(String)
    country: Mapped[str] = mapped_column(String)
    neighborhood: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    category: Mapped[str] = mapped_column(ActivityCategoryEnum)
    subcategory: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    priceLevel: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hours: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phoneNumber: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    websiteUrl: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    foursquareId: Mapped[Optional[str]] = mapped_column(String, nullable=True, unique=True)
    googlePlaceId: Mapped[Optional[str]] = mapped_column(String, nullable=True, unique=True)
    primaryImageUrl: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    imageSource: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    imageValidated: Mapped[bool] = mapped_column(Boolean, default=False)
    sourceCount: Mapped[int] = mapped_column(Integer, default=0)
    convergenceScore: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    authorityScore: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    descriptionShort: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    descriptionLong: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    contentHash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    lastScrapedAt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    lastValidatedAt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(NodeStatusEnum, default="pending")
    flagReason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    resolvedToId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    isCanonical: Mapped[bool] = mapped_column(Boolean, default=True)
    tourist_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tourist_local_divergence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    impression_count: Mapped[int] = mapped_column(Integer, default=0)
    acceptance_count: Mapped[int] = mapped_column(Integer, default=0)
    behavioral_quality_score: Mapped[float] = mapped_column(Float, default=0.5)
    llm_served_count: Mapped[int] = mapped_column(Integer, default=0)
    ml_served_count: Mapped[int] = mapped_column(Integer, default=0)
    behavioralUpdatedAt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cantMiss: Mapped[bool] = mapped_column(Boolean, default=False)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updatedAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ActivityAlias(Base):
    __tablename__ = "activity_aliases"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    activityNodeId: Mapped[str] = mapped_column(String)
    alias: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RawEvent(Base):
    __tablename__ = "raw_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    userId: Mapped[str] = mapped_column(String)
    sessionId: Mapped[str] = mapped_column(String)
    tripId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    activityNodeId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    clientEventId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    eventType: Mapped[str] = mapped_column(String)
    intentClass: Mapped[str] = mapped_column(IntentClassEnum)
    surface: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    platform: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Pre-launch behavioral scaffolding
    trainingExtracted: Mapped[bool] = mapped_column(Boolean, default=False)
    extractedAt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))
