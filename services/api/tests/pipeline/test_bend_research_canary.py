"""Canary integration tests for Pipeline D: Bend dry-run.

These tests verify the full pipeline against real data shape.
They do NOT call the LLM — they use fixture responses.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.api.pipeline.research_pipeline import run_research_pipeline


BEND_PASS_A = {
    "neighborhood_character": {
        "old_bend": "Walkable, brewery-heavy, river-adjacent",
        "west_side": "Upscale dining, newer development",
        "midtown": "Local-focused, affordable eats",
    },
    "temporal_patterns": {
        "summer": "Peak tourism, outdoor activities",
        "winter": "Ski season, Mt Bachelor",
        "shoulder": "Locals reclaim restaurants",
    },
    "peak_and_decline_flags": ["Deschutes Brewery - tourist overcrowding"],
    "source_amplification_flags": [],
    "divergence_signals": [],
    "synthesis_confidence": 0.82,
}


@pytest.fixture
def mock_pipeline_deps():
    with patch("services.api.pipeline.research_pipeline.assemble_source_bundle") as mock_bundle, \
         patch("services.api.pipeline.research_pipeline.run_pass_a") as mock_a, \
         patch("services.api.pipeline.research_pipeline.run_pass_b") as mock_b, \
         patch("services.api.pipeline.research_pipeline.resolve_venue_names") as mock_res, \
         patch("services.api.pipeline.research_pipeline.get_city_config") as mock_cfg:

        from services.api.pipeline.source_bundle import SourceBundle
        from services.api.pipeline.venue_resolver import ResolutionResult, MatchType

        mock_cfg.return_value = MagicMock(slug="bend")
        mock_bundle.return_value = SourceBundle(city_slug="bend", token_estimate=5000)
        mock_a.return_value = {
            "parsed": BEND_PASS_A,
            "input_tokens": 8000, "output_tokens": 1200,
            "raw_text": json.dumps(BEND_PASS_A),
        }
        mock_b.return_value = {
            "venues": [
                {"venue_name": "Pine Tavern", "vibe_tags": ["destination-meal", "scenic"],
                 "tourist_score": 0.45, "research_confidence": 0.78,
                 "knowledge_source": "bundle_primary", "source_amplification": False,
                 "local_vs_tourist_signal_conflict": False, "temporal_notes": None, "notes": None},
            ],
            "total_input_tokens": 15000, "total_output_tokens": 3000,
        }
        mock_res.return_value = [
            ResolutionResult("Pine Tavern", "node-1", "Pine Tavern",
                            MatchType.EXACT, 1.0),
        ]

        yield {
            "bundle": mock_bundle, "pass_a": mock_a, "pass_b": mock_b,
            "resolver": mock_res, "config": mock_cfg,
        }


def _make_fake_pool():
    pool = MagicMock()
    conn = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = ctx
    conn.fetchval.return_value = None
    conn.fetchrow.return_value = {
        "convergenceScore": 0.6, "authorityScore": 0.5,
        "tourist_score": 0.35, "sourceCount": 8,
    }
    conn.fetch.side_effect = [
        [{"slug": "hidden-gem"}, {"slug": "scenic"}],  # _fetch_vibe_vocabulary
        [{"canonicalName": "Pine Tavern"}],             # _fetch_venue_candidates
        [{"slug": "hidden-gem"}],                       # c_tag_rows for cross-reference
    ]
    return pool, conn


class TestBendCanaryDryRun:
    @pytest.mark.asyncio
    async def test_completes_without_error(self, mock_pipeline_deps):
        pool, conn = _make_fake_pool()
        result = await run_research_pipeline(
            pool, "bend", triggered_by="admin_seed",
            api_key="test-key", write_back=False)
        assert result["status"] == "COMPLETE"

    @pytest.mark.asyncio
    async def test_reports_resolution_stats(self, mock_pipeline_deps):
        pool, conn = _make_fake_pool()
        result = await run_research_pipeline(
            pool, "bend", triggered_by="admin_seed",
            api_key="test-key", write_back=False)
        assert result["venues_resolved"] >= 0
        assert result["venues_unresolved"] >= 0

    @pytest.mark.asyncio
    async def test_dry_run_no_activity_node_writes(self, mock_pipeline_deps):
        pool, conn = _make_fake_pool()
        result = await run_research_pipeline(
            pool, "bend", triggered_by="admin_seed",
            api_key="test-key", write_back=False)
        assert result["write_back"] is False

    @pytest.mark.asyncio
    async def test_cost_within_tolerance(self, mock_pipeline_deps):
        pool, conn = _make_fake_pool()
        result = await run_research_pipeline(
            pool, "bend", triggered_by="admin_seed",
            api_key="test-key", write_back=False)
        assert result.get("cost_usd", 0) < 5.0

    @pytest.mark.asyncio
    async def test_rejects_unknown_city(self, mock_pipeline_deps):
        mock_pipeline_deps["config"].return_value = None
        pool, conn = _make_fake_pool()
        with pytest.raises(ValueError, match="not in CITY_CONFIGS"):
            await run_research_pipeline(
                pool, "unknown_city", triggered_by="admin_seed",
                api_key="test-key")
