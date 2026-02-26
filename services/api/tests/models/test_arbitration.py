"""
Tests for Phase 6.5 -- Arbitration Layer

Covers: each rule fires correctly, priority order, blend interleaving,
agreement score, ArbitrationEvent SQL, cold user routing, exploration budget.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from services.api.models.arbitration import (
    ArbitrationContext,
    ArbitrationDecision,
    ArbitrationRule,
    Arbitrator,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def arbitrator():
    return Arbitrator()


def _ctx(**overrides) -> ArbitrationContext:
    """Build an ArbitrationContext with sensible defaults."""
    base = {
        "user_signal_count": 50,
        "trip_count": 5,
        "ml_confidence": 0.8,
        "ml_rankings": ["a", "b", "c", "d", "e"],
        "llm_rankings": ["f", "g", "h", "i", "j"],
        "persona_vibes": ["warm_slow"],
        "exploration_budget_remaining": 0,
    }
    base.update(overrides)
    return ArbitrationContext(**base)


# ---------------------------------------------------------------------------
# Agreement score
# ---------------------------------------------------------------------------

class TestAgreementScore:
    def test_no_overlap(self, arbitrator):
        score = arbitrator.compute_agreement_score(
            ["a", "b", "c", "d", "e"],
            ["f", "g", "h", "i", "j"],
        )
        assert score == 0.0

    def test_full_overlap(self, arbitrator):
        items = ["a", "b", "c", "d", "e"]
        score = arbitrator.compute_agreement_score(items, items)
        assert score == 1.0

    def test_partial_overlap(self, arbitrator):
        ml = ["a", "b", "c", "d", "e"]
        llm = ["a", "b", "x", "y", "z"]
        score = arbitrator.compute_agreement_score(ml, llm)
        assert score == pytest.approx(0.4)  # 2/5

    def test_empty_lists(self, arbitrator):
        assert arbitrator.compute_agreement_score([], []) == 0.0

    def test_one_empty(self, arbitrator):
        assert arbitrator.compute_agreement_score(["a"], []) == 0.0

    def test_short_lists(self, arbitrator):
        # Less than k items
        score = arbitrator.compute_agreement_score(["a", "b"], ["a", "c"])
        # top-5 of ["a","b"] = {"a","b"}, top-5 of ["a","c"] = {"a","c"}
        # overlap = 1, / 5 = 0.2
        assert score == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# Rule priority: LLM_COLD (trip_count == 0)
# ---------------------------------------------------------------------------

class TestLLMColdRule:
    def test_cold_user_fires(self, arbitrator):
        ctx = _ctx(trip_count=0, user_signal_count=0, ml_confidence=0.9)
        decision = arbitrator.arbitrate(ctx)
        assert decision.rule_fired == ArbitrationRule.LLM_COLD
        assert decision.served_source == "llm"
        assert decision.served_rankings == ctx.llm_rankings

    def test_cold_user_overrides_ml_confidence(self, arbitrator):
        ctx = _ctx(trip_count=0, ml_confidence=0.99, user_signal_count=100)
        decision = arbitrator.arbitrate(ctx)
        assert decision.rule_fired == ArbitrationRule.LLM_COLD


# ---------------------------------------------------------------------------
# Rule priority: LLM_WINS (user_signal_count < 10)
# ---------------------------------------------------------------------------

class TestLLMWinsRule:
    def test_low_signal_count_fires(self, arbitrator):
        ctx = _ctx(trip_count=2, user_signal_count=5, ml_confidence=0.9)
        decision = arbitrator.arbitrate(ctx)
        assert decision.rule_fired == ArbitrationRule.LLM_WINS
        assert decision.served_source == "llm"

    def test_signal_count_exactly_10_does_not_fire(self, arbitrator):
        ctx = _ctx(trip_count=2, user_signal_count=10, ml_confidence=0.9)
        decision = arbitrator.arbitrate(ctx)
        # Should NOT be LLM_WINS, should fall through to ML_WINS or others
        assert decision.rule_fired != ArbitrationRule.LLM_WINS


# ---------------------------------------------------------------------------
# Rule priority: ML_EXPLORE
# ---------------------------------------------------------------------------

class TestMLExploreRule:
    def test_exploration_budget_fires(self, arbitrator):
        ctx = _ctx(
            trip_count=3,
            user_signal_count=20,
            ml_confidence=0.9,
            exploration_budget_remaining=5,
        )
        decision = arbitrator.arbitrate(ctx)
        assert decision.rule_fired == ArbitrationRule.ML_EXPLORE
        assert decision.served_source == "ml"
        assert decision.served_rankings == ctx.ml_rankings

    def test_zero_budget_does_not_fire(self, arbitrator):
        ctx = _ctx(
            trip_count=3,
            user_signal_count=20,
            ml_confidence=0.9,
            exploration_budget_remaining=0,
        )
        decision = arbitrator.arbitrate(ctx)
        assert decision.rule_fired != ArbitrationRule.ML_EXPLORE


# ---------------------------------------------------------------------------
# Rule priority: ML_WINS
# ---------------------------------------------------------------------------

class TestMLWinsRule:
    def test_high_confidence_and_agreement(self, arbitrator):
        ml = ["a", "b", "c", "d", "e"]
        llm = ["a", "b", "c", "x", "y"]
        ctx = _ctx(
            trip_count=3,
            user_signal_count=50,
            ml_confidence=0.8,
            ml_rankings=ml,
            llm_rankings=llm,
        )
        decision = arbitrator.arbitrate(ctx)
        assert decision.rule_fired == ArbitrationRule.ML_WINS
        assert decision.served_source == "ml"

    def test_high_confidence_low_agreement_falls_through(self, arbitrator):
        ctx = _ctx(
            trip_count=3,
            user_signal_count=50,
            ml_confidence=0.8,
            ml_rankings=["a", "b", "c", "d", "e"],
            llm_rankings=["f", "g", "h", "i", "j"],
        )
        decision = arbitrator.arbitrate(ctx)
        # agreement = 0.0, so ML_WINS should NOT fire; falls to BLEND
        assert decision.rule_fired == ArbitrationRule.BLEND


# ---------------------------------------------------------------------------
# Rule priority: BLEND
# ---------------------------------------------------------------------------

class TestBlendRule:
    def test_moderate_confidence_triggers_blend(self, arbitrator):
        ctx = _ctx(
            trip_count=3,
            user_signal_count=50,
            ml_confidence=0.6,
            ml_rankings=["a", "b", "c"],
            llm_rankings=["d", "e", "f"],
        )
        decision = arbitrator.arbitrate(ctx)
        assert decision.rule_fired == ArbitrationRule.BLEND
        assert decision.served_source == "blend"

    def test_blend_interleaves_correctly(self, arbitrator):
        ml = ["a", "b", "c"]
        llm = ["d", "e", "f"]
        blended = arbitrator._blend_rankings(ml, llm)
        assert blended == ["a", "d", "b", "e", "c", "f"]

    def test_blend_deduplicates(self, arbitrator):
        ml = ["a", "b", "c"]
        llm = ["b", "d", "a"]
        blended = arbitrator._blend_rankings(ml, llm)
        assert len(blended) == len(set(blended))
        assert blended == ["a", "b", "d", "c"]

    def test_blend_unequal_lengths(self, arbitrator):
        ml = ["a", "b"]
        llm = ["c", "d", "e", "f"]
        blended = arbitrator._blend_rankings(ml, llm)
        assert blended == ["a", "c", "b", "d", "e", "f"]


# ---------------------------------------------------------------------------
# Default fallback: LLM_WINS
# ---------------------------------------------------------------------------

class TestDefaultFallback:
    def test_low_confidence_defaults_to_llm(self, arbitrator):
        ctx = _ctx(
            trip_count=3,
            user_signal_count=50,
            ml_confidence=0.3,
        )
        decision = arbitrator.arbitrate(ctx)
        assert decision.rule_fired == ArbitrationRule.LLM_WINS
        assert decision.served_source == "llm"


# ---------------------------------------------------------------------------
# Priority order enforcement
# ---------------------------------------------------------------------------

class TestPriorityOrder:
    def test_cold_beats_everything(self, arbitrator):
        ctx = _ctx(
            trip_count=0,
            user_signal_count=0,
            ml_confidence=0.99,
            exploration_budget_remaining=10,
        )
        decision = arbitrator.arbitrate(ctx)
        assert decision.rule_fired == ArbitrationRule.LLM_COLD

    def test_low_signal_beats_exploration(self, arbitrator):
        ctx = _ctx(
            trip_count=2,
            user_signal_count=5,
            ml_confidence=0.99,
            exploration_budget_remaining=10,
        )
        decision = arbitrator.arbitrate(ctx)
        assert decision.rule_fired == ArbitrationRule.LLM_WINS

    def test_exploration_beats_ml_wins(self, arbitrator):
        ml = ["a", "b", "c", "d", "e"]
        llm = ["a", "b", "c", "x", "y"]
        ctx = _ctx(
            trip_count=3,
            user_signal_count=50,
            ml_confidence=0.9,
            ml_rankings=ml,
            llm_rankings=llm,
            exploration_budget_remaining=5,
        )
        decision = arbitrator.arbitrate(ctx)
        assert decision.rule_fired == ArbitrationRule.ML_EXPLORE


# ---------------------------------------------------------------------------
# ArbitrationEvent SQL logging
# ---------------------------------------------------------------------------

class TestArbitrationEventSQL:
    @pytest.mark.asyncio
    async def test_log_calls_execute(self, arbitrator):
        pool = AsyncMock()
        pool.execute = AsyncMock(return_value=None)

        decision = ArbitrationDecision(
            rule_fired=ArbitrationRule.ML_WINS,
            served_rankings=["a", "b", "c"],
            served_source="ml",
            agreement_score=0.6,
        )

        event_id = await arbitrator.log_arbitration_event(
            pool, "user-1", "trip-1", decision
        )

        pool.execute.assert_called_once()
        sql = pool.execute.call_args[0][0]
        assert 'arbitration_events' in sql
        assert '"userId"' in sql
        assert '"tripId"' in sql
        assert '"mlTop3"' in sql
        assert '"llmTop3"' in sql
        assert '"arbitrationRule"' in sql
        assert '"servedSource"' in sql
        assert '"accepted"' in sql
        assert '"agreementScore"' in sql
        assert '"contextSnapshot"' in sql
        assert '"createdAt"' in sql
        assert "$10::jsonb" in sql

    @pytest.mark.asyncio
    async def test_log_passes_correct_values(self, arbitrator):
        pool = AsyncMock()
        pool.execute = AsyncMock(return_value=None)

        ctx = _ctx(ml_confidence=0.8)
        decision = arbitrator.arbitrate(ctx)

        await arbitrator.log_arbitration_event(
            pool, "user-1", "trip-1", decision, context=ctx
        )

        args = pool.execute.call_args[0]
        assert args[2] == "user-1"  # userId
        assert args[3] == "trip-1"  # tripId
        assert args[6] == decision.rule_fired.value  # arbitrationRule
        assert args[7] == decision.served_source  # servedSource
        assert args[8] is None  # accepted (not yet known)
        assert isinstance(args[9], float)  # agreementScore

    @pytest.mark.asyncio
    async def test_log_includes_context_snapshot(self, arbitrator):
        pool = AsyncMock()
        pool.execute = AsyncMock(return_value=None)

        ctx = _ctx(ml_confidence=0.75, persona_vibes=["warm_slow", "dense_late"])
        decision = arbitrator.arbitrate(ctx)

        await arbitrator.log_arbitration_event(
            pool, "user-1", "trip-1", decision, context=ctx
        )

        args = pool.execute.call_args[0]
        snapshot = json.loads(args[10])
        assert snapshot["ml_confidence"] == 0.75
        assert "warm_slow" in snapshot["persona_vibes"]
