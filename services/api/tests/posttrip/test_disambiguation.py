"""
Integration tests: disambiguation batch produces correct IntentionSignals.

Covers:
- Rule evaluation: each of the 6 rules produces correct intention + confidence
- Explicit feedback takes precedence over rule-based inference
- Idempotency: re-running batch doesn't create duplicate IntentionSignals
- Cross-track: pivot signals from Track 5 (mid-trip) visible in disambiguation context
- Condition matching: gt, lt, in, direct value operators
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.api.posttrip.disambiguation import (
    load_rules,
    matches_condition,
    evaluate_rule,
    get_signal_context,
    infer_intention,
    process_signal,
    run_disambiguation_batch,
)


# ===================================================================
# 1. Rule loading
# ===================================================================

class TestRuleLoading:
    """Tests for loading disambiguation rules from JSON."""

    def test_loads_six_rules(self):
        """Should load exactly 6 rules from disambiguation_rules.json."""
        rules = load_rules()
        assert len(rules) == 6

    def test_each_rule_has_required_fields(self):
        """Each rule must have id, conditions, intention, confidence."""
        rules = load_rules()
        for rule in rules:
            assert "id" in rule
            assert "conditions" in rule
            assert "intention" in rule
            assert "confidence" in rule
            assert 0.0 <= rule["confidence"] <= 1.0


# ===================================================================
# 2. Condition matching operators
# ===================================================================

class TestConditionMatching:
    """Tests for matches_condition() -- the core rule evaluation primitive."""

    def test_direct_equality(self):
        assert matches_condition("post_skipped", "post_skipped") is True
        assert matches_condition("slot_view", "post_skipped") is False

    def test_gt_operator(self):
        assert matches_condition(15, {"gt": 10}) is True
        assert matches_condition(10, {"gt": 10}) is False
        assert matches_condition(5, {"gt": 10}) is False

    def test_lt_operator(self):
        assert matches_condition(3, {"lt": 5}) is True
        assert matches_condition(5, {"lt": 5}) is False

    def test_gte_operator(self):
        assert matches_condition(10, {"gte": 10}) is True
        assert matches_condition(9, {"gte": 10}) is False

    def test_lte_operator(self):
        assert matches_condition(10, {"lte": 10}) is True
        assert matches_condition(11, {"lte": 10}) is False

    def test_in_operator(self):
        assert matches_condition("rain", {"in": ["rain", "snow"]}) is True
        assert matches_condition("clear", {"in": ["rain", "snow"]}) is False

    def test_boolean_equality(self):
        assert matches_condition(True, True) is True
        assert matches_condition(False, True) is False

    def test_unknown_operator_returns_false(self):
        assert matches_condition(10, {"unknown_op": 5}) is False


# ===================================================================
# 3. Rule evaluation
# ===================================================================

class TestRuleEvaluation:
    """Tests for evaluate_rule() -- full rule matching against context."""

    def test_all_conditions_must_match(self):
        """Rule matches only when ALL conditions are satisfied."""
        rule = {
            "conditions": {
                "signal_type": "post_skipped",
                "weather_condition": "rain",
                "activity_category": "outdoors",
            }
        }
        context_match = {
            "signal_type": "post_skipped",
            "weather_condition": "rain",
            "activity_category": "outdoors",
        }
        context_partial = {
            "signal_type": "post_skipped",
            "weather_condition": "clear",  # mismatch
            "activity_category": "outdoors",
        }
        assert evaluate_rule(rule, context_match) is True
        assert evaluate_rule(rule, context_partial) is False

    def test_missing_context_key_fails(self):
        """If a required context key is missing, rule doesn't match."""
        rule = {
            "conditions": {
                "signal_type": "post_skipped",
                "previously_visited": True,
            }
        }
        context = {"signal_type": "post_skipped"}  # missing previously_visited
        assert evaluate_rule(rule, context) is False


# ===================================================================
# 4. Each of the 6 disambiguation rules
# ===================================================================

class TestDisambiguationRules:
    """Tests that each rule produces the expected intention + confidence."""

    @pytest.mark.asyncio
    async def test_weather_outdoor_skip(self, mock_db_posttrip):
        """Rule: outdoor + rain -> weather (0.7)."""
        signal = MagicMock()
        signal.id = "sig-1"
        signal.signalType = "post_skipped"
        signal.userId = "user-1"
        signal.signal_metadata = {"activity_category": "outdoors"}
        signal.slotId = None
        signal.tripId = None
        signal.weatherContext = json.dumps({"condition": "rain"})

        result = await infer_intention(mock_db_posttrip.mock, signal)
        assert result is not None
        intention, confidence = result
        assert intention == "weather"
        assert confidence == 0.7

    @pytest.mark.asyncio
    async def test_clear_dining_skip(self, mock_db_posttrip):
        """Rule: dining + clear weather -> not_interested (0.6)."""
        signal = MagicMock()
        signal.id = "sig-2"
        signal.signalType = "post_skipped"
        signal.userId = "user-1"
        signal.signal_metadata = {"activity_category": "dining"}
        signal.slotId = None
        signal.tripId = None
        signal.weatherContext = json.dumps({"condition": "clear"})

        result = await infer_intention(mock_db_posttrip.mock, signal)
        assert result is not None
        intention, confidence = result
        assert intention == "not_interested"
        assert confidence == 0.6

    @pytest.mark.asyncio
    async def test_time_overrun_skip(self, mock_db_posttrip):
        """Rule: time_overrun=true -> bad_timing (0.8)."""
        signal = MagicMock()
        signal.id = "sig-3"
        signal.signalType = "post_skipped"
        signal.userId = "user-1"
        signal.signal_metadata = {"time_overrun": True}
        signal.slotId = None
        signal.tripId = None
        signal.weatherContext = None

        result = await infer_intention(mock_db_posttrip.mock, signal)
        assert result is not None
        intention, confidence = result
        assert intention == "bad_timing"
        assert confidence == 0.8

    @pytest.mark.asyncio
    async def test_distance_skip(self, mock_db_posttrip):
        """Rule: distance_km > 10 -> too_far (0.75)."""
        signal = MagicMock()
        signal.id = "sig-4"
        signal.signalType = "post_skipped"
        signal.userId = "user-1"
        signal.signal_metadata = {"distance_km": 15}
        signal.slotId = None
        signal.tripId = None
        signal.weatherContext = None

        result = await infer_intention(mock_db_posttrip.mock, signal)
        assert result is not None
        intention, confidence = result
        assert intention == "too_far"
        assert confidence == 0.75

    @pytest.mark.asyncio
    async def test_group_conflict_skip(self, mock_db_posttrip):
        """Rule: group trip + preference conflict -> group_conflict (0.65)."""
        signal = MagicMock()
        signal.id = "sig-5"
        signal.signalType = "post_skipped"
        signal.userId = "user-1"
        signal.signal_metadata = {"has_preference_conflict": True}
        signal.slotId = None
        signal.tripId = "trip-group"
        signal.weatherContext = None

        # SA: session.execute(select(Trip).where(...)) -> scalars().first() -> trip
        trip = MagicMock()
        trip.memberCount = 3  # group trip
        mock_db_posttrip.returns_one(trip)

        result = await infer_intention(mock_db_posttrip.mock, signal)
        assert result is not None
        intention, confidence = result
        assert intention == "group_conflict"
        assert confidence == 0.65

    @pytest.mark.asyncio
    async def test_revisit_skip(self, mock_db_posttrip):
        """Rule: previously_visited=true -> already_visited (0.7)."""
        signal = MagicMock()
        signal.id = "sig-6"
        signal.signalType = "post_skipped"
        signal.userId = "user-1"
        signal.signal_metadata = {"previously_visited": True}
        signal.slotId = None
        signal.tripId = None
        signal.weatherContext = None

        result = await infer_intention(mock_db_posttrip.mock, signal)
        assert result is not None
        intention, confidence = result
        assert intention == "already_visited"
        assert confidence == 0.7

    @pytest.mark.asyncio
    async def test_no_rule_matches_returns_none(self, mock_db_posttrip):
        """When no rule matches, infer_intention returns None."""
        signal = MagicMock()
        signal.id = "sig-none"
        signal.signalType = "post_skipped"
        signal.userId = "user-1"
        signal.signal_metadata = {}  # no metadata to trigger any rule
        signal.slotId = None
        signal.tripId = None
        signal.weatherContext = None

        result = await infer_intention(mock_db_posttrip.mock, signal)
        assert result is None


# ===================================================================
# 5. Explicit feedback precedence
# ===================================================================

class TestExplicitFeedbackPrecedence:
    """Explicit feedback should prevent rule-based inference."""

    @pytest.mark.asyncio
    async def test_explicit_feedback_skips_inference(self, mock_db_posttrip):
        """If explicit_feedback IntentionSignal exists, process_signal returns False."""
        signal = MagicMock()
        signal.id = "sig-explicit"
        signal.userId = "user-1"

        # SA: first execute -> select IntentionSignal where source=explicit_feedback
        # returns an existing intention
        existing = MagicMock()
        existing.source = "explicit_feedback"
        mock_db_posttrip.returns_one(existing)

        result = await process_signal(mock_db_posttrip.mock, signal)
        assert result is False


# ===================================================================
# 6. Idempotency
# ===================================================================

class TestBatchIdempotency:
    """Re-running the batch should not create duplicate IntentionSignals."""

    @pytest.mark.asyncio
    async def test_existing_rule_inference_skipped(self, mock_db_posttrip):
        """If rule_heuristic IntentionSignal exists, process_signal returns False."""
        signal = MagicMock()
        signal.id = "sig-idem"
        signal.userId = "user-1"

        # First execute: check explicit_feedback -> None
        mock_db_posttrip.returns_none()
        # Second execute: check rule_heuristic -> existing
        existing_rule = MagicMock()
        existing_rule.source = "rule_heuristic"
        mock_db_posttrip.returns_one(existing_rule)

        result = await process_signal(mock_db_posttrip.mock, signal)
        assert result is False

    @pytest.mark.asyncio
    async def test_batch_stats_correct(self, mock_db_posttrip):
        """Batch stats should accurately reflect processed/created/skipped."""
        sig1 = MagicMock()
        sig1.id = "sig-new"
        sig1.signalType = "post_skipped"
        sig1.userId = "user-1"
        sig1.signal_metadata = {"time_overrun": True}
        sig1.slotId = None
        sig1.tripId = None
        sig1.weatherContext = None
        sig1.createdAt = datetime.now(timezone.utc)

        sig2 = MagicMock()
        sig2.id = "sig-existing"
        sig2.signalType = "post_skipped"
        sig2.userId = "user-1"
        sig2.signal_metadata = {}
        sig2.slotId = None
        sig2.tripId = None
        sig2.weatherContext = None
        sig2.createdAt = datetime.now(timezone.utc)

        # First execute: select BehavioralSignal -> [sig1, sig2]
        mock_db_posttrip.returns_many([sig1, sig2])

        # For sig1 (process_signal):
        #   check explicit_feedback -> None
        mock_db_posttrip.returns_none()
        #   check rule_heuristic -> None
        mock_db_posttrip.returns_none()
        #   infer_intention succeeds (time_overrun rule)
        #   insert IntentionSignal -> rowcount
        mock_db_posttrip.returns_rowcount(1)

        # For sig2 (process_signal):
        #   check explicit_feedback -> None
        mock_db_posttrip.returns_none()
        #   check rule_heuristic -> None
        mock_db_posttrip.returns_none()
        #   infer_intention returns None (no matching rule, empty metadata)

        stats = await run_disambiguation_batch(mock_db_posttrip.mock)

        assert stats["processed"] == 2
        assert stats["created"] + stats["skipped"] == 2


# ===================================================================
# 7. Cross-track: pivot signals from Track 5
# ===================================================================

class TestCrossTrackPivotVisibility:
    """Pivot signals from mid-trip (Track 5) should be visible in disambiguation context."""

    @pytest.mark.asyncio
    async def test_pivot_signal_metadata_available_in_context(self, mock_db_posttrip):
        """Weather context from weatherContext field should inform disambiguation."""
        signal = MagicMock()
        signal.id = "sig-pivot-ctx"
        signal.signalType = "post_skipped"
        signal.userId = "user-1"
        signal.signal_metadata = {
            "activity_category": "outdoors",
        }
        signal.slotId = None
        signal.tripId = None
        signal.weatherContext = json.dumps({"condition": "rain", "pivot_source": "weather_trigger"})

        # No DB calls needed -- context comes from signal attributes
        context = await get_signal_context(mock_db_posttrip.mock, signal)

        assert context["weather_condition"] == "rain"
        assert context["activity_category"] == "outdoors"

    @pytest.mark.asyncio
    async def test_pivot_enriched_signal_triggers_weather_rule(self, mock_db_posttrip):
        """A skip signal with pivot weather context should trigger weather rule."""
        signal = MagicMock()
        signal.id = "sig-pivot-disambig"
        signal.signalType = "post_skipped"
        signal.userId = "user-1"
        signal.signal_metadata = {"activity_category": "outdoors"}
        signal.slotId = None
        signal.tripId = None
        signal.weatherContext = json.dumps({"condition": "rain"})

        result = await infer_intention(mock_db_posttrip.mock, signal)
        assert result is not None
        intention, confidence = result
        assert intention == "weather"
