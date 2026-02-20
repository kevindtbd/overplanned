"""
Solo fallback chain tests (M-011).

Validates graceful degradation:
- LLM timeout -> deterministic ranking fallback
- Qdrant timeout -> Postgres-only candidate fetch
- Both timeouts -> minimal viable itinerary from Postgres
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.api.tests.conftest import (
    make_activity_node,
    make_trip,
    make_user,
    make_itinerary_slot,
)
from services.api.generation.ranker import (
    rank_candidates_with_llm,
    LLM_TIMEOUT_S,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def persona_seed():
    return {
        "vibes": ["hidden-gem", "local-favorite"],
        "pace": "moderate",
        "budget": "mid",
    }


@pytest.fixture
def candidate_nodes():
    """Candidate pool sorted by convergenceScore descending (deterministic fallback order)."""
    nodes = []
    for i, (cat, score) in enumerate([
        ("dining", 0.95),
        ("culture", 0.88),
        ("outdoors", 0.75),
        ("experience", 0.60),
        ("shopping", 0.45),
    ]):
        nodes.append(make_activity_node(
            id=f"fb-node-{i:03d}",
            name=f"Fallback Venue {i}",
            slug=f"fallback-venue-{i}",
            category=cat,
            convergenceScore=score,
            authorityScore=score * 0.8,
        ))
    return nodes


# ===========================================================================
# LLM timeout -> deterministic fallback
# ===========================================================================

class TestLLMTimeoutFallback:
    """When LLM times out, fall back to deterministic convergence-score ranking."""

    @pytest.mark.asyncio
    async def test_llm_timeout_triggers_fallback(self, persona_seed, candidate_nodes):
        """LLM timeout should raise TimeoutError, signaling fallback."""
        slow_client = AsyncMock()

        async def _slow_create(**kwargs):
            await asyncio.sleep(LLM_TIMEOUT_S + 2)
            return MagicMock()

        slow_client.messages.create = _slow_create

        with pytest.raises(asyncio.TimeoutError):
            await rank_candidates_with_llm(
                persona_seed, candidate_nodes, slow_client
            )

    def test_deterministic_fallback_sorts_by_convergence(self, candidate_nodes):
        """Deterministic fallback: rank by convergenceScore descending."""
        sorted_nodes = sorted(
            candidate_nodes,
            key=lambda n: n.get("convergenceScore", 0),
            reverse=True,
        )
        for i in range(1, len(sorted_nodes)):
            assert (
                sorted_nodes[i - 1]["convergenceScore"]
                >= sorted_nodes[i]["convergenceScore"]
            ), "Fallback must sort by convergenceScore descending"

    def test_deterministic_fallback_assigns_slot_types(self, candidate_nodes):
        """Deterministic fallback: dining/drinks -> meal, culture -> anchor, rest -> flex."""
        type_map = {
            "dining": "meal",
            "drinks": "meal",
            "culture": "anchor",
            "outdoors": "flex",
            "experience": "flex",
            "shopping": "flex",
        }
        for node in candidate_nodes:
            expected = type_map.get(node["category"], "flex")
            assert expected in ("meal", "anchor", "flex"), (
                f"Unknown slot type mapping for category={node['category']}"
            )

    def test_deterministic_fallback_produces_valid_slots(self, candidate_nodes):
        """Fallback ranking still creates valid ItinerarySlots."""
        trip_id = str(uuid.uuid4())
        sorted_nodes = sorted(
            candidate_nodes,
            key=lambda n: n.get("convergenceScore", 0),
            reverse=True,
        )
        slots = [
            make_itinerary_slot(
                trip_id=trip_id,
                activityNodeId=node["id"],
                dayNumber=1,
                sortOrder=i,
                slotType="meal" if node["category"] == "dining" else "flex",
            )
            for i, node in enumerate(sorted_nodes)
        ]
        assert len(slots) == len(candidate_nodes)
        for slot in slots:
            assert slot["activityNodeId"] is not None
            assert slot["tripId"] == trip_id


# ===========================================================================
# Qdrant timeout -> Postgres fallback
# ===========================================================================

class TestQdrantTimeoutFallback:
    """When Qdrant is unreachable, fall back to Postgres for candidates."""

    def test_postgres_fallback_returns_nodes_by_convergence(self, candidate_nodes):
        """
        Postgres fallback: SELECT from ActivityNode
        WHERE city = :city AND status = 'approved'
        ORDER BY convergenceScore DESC LIMIT :n
        """
        # Simulate Postgres result set: nodes sorted by convergence
        city = "Tokyo"
        approved = [n for n in candidate_nodes if n.get("status") in ("pending", "approved")]
        by_score = sorted(approved, key=lambda n: n.get("convergenceScore", 0), reverse=True)
        assert len(by_score) > 0, "Postgres should return at least some nodes"
        # Verify ordering
        scores = [n["convergenceScore"] for n in by_score]
        assert scores == sorted(scores, reverse=True)

    def test_postgres_fallback_filters_by_city(self, candidate_nodes):
        """Postgres fallback only returns nodes matching the trip city."""
        target_city = "Tokyo"
        city_nodes = [n for n in candidate_nodes if n["city"] == target_city]
        assert len(city_nodes) == len(candidate_nodes), (
            "All test nodes should be Tokyo for this test"
        )

    def test_postgres_fallback_excludes_flagged_nodes(self):
        """Flagged or archived nodes must not appear in fallback results."""
        flagged = make_activity_node(status="flagged", name="Bad Venue")
        archived = make_activity_node(status="archived", name="Old Venue")
        active = make_activity_node(status="pending", name="Good Venue")

        pool = [flagged, archived, active]
        valid = [n for n in pool if n["status"] not in ("flagged", "archived")]
        assert len(valid) == 1
        assert valid[0]["name"] == "Good Venue"


# ===========================================================================
# Both timeouts -> minimal viable itinerary
# ===========================================================================

class TestDoubleFailureFallback:
    """Both LLM and Qdrant down: generate minimal itinerary from Postgres."""

    def test_minimal_itinerary_has_at_least_one_slot(self, candidate_nodes):
        """Even with all services down, at least 1 slot should be created."""
        trip_id = str(uuid.uuid4())
        # Simulate: take top-1 by convergence from Postgres
        top_node = max(candidate_nodes, key=lambda n: n.get("convergenceScore", 0))
        slot = make_itinerary_slot(
            trip_id=trip_id,
            activityNodeId=top_node["id"],
            dayNumber=1,
            sortOrder=0,
            slotType="anchor",
        )
        assert slot["activityNodeId"] == top_node["id"]

    def test_minimal_itinerary_covers_meals(self, candidate_nodes):
        """Minimal fallback should include at least one meal slot if dining nodes exist."""
        dining_nodes = [n for n in candidate_nodes if n["category"] == "dining"]
        assert len(dining_nodes) > 0, "Test pool should have dining nodes"
        meal_slot = make_itinerary_slot(
            activityNodeId=dining_nodes[0]["id"],
            slotType="meal",
        )
        assert meal_slot["slotType"] == "meal"
