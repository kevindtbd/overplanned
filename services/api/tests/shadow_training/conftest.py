"""
Shared fixtures for shadow training data quality tests.

Provides:
- Factory helpers for training-relevant signal types (positive, negative, implicit)
- Candidate set builders for ranked pool logging
- Session sequence builders for temporal ordering tests
- Re-exports core conftest fixtures (mock_db, mock_redis, etc.)
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

import pytest

from services.api.tests.conftest import (
    make_user,
    make_trip,
    make_activity_node,
    make_behavioral_signal,
    make_raw_event,
    make_itinerary_slot,
)


# ---------------------------------------------------------------------------
# ID helpers
# ---------------------------------------------------------------------------

def _gen_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Stable test identities
# ---------------------------------------------------------------------------

@pytest.fixture
def solo_user():
    """A solo traveler user for training signal tests."""
    return make_user(
        id="user-solo-train-001",
        name="Training User",
        onboardingComplete=True,
    )


@pytest.fixture
def solo_trip(solo_user):
    """A solo trip associated with the training user."""
    return make_trip(
        id="trip-solo-train-001",
        userId=solo_user["id"],
        mode="solo",
        status="active",
        destination="Tokyo, Japan",
        city="Tokyo",
        country="Japan",
    )


@pytest.fixture
def activity_nodes():
    """A pool of 6 activity nodes for candidate set tests."""
    categories = ["dining", "culture", "outdoors", "nightlife", "shopping", "experience"]
    nodes = []
    for i, cat in enumerate(categories):
        nodes.append(make_activity_node(
            id=f"node-train-{i:03d}",
            name=f"Test Venue {i}",
            slug=f"test-venue-{i}",
            category=cat,
            convergenceScore=0.5 + (i * 0.08),
            authorityScore=0.4 + (i * 0.05),
        ))
    return nodes


@pytest.fixture
def session_id():
    """A stable session ID for sequence tests."""
    return "session-train-001"


# ---------------------------------------------------------------------------
# Signal builders — positive pairs
# ---------------------------------------------------------------------------

def make_positive_signal(
    user_id: str,
    trip_id: str,
    activity_node_id: str,
    signal_type: str = "slot_confirm",
    **overrides: Any,
) -> dict:
    """Build a positive training signal (slot_confirm, slot_complete, post_loved)."""
    valid_positive = {"slot_confirm", "slot_complete", "post_loved"}
    assert signal_type in valid_positive, f"Not a positive signal: {signal_type}"
    return make_behavioral_signal(
        user_id=user_id,
        tripId=trip_id,
        activityNodeId=activity_node_id,
        signalType=signal_type,
        signalValue=1.0,
        rawAction=signal_type,
        tripPhase="active" if signal_type != "post_loved" else "post_trip",
        **overrides,
    )


# ---------------------------------------------------------------------------
# Signal builders — explicit negative
# ---------------------------------------------------------------------------

def make_explicit_negative_signal(
    user_id: str,
    trip_id: str,
    activity_node_id: str,
    signal_type: str = "slot_skip",
    **overrides: Any,
) -> dict:
    """Build an explicit negative training signal (slot_skip, discover_swipe_left, post_disliked)."""
    valid_negative = {"slot_skip", "discover_swipe_left", "post_disliked"}
    assert signal_type in valid_negative, f"Not an explicit negative: {signal_type}"
    return make_behavioral_signal(
        user_id=user_id,
        tripId=trip_id,
        activityNodeId=activity_node_id,
        signalType=signal_type,
        signalValue=-1.0,
        rawAction=signal_type,
        tripPhase="active" if signal_type != "post_disliked" else "post_trip",
        **overrides,
    )


# ---------------------------------------------------------------------------
# Signal builders — implicit negative (impression without tap)
# ---------------------------------------------------------------------------

def make_impression_event(
    user_id: str,
    session_id: str,
    activity_node_id: str,
    position: int,
    **overrides: Any,
) -> dict:
    """Build a RawEvent impression (shown but not tapped = implicit negative)."""
    return make_raw_event(
        user_id=user_id,
        session_id=session_id,
        activityNodeId=activity_node_id,
        eventType="impression",
        intentClass="implicit",
        payload={"position": position, "surface": "discover_feed"},
        **overrides,
    )


def make_tap_event(
    user_id: str,
    session_id: str,
    activity_node_id: str,
    **overrides: Any,
) -> dict:
    """Build a RawEvent tap (user engaged with the impression)."""
    return make_raw_event(
        user_id=user_id,
        session_id=session_id,
        activityNodeId=activity_node_id,
        eventType="tap",
        intentClass="explicit",
        payload={"surface": "discover_feed"},
        **overrides,
    )


# ---------------------------------------------------------------------------
# Candidate set builder — logs full ranked pool
# ---------------------------------------------------------------------------

def make_candidate_set_event(
    user_id: str,
    session_id: str,
    trip_id: str,
    candidates: list[dict],
    **overrides: Any,
) -> dict:
    """Build a RawEvent that logs the full ranked candidate pool for a generation."""
    compact = [
        {
            "id": c["id"],
            "rank": i + 1,
            "category": c.get("category", ""),
            "convergenceScore": c.get("convergenceScore"),
        }
        for i, c in enumerate(candidates)
    ]
    return make_raw_event(
        user_id=user_id,
        session_id=session_id,
        tripId=trip_id,
        eventType="generation.candidate_set",
        intentClass="contextual",
        payload={"candidates": compact, "poolSize": len(candidates)},
        **overrides,
    )


# ---------------------------------------------------------------------------
# Session sequence builder
# ---------------------------------------------------------------------------

def make_ordered_session_events(
    user_id: str,
    session_id: str,
    activity_node_ids: list[str],
    base_time: datetime | None = None,
) -> list[dict]:
    """Build a time-ordered sequence of impression events within a session."""
    base = base_time or datetime.now(timezone.utc)
    events = []
    for i, node_id in enumerate(activity_node_ids):
        events.append(make_impression_event(
            user_id=user_id,
            session_id=session_id,
            activity_node_id=node_id,
            position=i,
            createdAt=base + timedelta(seconds=i * 2),
        ))
    return events
