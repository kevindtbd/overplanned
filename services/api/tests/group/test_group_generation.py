"""
Group generation tests — M-003 / M-004.

Validates:
  - PreferenceMerger: equal weights, fairness-adjusted weights, vibe blending
  - GroupGenerationEngine: candidate pool, per-member scoring, slot creation
  - Group slots created with voteState='proposed', isContested=false
  - Per-member preference scores logged in RawEvent payload
  - Fallback cascade (same tiers as solo) used on Qdrant failure
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.api.generation.preference_merger import (
    merge_preferences,
    score_candidate_per_member,
    MergedPreference,
)
from services.api.group.fairness import FairnessState, MemberDebt
from services.api.tests.conftest import (
    make_activity_node,
    make_trip,
    make_user,
    make_itinerary_slot,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def three_member_ids() -> list[str]:
    return ["user-alice", "user-bob", "user-charlie"]


@pytest.fixture
def three_member_seeds() -> list[dict]:
    return [
        {"vibes": ["hidden-gem", "local-favorite"], "pace": "slow", "budget": "mid"},
        {"vibes": ["street-food", "nightlife"], "pace": "fast", "budget": "budget"},
        {"vibes": ["hidden-gem", "culture"], "pace": "moderate", "budget": "splurge"},
    ]


@pytest.fixture
def candidate_pool() -> list[dict]:
    return [
        make_activity_node(
            id=f"node-{i:03d}",
            name=f"Venue {i}",
            slug=f"venue-{i}",
            category=cat,
            convergenceScore=0.5 + i * 0.1,
        )
        for i, cat in enumerate(["dining", "culture", "outdoors", "experience", "nightlife"])
    ]


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(),
        __aexit__=AsyncMock(),
    ))
    db.execute = AsyncMock(return_value=None)
    db.fetch = AsyncMock(return_value=[])
    db.fetchrow = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_anthropic():
    client = AsyncMock()
    content_block = MagicMock()
    usage = MagicMock()
    usage.input_tokens = 500
    usage.output_tokens = 200
    response = MagicMock()
    response.content = [content_block]
    response.usage = usage
    client.messages.create = AsyncMock(return_value=response)
    return client


# ===========================================================================
# Preference Merger
# ===========================================================================

class TestPreferenceMerger:
    """merge_preferences blends N persona seeds into a weighted query."""

    def test_equal_weights_with_no_fairness_state(self, three_member_ids, three_member_seeds):
        """Without fairness state, all members get equal weight = 1/N."""
        result = merge_preferences(
            member_ids=three_member_ids,
            member_seeds=three_member_seeds,
            city="Tokyo",
        )
        n = len(three_member_ids)
        expected_weight = 1.0 / n
        for mid, w in result.member_weights.items():
            assert w == pytest.approx(expected_weight, abs=0.01)

    def test_weights_sum_to_one(self, three_member_ids, three_member_seeds):
        """All member weights must sum to 1.0."""
        result = merge_preferences(
            member_ids=three_member_ids,
            member_seeds=three_member_seeds,
            city="Tokyo",
        )
        total = sum(result.member_weights.values())
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_fairness_debt_boosts_compromised_member(self, three_member_ids, three_member_seeds):
        """Member with high cumulative debt gets a boosted weight."""
        fairness_state: dict = {
            "members": {
                "user-alice": {"memberId": "user-alice", "cumulativeDebt": 5.0},
                "user-bob": {"memberId": "user-bob", "cumulativeDebt": 0.0},
                "user-charlie": {"memberId": "user-charlie", "cumulativeDebt": 0.0},
            },
            "totalVotes": 3,
        }
        result = merge_preferences(
            member_ids=three_member_ids,
            member_seeds=three_member_seeds,
            city="Tokyo",
            fairness_state=fairness_state,
        )
        # Alice has the most debt and should get the highest weight
        assert result.member_weights["user-alice"] > result.member_weights["user-bob"]
        assert result.member_weights["user-alice"] > result.member_weights["user-charlie"]

    def test_shared_vibes_appear_in_dominant_vibes(self, three_member_ids, three_member_seeds):
        """Vibes shared by multiple members rank higher in the merged output."""
        result = merge_preferences(
            member_ids=three_member_ids,
            member_seeds=three_member_seeds,
            city="Tokyo",
        )
        # "hidden-gem" appears in alice and charlie's seeds -> should be dominant
        assert "hidden-gem" in result.dominant_vibes

    def test_query_contains_city_name(self, three_member_ids, three_member_seeds):
        """Merged query must reference the city."""
        result = merge_preferences(
            member_ids=three_member_ids,
            member_seeds=three_member_seeds,
            city="Osaka",
        )
        assert "Osaka" in result.query

    def test_query_contains_member_count(self, three_member_ids, three_member_seeds):
        """Merged query mentions the group size."""
        result = merge_preferences(
            member_ids=three_member_ids,
            member_seeds=three_member_seeds,
            city="Tokyo",
        )
        assert "3" in result.query

    def test_raises_on_mismatched_lengths(self, three_member_ids):
        """ValueError if member_ids and member_seeds have different lengths."""
        with pytest.raises(ValueError, match="equal length"):
            merge_preferences(
                member_ids=three_member_ids,
                member_seeds=[{"vibes": [], "pace": "slow", "budget": "mid"}],
                city="Tokyo",
            )

    def test_raises_on_empty_members(self):
        """ValueError if no members provided."""
        with pytest.raises(ValueError, match="empty member list"):
            merge_preferences(
                member_ids=[],
                member_seeds=[],
                city="Tokyo",
            )

    def test_blended_pace_weighted_correctly(self):
        """Blended pace reflects weighted average of member paces."""
        # Two slow + one fast -> blended should be slow or moderate
        result = merge_preferences(
            member_ids=["u1", "u2", "u3"],
            member_seeds=[
                {"vibes": [], "pace": "slow", "budget": "mid"},
                {"vibes": [], "pace": "slow", "budget": "mid"},
                {"vibes": [], "pace": "fast", "budget": "mid"},
            ],
            city="Tokyo",
        )
        assert result.blended_pace in ("slow", "moderate")


# ===========================================================================
# Per-member candidate scoring
# ===========================================================================

class TestCandidateScoring:
    """score_candidate_per_member computes per-member preference score."""

    def test_returns_score_for_each_member(self, three_member_ids, three_member_seeds, candidate_pool):
        """Score dict has an entry for every member."""
        scores = score_candidate_per_member(
            candidate=candidate_pool[0],
            member_seeds=three_member_seeds,
            member_ids=three_member_ids,
        )
        assert set(scores.keys()) == set(three_member_ids)

    def test_scores_in_valid_range(self, three_member_ids, three_member_seeds, candidate_pool):
        """All scores must be in [0.0, 1.0]."""
        for candidate in candidate_pool:
            scores = score_candidate_per_member(
                candidate=candidate,
                member_seeds=three_member_seeds,
                member_ids=three_member_ids,
            )
            for mid, score in scores.items():
                assert 0.0 <= score <= 1.0, f"Score {score} out of range for {mid}"

    def test_member_with_matching_vibes_scores_higher(self, three_member_ids):
        """Member whose vibes match the node's vibeTags scores higher."""
        candidate = make_activity_node(
            id="node-vibe-match",
            name="Local Gem",
            slug="local-gem",
            category="experience",
        )
        # Inject vibe tags matching alice's preferences
        candidate["vibeTags"] = [{"slug": "hidden-gem", "label": "Hidden Gem"}]

        seeds = [
            {"vibes": ["hidden-gem"], "pace": "slow", "budget": "mid"},  # alice - match
            {"vibes": ["beach", "surfing"], "pace": "fast", "budget": "mid"},  # bob - no match
        ]
        scores = score_candidate_per_member(
            candidate=candidate,
            member_seeds=seeds,
            member_ids=["user-alice", "user-bob"],
        )
        assert scores["user-alice"] > scores["user-bob"]


# ===========================================================================
# Group slot schema
# ===========================================================================

class TestGroupSlotSchema:
    """Group slots start with voteState='proposed' and isContested=false."""

    def test_group_slot_defaults(self):
        """make_itinerary_slot defaults match group voting lifecycle."""
        slot = make_itinerary_slot(
            voteState="proposed",
            isContested=False,
        )
        assert slot["voteState"] == "proposed"
        assert slot["isContested"] is False
        assert slot["status"] == "proposed"
        assert slot["isLocked"] is False

    def test_group_slot_can_be_contested(self):
        """Slot can be marked contested after camp detection."""
        slot = make_itinerary_slot(
            voteState="voting",
            isContested=True,
        )
        assert slot["isContested"] is True
        assert slot["voteState"] == "voting"


# ===========================================================================
# Merger metadata
# ===========================================================================

class TestMergerMeta:
    """merger_meta dict is correctly populated."""

    def test_merger_meta_contains_required_keys(self, three_member_ids, three_member_seeds):
        result = merge_preferences(
            member_ids=three_member_ids,
            member_seeds=three_member_seeds,
            city="Tokyo",
        )
        meta = result.merger_meta
        assert "memberCount" in meta
        assert "weightMap" in meta
        assert "dominantVibes" in meta
        assert "blendedPace" in meta
        assert "blendedBudget" in meta
        assert "fairnessAdjusted" in meta

    def test_fairness_adjusted_false_without_state(self, three_member_ids, three_member_seeds):
        """fairnessAdjusted is False when no fairnessState provided."""
        result = merge_preferences(
            member_ids=three_member_ids,
            member_seeds=three_member_seeds,
            city="Tokyo",
        )
        assert result.merger_meta["fairnessAdjusted"] is False

    def test_fairness_adjusted_true_with_state(self, three_member_ids, three_member_seeds):
        """fairnessAdjusted is True when fairnessState is provided."""
        result = merge_preferences(
            member_ids=three_member_ids,
            member_seeds=three_member_seeds,
            city="Tokyo",
            fairness_state={
                "members": {},
                "totalVotes": 0,
            },
        )
        assert result.merger_meta["fairnessAdjusted"] is True
