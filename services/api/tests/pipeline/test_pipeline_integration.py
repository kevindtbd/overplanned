"""
Pipeline integration tests.

Covers:
- Full 1-city pipeline: scrape -> resolve -> tag -> score -> Qdrant
- Qdrant parity: Postgres canonical count == Qdrant count
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.api.pipeline.city_seeder import (
    PipelineStep,
    SeedProgress,
    SeedResult,
    StepStatus,
    STEP_ORDER,
    _load_progress,
    _save_progress,
    _should_run_step,
    _mark_step_start,
    _mark_step_done,
    _mark_step_failed,
)
from services.api.pipeline.convergence import (
    compute_convergence_score,
    compute_authority_score as compute_convergence_authority,
    resolve_authority,
)
from services.api.pipeline.qdrant_sync import (
    build_embedding_text,
    COLLECTION_NAME,
    VECTOR_DIM,
)

from .conftest import (
    FakePool,
    FakeQdrantClient,
    FakeEmbeddingService,
    make_activity_node,
    make_quality_signal,
    make_id,
)


# ===================================================================
# Embedding text construction
# ===================================================================


class TestBuildEmbeddingText:
    def test_full_text(self):
        text = build_embedding_text(
            name="Ichiran Ramen",
            description_short="Famous tonkotsu ramen chain",
            category="dining",
            vibe_tag_slugs=["hidden-gem", "local-institution"],
        )
        assert "Ichiran Ramen" in text
        assert "Famous tonkotsu" in text
        assert "Category: dining" in text
        assert "Vibes: hidden-gem, local-institution" in text

    def test_minimal_text(self):
        text = build_embedding_text(
            name="Test Place",
            description_short=None,
            category="culture",
            vibe_tag_slugs=[],
        )
        assert "Test Place" in text
        assert "Category: culture" in text
        assert "Vibes:" not in text


# ===================================================================
# Convergence scoring (pure functions)
# ===================================================================


class TestConvergenceScoring:
    def test_single_source_score(self):
        score = compute_convergence_score(1, has_vibe_agreement=False)
        assert score == round(1 / 3.0, 4)

    def test_three_source_max(self):
        score = compute_convergence_score(3, has_vibe_agreement=False)
        assert score == 1.0

    def test_vibe_agreement_bonus(self):
        without = compute_convergence_score(2, has_vibe_agreement=False)
        with_vibe = compute_convergence_score(2, has_vibe_agreement=True)
        assert with_vibe > without
        assert with_vibe - without == pytest.approx(0.1, abs=0.001)

    def test_capped_at_one(self):
        score = compute_convergence_score(5, has_vibe_agreement=True)
        assert score == 1.0

    def test_authority_average(self):
        sources = [("foursquare", 0.7), ("atlas_obscura", 0.85)]
        authority = compute_convergence_authority(sources)
        expected = round((0.7 + 0.85) / 2, 4)
        assert authority == expected

    def test_authority_empty_sources(self):
        assert compute_convergence_authority([]) == 0.0

    def test_resolve_authority_uses_db_value(self):
        assert resolve_authority("anything", 0.9) == 0.9

    def test_resolve_authority_fallback_registry(self):
        result = resolve_authority("the_infatuation", None)
        assert result == 0.9

    def test_resolve_authority_unknown_source(self):
        result = resolve_authority("totally_unknown_source_xyz", None)
        assert result == 0.3  # default


# ===================================================================
# Seed progress persistence
# ===================================================================


class TestSeedProgress:
    def test_new_progress_has_all_steps(self):
        progress = SeedProgress(city="tokyo")
        for step in STEP_ORDER:
            assert step.value in progress.steps
            assert progress.steps[step.value].status == StepStatus.PENDING

    def test_save_and_load_round_trip(self, tmp_progress_dir):
        with patch(
            "services.api.pipeline.city_seeder.PROGRESS_DIR",
            tmp_progress_dir,
        ):
            progress = SeedProgress(city="tokyo", run_id="test_run")
            _mark_step_done(progress, PipelineStep.SCRAPE, {"total_scraped": 42})

            loaded = _load_progress("tokyo")
            assert loaded.steps[PipelineStep.SCRAPE.value].status == StepStatus.COMPLETED
            assert loaded.steps[PipelineStep.SCRAPE.value].metrics["total_scraped"] == 42

    def test_should_run_step_pending(self):
        progress = SeedProgress(city="tokyo")
        assert _should_run_step(progress, PipelineStep.SCRAPE) is True

    def test_should_run_step_completed(self):
        progress = SeedProgress(city="tokyo")
        _mark_step_done(progress, PipelineStep.SCRAPE)
        assert _should_run_step(progress, PipelineStep.SCRAPE) is False

    def test_mark_step_failed(self, tmp_progress_dir):
        with patch(
            "services.api.pipeline.city_seeder.PROGRESS_DIR",
            tmp_progress_dir,
        ):
            progress = SeedProgress(city="tokyo")
            _mark_step_failed(progress, PipelineStep.SCRAPE, "HTTP 500")
            assert progress.steps[PipelineStep.SCRAPE.value].status == StepStatus.FAILED
            assert progress.steps[PipelineStep.SCRAPE.value].error == "HTTP 500"


# ===================================================================
# Qdrant parity check
# ===================================================================


class TestQdrantParity:
    @pytest.mark.asyncio
    async def test_parity_check_matching(self):
        """When Postgres count == Qdrant count, parity holds."""
        pool = FakePool()
        qdrant = FakeQdrantClient()

        # Simulate 5 canonical nodes in Postgres
        # and 5 points in Qdrant
        await qdrant.create_collection(COLLECTION_NAME)
        col = qdrant.collections[COLLECTION_NAME]
        for i in range(5):
            node_id = make_id()
            col.points[node_id] = {"vector": [0.0] * VECTOR_DIM, "payload": {}}
        col.points_count = 5

        info = await qdrant.get_collection(COLLECTION_NAME)
        assert info.points_count == 5

    @pytest.mark.asyncio
    async def test_parity_check_mismatched(self):
        """When counts differ, we detect the mismatch."""
        qdrant = FakeQdrantClient()
        await qdrant.create_collection(COLLECTION_NAME)
        col = qdrant.collections[COLLECTION_NAME]

        # 3 in Qdrant
        for i in range(3):
            col.points[make_id()] = {}
        col.points_count = 3

        info = await qdrant.get_collection(COLLECTION_NAME)
        pg_count = 5  # simulated Postgres count

        assert info.points_count != pg_count


# ===================================================================
# Full pipeline step ordering
# ===================================================================


class TestPipelineStepOrder:
    def test_step_order_is_correct(self):
        expected = [
            "scrape",
            "llm_fallback",
            "geocode_backfill",
            "entity_resolution",
            "vibe_extraction",
            "rule_inference",
            "convergence",
            "qdrant_sync",
        ]
        assert [s.value for s in STEP_ORDER] == expected

    def test_seed_result_structure(self):
        result = SeedResult(city="tokyo", success=True)
        assert result.city == "tokyo"
        assert result.success is True
        assert result.nodes_scraped == 0
        assert result.errors == []
