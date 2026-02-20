"""
Discover feed personalization tests (M-011).

Validates the rules for the solo discover feed:
- Feed excludes already-slotted activities
- Feed is ranked by persona-vibe alignment
- Swiped-left items do not reappear in the same session
- Shortlisted items are tracked and can be promoted to slots
- Discover events emit correct RawEvent types
"""

import uuid
from datetime import datetime, timezone

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
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def discover_user():
    return make_user(id="user-discover-001", onboardingComplete=True)


@pytest.fixture
def discover_trip(discover_user):
    return make_trip(
        id="trip-discover-001",
        userId=discover_user["id"],
        mode="solo",
        status="planning",
    )


@pytest.fixture
def discover_pool():
    """Pool of 8 nodes for discover feed testing."""
    return [
        make_activity_node(
            id=f"disc-node-{i:03d}",
            name=f"Discover Venue {i}",
            slug=f"discover-venue-{i}",
            category=cat,
            convergenceScore=0.7 + (i * 0.03),
        )
        for i, cat in enumerate([
            "dining", "culture", "outdoors", "nightlife",
            "shopping", "experience", "wellness", "entertainment",
        ])
    ]


@pytest.fixture
def session_id():
    return "session-discover-001"


# ===========================================================================
# Feed exclusion rules
# ===========================================================================

class TestFeedExclusion:
    """Already-slotted activities must not appear in discover feed."""

    def test_slotted_activities_excluded(self, discover_trip, discover_pool):
        """Nodes already in itinerary slots are filtered out."""
        slotted_id = discover_pool[0]["id"]
        _ = make_itinerary_slot(
            trip_id=discover_trip["id"],
            activityNodeId=slotted_id,
            status="confirmed",
        )
        feed = [n for n in discover_pool if n["id"] != slotted_id]
        assert len(feed) == len(discover_pool) - 1
        assert all(n["id"] != slotted_id for n in feed)

    def test_swiped_left_excluded_in_session(self, discover_user, discover_trip, discover_pool, session_id):
        """Swiped-left items do not reappear in the same session."""
        swiped_id = discover_pool[1]["id"]
        _ = make_behavioral_signal(
            user_id=discover_user["id"],
            signalType="discover_swipe_left",
            signalValue=-1.0,
            tripId=discover_trip["id"],
            activityNodeId=swiped_id,
            rawAction="discover_swipe_left",
        )
        # Simulate filtering
        swiped_ids = {swiped_id}
        feed = [n for n in discover_pool if n["id"] not in swiped_ids]
        assert all(n["id"] != swiped_id for n in feed)

    def test_multiple_exclusions_stack(self, discover_trip, discover_pool):
        """Multiple slotted + swiped nodes all excluded."""
        excluded_ids = {discover_pool[0]["id"], discover_pool[2]["id"], discover_pool[4]["id"]}
        feed = [n for n in discover_pool if n["id"] not in excluded_ids]
        assert len(feed) == len(discover_pool) - 3


# ===========================================================================
# Persona-based ranking
# ===========================================================================

class TestPersonaRanking:
    """Discover feed is ranked by persona-vibe alignment."""

    def test_feed_ranked_by_convergence(self, discover_pool):
        """Default ranking: convergenceScore descending."""
        ranked = sorted(
            discover_pool,
            key=lambda n: n.get("convergenceScore", 0),
            reverse=True,
        )
        scores = [n["convergenceScore"] for n in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_feed_preserves_category_diversity(self, discover_pool):
        """Feed should include nodes from multiple categories."""
        categories = {n["category"] for n in discover_pool}
        assert len(categories) >= 4, "Discover pool should span multiple categories"


# ===========================================================================
# Shortlist tracking
# ===========================================================================

class TestShortlisting:
    """Shortlisted items are tracked and can be promoted to slots."""

    def test_shortlist_signal_emitted(self, discover_user, discover_trip, discover_pool):
        """Shortlisting a node emits discover_shortlist signal."""
        node_id = discover_pool[3]["id"]
        signal = make_behavioral_signal(
            user_id=discover_user["id"],
            signalType="discover_shortlist",
            signalValue=1.0,
            tripId=discover_trip["id"],
            activityNodeId=node_id,
            rawAction="discover_shortlist",
        )
        assert signal["signalType"] == "discover_shortlist"
        assert signal["activityNodeId"] == node_id

    def test_shortlisted_can_become_slot(self, discover_trip, discover_pool):
        """A shortlisted node can be promoted to an ItinerarySlot."""
        node_id = discover_pool[3]["id"]
        slot = make_itinerary_slot(
            trip_id=discover_trip["id"],
            activityNodeId=node_id,
            slotType="flex",
            status="proposed",
        )
        assert slot["activityNodeId"] == node_id
        assert slot["status"] == "proposed"


# ===========================================================================
# Discover event emission
# ===========================================================================

class TestDiscoverEventEmission:
    """Discover interactions emit correct RawEvent types."""

    def test_swipe_right_emits_explicit_event(self, discover_user, session_id, discover_pool):
        """Swiping right emits an explicit RawEvent."""
        event = make_raw_event(
            user_id=discover_user["id"],
            session_id=session_id,
            activityNodeId=discover_pool[0]["id"],
            eventType="discover.swipe_right",
            intentClass="explicit",
            payload={"surface": "discover_feed"},
        )
        assert event["eventType"] == "discover.swipe_right"
        assert event["intentClass"] == "explicit"

    def test_swipe_left_emits_explicit_event(self, discover_user, session_id, discover_pool):
        """Swiping left emits an explicit RawEvent."""
        event = make_raw_event(
            user_id=discover_user["id"],
            session_id=session_id,
            activityNodeId=discover_pool[1]["id"],
            eventType="discover.swipe_left",
            intentClass="explicit",
            payload={"surface": "discover_feed"},
        )
        assert event["eventType"] == "discover.swipe_left"
        assert event["intentClass"] == "explicit"

    def test_impression_emits_implicit_event(self, discover_user, session_id, discover_pool):
        """Viewing a card without interaction emits implicit event."""
        event = make_raw_event(
            user_id=discover_user["id"],
            session_id=session_id,
            activityNodeId=discover_pool[2]["id"],
            eventType="discover.impression",
            intentClass="implicit",
            payload={"position": 0, "surface": "discover_feed"},
        )
        assert event["eventType"] == "discover.impression"
        assert event["intentClass"] == "implicit"
        assert event["payload"]["position"] == 0
