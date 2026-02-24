"""
Tests for Phase 6.6 -- HLLM Triggers (Subflow Routing)

Covers: each trigger condition, multiple triggers, subflow mapping,
novelty detection keywords, should_use_llm logic.
"""

from __future__ import annotations

import pytest

from services.api.models.hllm_triggers import (
    HLLMTrigger,
    HLLMTriggerDetector,
    NOVELTY_PHRASES,
    TriggerContext,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def detector():
    return HLLMTriggerDetector()


def _ctx(**overrides) -> TriggerContext:
    """Build a TriggerContext with defaults that fire zero triggers."""
    base = {
        "user_signal_count": 100,
        "trip_count": 10,
        "trip_member_count": 1,
        "ml_confidence": 0.9,
        "agreement_score": 0.8,
        "recent_signal_categories": ["dining", "dining", "dining", "dining", "dining"],
        "has_active_pivot": False,
        "user_message": None,
    }
    base.update(overrides)
    return TriggerContext(**base)


# ---------------------------------------------------------------------------
# Individual trigger checks
# ---------------------------------------------------------------------------

class TestColdUser:
    def test_fires_below_threshold(self, detector):
        ctx = _ctx(trip_count=2)
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.COLD_USER in triggers

    def test_does_not_fire_at_threshold(self, detector):
        ctx = _ctx(trip_count=3)
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.COLD_USER not in triggers

    def test_does_not_fire_above_threshold(self, detector):
        ctx = _ctx(trip_count=10)
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.COLD_USER not in triggers


class TestNoveltyRequest:
    def test_fires_on_something_different(self, detector):
        ctx = _ctx(user_message="I want something different this time")
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.NOVELTY_REQUEST in triggers

    def test_fires_on_surprise_me(self, detector):
        ctx = _ctx(user_message="Surprise me!")
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.NOVELTY_REQUEST in triggers

    def test_fires_on_hidden_gem(self, detector):
        ctx = _ctx(user_message="Show me a hidden gem")
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.NOVELTY_REQUEST in triggers

    def test_fires_on_off_beaten_path(self, detector):
        ctx = _ctx(user_message="Take me off the beaten path")
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.NOVELTY_REQUEST in triggers

    def test_does_not_fire_on_normal_message(self, detector):
        ctx = _ctx(user_message="Show me good restaurants")
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.NOVELTY_REQUEST not in triggers

    def test_does_not_fire_on_no_message(self, detector):
        ctx = _ctx(user_message=None)
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.NOVELTY_REQUEST not in triggers

    def test_case_insensitive(self, detector):
        ctx = _ctx(user_message="SURPRISE ME please")
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.NOVELTY_REQUEST in triggers


class TestLowMLConfidence:
    def test_fires_below_threshold(self, detector):
        ctx = _ctx(ml_confidence=0.2)
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.LOW_ML_CONFIDENCE in triggers

    def test_does_not_fire_above_threshold(self, detector):
        ctx = _ctx(ml_confidence=0.5)
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.LOW_ML_CONFIDENCE not in triggers


class TestHighDisagreement:
    def test_fires_below_threshold(self, detector):
        ctx = _ctx(agreement_score=0.1)
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.HIGH_DISAGREEMENT in triggers

    def test_does_not_fire_at_threshold(self, detector):
        ctx = _ctx(agreement_score=0.2)
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.HIGH_DISAGREEMENT not in triggers


class TestCuisineShift:
    def test_fires_on_category_change(self, detector):
        ctx = _ctx(recent_signal_categories=["dining", "dining", "dining", "nightlife"])
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.CUISINE_SHIFT in triggers

    def test_does_not_fire_on_consistent_categories(self, detector):
        ctx = _ctx(recent_signal_categories=["dining", "dining", "dining", "dining"])
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.CUISINE_SHIFT not in triggers

    def test_does_not_fire_with_too_few_signals(self, detector):
        ctx = _ctx(recent_signal_categories=["dining", "nightlife"])
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.CUISINE_SHIFT not in triggers


class TestGroupContext:
    def test_fires_with_3_plus_members(self, detector):
        ctx = _ctx(trip_member_count=3)
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.GROUP_CONTEXT in triggers

    def test_fires_with_5_members(self, detector):
        ctx = _ctx(trip_member_count=5)
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.GROUP_CONTEXT in triggers

    def test_does_not_fire_solo(self, detector):
        ctx = _ctx(trip_member_count=1)
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.GROUP_CONTEXT not in triggers

    def test_does_not_fire_duo(self, detector):
        ctx = _ctx(trip_member_count=2)
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.GROUP_CONTEXT not in triggers


class TestPivotEvent:
    def test_fires_with_active_pivot(self, detector):
        ctx = _ctx(has_active_pivot=True)
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.PIVOT_EVENT in triggers

    def test_does_not_fire_without_pivot(self, detector):
        ctx = _ctx(has_active_pivot=False)
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.PIVOT_EVENT not in triggers


# ---------------------------------------------------------------------------
# Multiple triggers
# ---------------------------------------------------------------------------

class TestMultipleTriggers:
    def test_multiple_triggers_fire_simultaneously(self, detector):
        ctx = _ctx(
            trip_count=1,
            ml_confidence=0.1,
            has_active_pivot=True,
        )
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.COLD_USER in triggers
        assert HLLMTrigger.LOW_ML_CONFIDENCE in triggers
        assert HLLMTrigger.PIVOT_EVENT in triggers
        assert len(triggers) >= 3

    def test_no_triggers_fire_with_safe_defaults(self, detector):
        ctx = _ctx()
        triggers = detector.detect_triggers(ctx)
        assert len(triggers) == 0


# ---------------------------------------------------------------------------
# should_use_llm
# ---------------------------------------------------------------------------

class TestShouldUseLLM:
    def test_true_when_triggers_present(self, detector):
        assert detector.should_use_llm([HLLMTrigger.COLD_USER]) is True

    def test_false_when_no_triggers(self, detector):
        assert detector.should_use_llm([]) is False

    def test_true_with_multiple_triggers(self, detector):
        triggers = [HLLMTrigger.COLD_USER, HLLMTrigger.PIVOT_EVENT]
        assert detector.should_use_llm(triggers) is True


# ---------------------------------------------------------------------------
# Subflow mapping
# ---------------------------------------------------------------------------

class TestSubflowMapping:
    def test_cold_user_subflow(self, detector):
        subflow = detector.get_subflow_for_triggers([HLLMTrigger.COLD_USER])
        assert subflow == "llm_cold_start"

    def test_novelty_subflow(self, detector):
        subflow = detector.get_subflow_for_triggers([HLLMTrigger.NOVELTY_REQUEST])
        assert subflow == "llm_novelty_generation"

    def test_pivot_subflow(self, detector):
        subflow = detector.get_subflow_for_triggers([HLLMTrigger.PIVOT_EVENT])
        assert subflow == "llm_pivot_handling"

    def test_group_subflow(self, detector):
        subflow = detector.get_subflow_for_triggers([HLLMTrigger.GROUP_CONTEXT])
        assert subflow == "llm_group_consensus"

    def test_no_triggers_returns_default(self, detector):
        subflow = detector.get_subflow_for_triggers([])
        assert subflow == "ml_default"

    def test_multiple_triggers_uses_first(self, detector):
        triggers = [HLLMTrigger.PIVOT_EVENT, HLLMTrigger.COLD_USER]
        subflow = detector.get_subflow_for_triggers(triggers)
        assert subflow == "llm_pivot_handling"

    def test_all_triggers_have_subflows(self, detector):
        for trigger in HLLMTrigger:
            subflow = detector.get_subflow_for_triggers([trigger])
            assert subflow != "ml_default"
            assert subflow.startswith("llm_")
