"""
SQLAlchemy async database module.

Re-exports engine, session, and model utilities for the FastAPI service.
Replaces prisma-client-py (archived April 2025).
"""

from services.api.db.engine import create_engine, standalone_session
from services.api.db.session import get_db
from services.api.db.models import (
    Base,
    AuditLog,
    Trip,
    TripMember,
    InviteToken,
    SharedTripToken,
    ItinerarySlot,
    BehavioralSignal,
    IntentionSignal,
    RawEvent,
)

__all__ = [
    "create_engine",
    "standalone_session",
    "get_db",
    "Base",
    "AuditLog",
    "Trip",
    "TripMember",
    "InviteToken",
    "SharedTripToken",
    "ItinerarySlot",
    "BehavioralSignal",
    "IntentionSignal",
    "RawEvent",
]
