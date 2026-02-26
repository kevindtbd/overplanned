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

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AuditLog(Base):
    """Append-only audit log. NEVER update or delete rows from this table."""

    __tablename__ = "AuditLog"

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
    __tablename__ = "Trip"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    userId: Mapped[str] = mapped_column(String)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    mode: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
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
    __tablename__ = "TripMember"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    tripId: Mapped[str] = mapped_column(String)
    userId: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    joinedAt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InviteToken(Base):
    __tablename__ = "InviteToken"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    tripId: Mapped[str] = mapped_column(String)
    token: Mapped[str] = mapped_column(String, unique=True)
    createdBy: Mapped[str] = mapped_column(String)
    maxUses: Mapped[int] = mapped_column(Integer, default=1)
    usedCount: Mapped[int] = mapped_column(Integer, default=0)
    role: Mapped[str] = mapped_column(String)
    expiresAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revokedAt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SharedTripToken(Base):
    __tablename__ = "SharedTripToken"

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
    __tablename__ = "ItinerarySlot"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    tripId: Mapped[str] = mapped_column(String)
    tripLegId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    activityNodeId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    dayNumber: Mapped[int] = mapped_column(Integer)
    sortOrder: Mapped[int] = mapped_column(Integer)
    slotType: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
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
    __tablename__ = "BehavioralSignal"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    userId: Mapped[str] = mapped_column(String)
    tripId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    slotId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    activityNodeId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    signalType: Mapped[str] = mapped_column(String)
    signalValue: Mapped[float] = mapped_column(Float)
    tripPhase: Mapped[str] = mapped_column(String)
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
    __tablename__ = "IntentionSignal"

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
    __tablename__ = "RankingEvent"

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


class RawEvent(Base):
    __tablename__ = "RawEvent"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    userId: Mapped[str] = mapped_column(String)
    sessionId: Mapped[str] = mapped_column(String)
    tripId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    activityNodeId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    clientEventId: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    eventType: Mapped[str] = mapped_column(String)
    intentClass: Mapped[str] = mapped_column(String)
    surface: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    platform: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Pre-launch behavioral scaffolding
    trainingExtracted: Mapped[bool] = mapped_column(Boolean, default=False)
    extractedAt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))
