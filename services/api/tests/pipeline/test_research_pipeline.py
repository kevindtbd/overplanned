"""Tests for Pipeline D orchestrator."""
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from services.api.pipeline.research_pipeline import (
    run_research_pipeline,
    check_cost_budget,
    check_city_cooldown,
    check_circuit_breaker,
    should_flag_delta,
    MAX_DAILY_COST_USD,
    CITY_COOLDOWN_HOURS,
    CIRCUIT_BREAKER_THRESHOLD,
    DELTA_THRESHOLD,
)


def _make_fake_pool():
    pool = MagicMock()
    conn = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = ctx
    return pool, conn


class TestCostBudget:
    @pytest.mark.asyncio
    async def test_allows_under_budget(self):
        pool, conn = _make_fake_pool()
        conn.fetchval.return_value = 10.0
        allowed = await check_cost_budget(pool)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_blocks_over_budget(self):
        pool, conn = _make_fake_pool()
        conn.fetchval.return_value = 26.0
        allowed = await check_cost_budget(pool)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_handles_null_sum(self):
        pool, conn = _make_fake_pool()
        conn.fetchval.return_value = None
        allowed = await check_cost_budget(pool)
        assert allowed is True


class TestCityCooldown:
    @pytest.mark.asyncio
    async def test_allows_after_cooldown(self):
        pool, conn = _make_fake_pool()
        conn.fetchval.return_value = None
        allowed = await check_city_cooldown(pool, "bend")
        assert allowed is True

    @pytest.mark.asyncio
    async def test_blocks_within_cooldown(self):
        pool, conn = _make_fake_pool()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        conn.fetchval.return_value = now
        allowed = await check_city_cooldown(pool, "bend")
        assert allowed is False


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_allows_after_success(self):
        pool, conn = _make_fake_pool()
        conn.fetchval.return_value = 0
        allowed = await check_circuit_breaker(pool)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_blocks_after_3_failures(self):
        pool, conn = _make_fake_pool()
        conn.fetchval.return_value = 3
        allowed = await check_circuit_breaker(pool)
        assert allowed is False


class TestDryRunPipeline:
    @pytest.mark.asyncio
    async def test_dry_run_skips_activity_node_update(self):
        pool, conn = _make_fake_pool()
        with patch("services.api.pipeline.research_pipeline.assemble_source_bundle") as mock_bundle, \
             patch("services.api.pipeline.research_pipeline.run_pass_a") as mock_a, \
             patch("services.api.pipeline.research_pipeline.run_pass_b") as mock_b, \
             patch("services.api.pipeline.research_pipeline.validate_full") as mock_val, \
             patch("services.api.pipeline.research_pipeline.resolve_venue_names") as mock_res, \
             patch("services.api.pipeline.research_pipeline.get_city_config") as mock_cfg:

            from services.api.pipeline.source_bundle import SourceBundle
            from services.api.pipeline.research_validator import ValidationResult

            mock_cfg.return_value = MagicMock(slug="bend")
            mock_bundle.return_value = SourceBundle(city_slug="bend", token_estimate=100)
            mock_a.return_value = {
                "parsed": {"synthesis_confidence": 0.8, "neighborhood_character": {},
                           "temporal_patterns": {}, "peak_and_decline_flags": [],
                           "source_amplification_flags": [], "divergence_signals": []},
                "input_tokens": 100, "output_tokens": 50, "raw_text": "{}",
            }
            mock_b.return_value = {"venues": [], "total_input_tokens": 0, "total_output_tokens": 0}
            mock_val.return_value = ValidationResult(passed=True)
            mock_res.return_value = []

            conn.fetchval.return_value = None
            conn.fetchrow.return_value = None
            conn.fetch.return_value = []

            result = await run_research_pipeline(
                pool, "bend", triggered_by="admin_seed",
                api_key="test-key", write_back=False)

            assert result["status"] == "COMPLETE"
            update_calls = [c for c in conn.execute.call_args_list
                           if c and "activity_nodes" in str(c).lower()
                           and "UPDATE" in str(c).upper()]
            assert len(update_calls) == 0


class TestDeltaThreshold:
    def test_flags_large_score_shift(self):
        assert should_flag_delta(c_confidence=0.3, d_confidence=0.8) is True

    def test_allows_small_shift(self):
        assert should_flag_delta(c_confidence=0.5, d_confidence=0.6) is False
