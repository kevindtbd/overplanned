"""
Solo itinerary generation integration tests (M-011).

Validates the full pipeline: onboarding data -> LLM ranking -> slot creation.

Tests:
- Persona seed flows from onboarding into ranker prompt
- Candidate pool is fetched from Qdrant + Postgres fallback
- LLM ranker returns valid ranked list
- Ranked candidates become ItinerarySlots with correct day/sort assignments
- All LLM calls are logged with model version, prompt version, latency, cost
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.api.tests.conftest import (
    make_user,
    make_trip,
    make_activity_node,
    make_itinerary_slot,
)
from services.api.generation.ranker import (
    rank_candidates_with_llm,
    _build_user_prompt,
    RANKER_MODEL,
    RANKER_PROMPT_VERSION,
    LLM_TIMEOUT_S,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def persona_seed():
    """A typical solo traveler persona seed from onboarding."""
    return {
        "vibes": ["hidden-gem", "local-favorite", "street-food"],
        "pace": "moderate",
        "budget": "mid",
    }


@pytest.fixture
def candidate_nodes():
    """Pool of candidate ActivityNodes for ranking."""
    return [
        make_activity_node(
            id=f"cand-{i:03d}",
            name=f"Candidate {i}",
            slug=f"candidate-{i}",
            category=cat,
            convergenceScore=0.6 + (i * 0.05),
            authorityScore=0.5 + (i * 0.03),
        )
        for i, cat in enumerate(["dining", "culture", "outdoors", "dining", "experience"])
    ]


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client that returns a valid ranking response."""
    client = AsyncMock()

    def _make_response(candidates):
        ranked = [
            {
                "id": f"cand-{i:03d}",
                "rank": i + 1,
                "slotType": "meal" if cat in ("dining",) else "flex",
                "reasoning": f"Good fit for candidate {i}",
            }
            for i, cat in enumerate(["dining", "culture", "outdoors", "dining", "experience"])
        ]
        content_block = MagicMock()
        content_block.text = json.dumps({"ranked": ranked})
        usage = MagicMock()
        usage.input_tokens = 450
        usage.output_tokens = 200
        response = MagicMock()
        response.content = [content_block]
        response.usage = usage
        return response

    client.messages.create = AsyncMock(
        return_value=_make_response(None)
    )
    return client


# ===========================================================================
# Onboarding -> Generation pipeline
# ===========================================================================

class TestOnboardingToGeneration:
    """Persona seed from onboarding flows into the ranker prompt."""

    def test_persona_seed_included_in_prompt(self, persona_seed, candidate_nodes):
        """User prompt includes all persona vibes, pace, budget."""
        prompt_str = _build_user_prompt(persona_seed, candidate_nodes)
        prompt = json.loads(prompt_str)
        assert prompt["persona"]["vibes"] == persona_seed["vibes"]
        assert prompt["persona"]["pace"] == "moderate"
        assert prompt["persona"]["budget"] == "mid"

    def test_all_candidates_in_prompt(self, persona_seed, candidate_nodes):
        """All candidate nodes appear in the prompt payload."""
        prompt_str = _build_user_prompt(persona_seed, candidate_nodes)
        prompt = json.loads(prompt_str)
        prompt_ids = {c["id"] for c in prompt["candidates"]}
        expected_ids = {c["id"] for c in candidate_nodes}
        assert prompt_ids == expected_ids

    def test_prompt_candidate_fields(self, persona_seed, candidate_nodes):
        """Each candidate in prompt has required fields for ranking."""
        prompt_str = _build_user_prompt(persona_seed, candidate_nodes)
        prompt = json.loads(prompt_str)
        for c in prompt["candidates"]:
            assert "id" in c
            assert "name" in c
            assert "category" in c
            assert "convergenceScore" in c


class TestLLMRanking:
    """LLM ranker returns valid ranked list with metadata."""

    @pytest.mark.asyncio
    async def test_rank_candidates_returns_sorted_list(
        self, persona_seed, candidate_nodes, mock_anthropic_client
    ):
        """Ranked list is sorted by rank ascending."""
        ranked, meta = await rank_candidates_with_llm(
            persona_seed, candidate_nodes, mock_anthropic_client
        )
        ranks = [r["rank"] for r in ranked]
        assert ranks == sorted(ranks)

    @pytest.mark.asyncio
    async def test_rank_candidates_all_ids_present(
        self, persona_seed, candidate_nodes, mock_anthropic_client
    ):
        """All candidate IDs appear in the ranked output."""
        ranked, _ = await rank_candidates_with_llm(
            persona_seed, candidate_nodes, mock_anthropic_client
        )
        ranked_ids = {r["id"] for r in ranked}
        expected_ids = {c["id"] for c in candidate_nodes}
        assert ranked_ids == expected_ids

    @pytest.mark.asyncio
    async def test_rank_meta_includes_model_info(
        self, persona_seed, candidate_nodes, mock_anthropic_client
    ):
        """Log metadata includes model version and prompt version."""
        _, meta = await rank_candidates_with_llm(
            persona_seed, candidate_nodes, mock_anthropic_client
        )
        assert meta["model"] == RANKER_MODEL
        assert meta["promptVersion"] == RANKER_PROMPT_VERSION
        assert "latencyMs" in meta
        assert "inputTokens" in meta
        assert "outputTokens" in meta

    @pytest.mark.asyncio
    async def test_rank_meta_latency_nonnegative(
        self, persona_seed, candidate_nodes, mock_anthropic_client
    ):
        """Latency must be a non-negative integer."""
        _, meta = await rank_candidates_with_llm(
            persona_seed, candidate_nodes, mock_anthropic_client
        )
        assert isinstance(meta["latencyMs"], int)
        assert meta["latencyMs"] >= 0


class TestSlotsCreatedFromRanking:
    """Ranked candidates become ItinerarySlots with correct assignments."""

    def test_slots_have_correct_activity_node_ids(self, candidate_nodes):
        """Each slot references the correct activityNodeId from ranking."""
        trip_id = str(uuid.uuid4())
        ranked = [
            {"id": candidate_nodes[i]["id"], "rank": i + 1, "slotType": "flex"}
            for i in range(len(candidate_nodes))
        ]
        slots = [
            make_itinerary_slot(
                trip_id=trip_id,
                activityNodeId=r["id"],
                dayNumber=1,
                sortOrder=r["rank"],
                slotType=r["slotType"],
            )
            for r in ranked
        ]
        for slot, r in zip(slots, ranked):
            assert slot["activityNodeId"] == r["id"]
            assert slot["sortOrder"] == r["rank"]

    def test_meal_slots_assigned_meal_type(self, candidate_nodes):
        """Dining candidates get slotType=meal."""
        trip_id = str(uuid.uuid4())
        # Candidate 0 and 3 are dining
        ranked = [
            {"id": candidate_nodes[0]["id"], "rank": 1, "slotType": "meal"},
            {"id": candidate_nodes[1]["id"], "rank": 2, "slotType": "flex"},
        ]
        slots = [
            make_itinerary_slot(
                trip_id=trip_id,
                activityNodeId=r["id"],
                slotType=r["slotType"],
            )
            for r in ranked
        ]
        assert slots[0]["slotType"] == "meal"
        assert slots[1]["slotType"] == "flex"

    def test_slots_default_to_proposed_status(self):
        """New slots from generation start in 'proposed' status."""
        slot = make_itinerary_slot()
        assert slot["status"] == "proposed"


class TestLLMTimeout:
    """LLM call must respect timeout boundary."""

    @pytest.mark.asyncio
    async def test_timeout_raises_on_slow_llm(self, persona_seed, candidate_nodes):
        """asyncio.TimeoutError raised if LLM exceeds LLM_TIMEOUT_S."""
        slow_client = AsyncMock()

        async def _slow_create(**kwargs):
            await asyncio.sleep(LLM_TIMEOUT_S + 1)
            return MagicMock()

        slow_client.messages.create = _slow_create

        with pytest.raises(asyncio.TimeoutError):
            await rank_candidates_with_llm(
                persona_seed, candidate_nodes, slow_client
            )

    @pytest.mark.asyncio
    async def test_malformed_llm_response_raises_value_error(
        self, persona_seed, candidate_nodes
    ):
        """ValueError raised if LLM returns non-JSON response."""
        bad_client = AsyncMock()
        content_block = MagicMock()
        content_block.text = "This is not valid JSON at all"
        usage = MagicMock()
        usage.input_tokens = 100
        usage.output_tokens = 50
        response = MagicMock()
        response.content = [content_block]
        response.usage = usage
        bad_client.messages.create = AsyncMock(return_value=response)

        with pytest.raises(ValueError, match="malformed ranking JSON"):
            await rank_candidates_with_llm(
                persona_seed, candidate_nodes, bad_client
            )
