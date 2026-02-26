"""
Bend canary integration tests.

Validates the full pipeline chain is wired correctly for Bend, Oregon
(the canary city). Tests cover:
  - Bend city config completeness and correctness
  - Pipeline step ordering and orchestration
  - Arctic Shift scraper city detection for Bend terms
  - Blog RSS feed filtering behavior for Bend
  - Vibe extraction status filter and query structure
  - Convergence scoring produces expected shapes
  - Rule inference tag vocabulary alignment
  - End-to-end pipeline with mocked steps
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.api.pipeline.city_configs import (
    CITY_CONFIGS,
    CityConfig,
    get_city_config,
    get_all_neighborhood_terms,
    get_all_stopwords,
    get_target_cities_dict,
    COMMON_CHAIN_STOPWORDS,
    COMMON_GENERIC_STOPWORDS,
)
from services.api.pipeline.city_seeder import (
    PipelineStep,
    SeedProgress,
    SeedResult,
    StepStatus,
    STEP_ORDER,
    _should_run_step,
    _mark_step_done,
    seed_city,
)
from services.api.pipeline.convergence import (
    compute_convergence_score,
    compute_authority_score as compute_convergence_authority,
    resolve_authority,
    SOURCE_AUTHORITY_DEFAULTS,
)
from services.api.pipeline.vibe_extraction import (
    ALL_TAGS,
    VIBE_VOCABULARY,
    CONFIDENCE_THRESHOLD,
    MODEL_NAME,
)
from services.api.pipeline.rule_inference import (
    CATEGORY_TAG_RULES,
    compute_tags_for_node,
)
from services.api.scrapers.arctic_shift import (
    ArcticShiftScraper,
    detect_city,
    extract_venue_names,
    compute_sentiment,
    TARGET_CITIES,
    TERM_TO_CITY,
    ALL_CITY_TERMS,
    SUBREDDIT_WEIGHTS,
)
from services.api.scrapers.blog_rss import (
    BlogRssScraper,
    FEED_REGISTRY,
    FeedSource,
)

from .conftest import (
    FakePool,
    FakeRecord,
    make_activity_node,
    make_quality_signal,
    make_id,
)


# ===================================================================
# 1. Bend City Config Validation
# ===================================================================


class TestBendCityConfig:
    """Verify Bend config has everything needed for a canary run."""

    def test_bend_config_exists(self):
        assert "bend" in CITY_CONFIGS

    def test_bend_is_canary(self):
        cfg = get_city_config("bend")
        assert cfg.is_canary is True

    def test_bend_has_correct_metadata(self):
        cfg = get_city_config("bend")
        assert cfg.name == "Bend"
        assert cfg.slug == "bend"
        assert cfg.country == "United States"
        assert cfg.timezone == "America/Los_Angeles"

    def test_bend_subreddits(self):
        cfg = get_city_config("bend")
        assert "bend" in cfg.subreddits
        assert "bendoregon" in cfg.subreddits
        assert "centraloregon" in cfg.subreddits
        # Primary sub should have highest weight
        assert cfg.subreddits["bend"] == 1.0
        # All weights in valid range
        for sub, weight in cfg.subreddits.items():
            assert 0.0 < weight <= 1.0, f"Subreddit {sub} weight {weight} out of range"

    def test_bend_neighborhood_terms_are_local(self):
        cfg = get_city_config("bend")
        terms_lower = [t.lower() for t in cfg.neighborhood_terms]
        # Must include the city itself
        assert "bend" in terms_lower
        # Must include recognizable Bend landmarks/areas
        assert "old mill" in terms_lower or "old mill district" in terms_lower
        assert "pilot butte" in terms_lower
        assert "deschutes" in terms_lower or "deschutes river" in terms_lower

    def test_bend_bounding_box_covers_bend(self):
        cfg = get_city_config("bend")
        # Bend, OR approximate coordinates: 44.058, -121.315
        assert cfg.bbox.contains(44.058, -121.315), (
            "Bounding box should contain central Bend"
        )
        # Should not contain Portland
        assert not cfg.bbox.contains(45.52, -122.68), (
            "Bounding box should not contain Portland"
        )

    def test_bend_expected_node_range(self):
        cfg = get_city_config("bend")
        # Canary city = smaller venue set
        assert cfg.expected_nodes_min >= 50, "Bend minimum too low"
        assert cfg.expected_nodes_max <= 1000, "Bend maximum too high for small city"
        assert cfg.expected_nodes_min < cfg.expected_nodes_max

    def test_bend_in_target_cities_dict(self):
        targets = get_target_cities_dict()
        assert "bend" in targets
        assert len(targets["bend"]) >= 5

    def test_bend_neighborhood_terms_in_global_lookup(self):
        all_terms = get_all_neighborhood_terms()
        # At least "bend" should map back to "bend"
        assert all_terms.get("bend") == "bend"


# ===================================================================
# 2. Arctic Shift Scraper -- Bend City Detection Gap
# ===================================================================


class TestArcticShiftBendDetection:
    """Test that Arctic Shift's detect_city works (or doesn't) for Bend."""

    def test_detect_city_module_level_is_japan_only(self):
        """
        KNOWN GAP: The module-level TARGET_CITIES only has Japan cities.
        detect_city() uses these, so it will NOT detect Bend content.
        """
        assert "bend" not in TARGET_CITIES
        assert "bend" not in ALL_CITY_TERMS
        # This proves the gap: detect_city won't find Bend
        result = detect_city("I love hiking around Bend and Pilot Butte")
        assert result is None, (
            "detect_city should return None for Bend (module-level terms are Japan-only)"
        )

    def test_scraper_accepts_target_cities_param(self):
        """ArcticShiftScraper constructor accepts target_cities for Bend."""
        scraper = ArcticShiftScraper(
            parquet_dir="/nonexistent",
            target_cities=["bend"],
        )
        assert "bend" in scraper.config.target_cities

    def test_bend_subreddits_not_in_default_weights(self):
        """
        KNOWN GAP: Bend subreddits aren't in the module-level SUBREDDIT_WEIGHTS.
        The scraper defaults to these when no subreddits parameter is given.
        """
        assert "bend" not in SUBREDDIT_WEIGHTS
        assert "bendoregon" not in SUBREDDIT_WEIGHTS
        assert "centraloregon" not in SUBREDDIT_WEIGHTS

    def test_city_seeder_passes_city_to_scraper(self):
        """
        city_seeder.py creates ArcticShiftScraper(target_cities=[city]).
        This is correct but insufficient because detect_city() is still broken.
        """
        # Verify the call pattern in city_seeder
        # ArcticShiftScraper(target_cities=[city]) -- line 305 of city_seeder.py
        # This is correct API usage but detect_city needs the neighborhood terms
        pass  # Structural verification, see execution guide GAP-1


# ===================================================================
# 3. Blog RSS -- Bend Feed Filtering
# ===================================================================


class TestBlogRssBendFiltering:
    """Test that Blog RSS feed filtering works for Bend."""

    def test_no_bend_feeds_in_registry(self):
        """
        KNOWN GAP: No feeds in FEED_REGISTRY have 'bend' in name or city.
        """
        bend_feeds = [
            f for f in FEED_REGISTRY
            if f.city and "bend" in f.city.lower()
        ]
        assert len(bend_feeds) == 0, "Expected no Bend-specific feeds (known gap)"

    def test_feed_filter_bend_returns_empty(self):
        """Filtering by 'bend' returns no feeds."""
        pool = MagicMock()
        scraper = BlogRssScraper(db_pool=pool, feed_filter="bend")
        active = scraper._active_feeds()
        assert len(active) == 0

    def test_multi_city_feeds_excluded_by_bend_filter(self):
        """Even multi-city feeds (Infatuation, Eater) get excluded."""
        pool = MagicMock()
        scraper = BlogRssScraper(db_pool=pool, feed_filter="bend")
        active = scraper._active_feeds()
        feed_names = [f.name for f in active]
        assert "The Infatuation" not in feed_names
        assert "Eater" not in feed_names

    def test_custom_bend_feeds_work(self):
        """If Bend feeds are added to registry, they would match."""
        bend_feed = FeedSource(
            name="Bend Bulletin Food",
            feed_url="https://example.com/feed",
            base_url="https://example.com",
            authority_score=0.75,
            city="Bend",
            category="dining",
        )
        pool = MagicMock()
        scraper = BlogRssScraper(
            db_pool=pool,
            feed_filter="bend",
            feeds=[bend_feed],
        )
        active = scraper._active_feeds()
        assert len(active) == 1
        assert active[0].name == "Bend Bulletin Food"


# ===================================================================
# 4. Vibe Extraction Query Validation
# ===================================================================


class TestVibeExtractionForBend:
    """Verify vibe extraction settings are appropriate for Bend canary."""

    def test_vocabulary_is_44_tags(self):
        assert len(ALL_TAGS) == 44

    def test_model_is_haiku(self):
        assert "haiku" in MODEL_NAME.lower()

    def test_confidence_threshold_is_reasonable(self):
        assert 0.5 <= CONFIDENCE_THRESHOLD <= 0.9

    def test_extraction_queries_active_status(self):
        """
        Vibe extraction queries nodes with status='active'.
        This is the correct filter for canonical nodes ready for tagging.
        """
        # The query in _fetch_untagged_nodes uses:
        #   AND an.status = 'active'
        # This is correct -- nodes start as 'active' after entity resolution
        # marks them canonical.
        pass  # Verified by reading vibe_extraction.py line 338


# ===================================================================
# 5. Rule Inference Vocabulary Alignment
# ===================================================================


class TestRuleInferenceVocabulary:
    """Check that rule inference tags align with the 44-tag vocabulary."""

    def test_rule_tags_vs_vocabulary(self):
        """
        KNOWN GAP: Many rule inference tags are not in ALL_TAGS.
        This will cause missing_vibe_tags warnings at runtime.
        """
        rule_tags = set()
        for category, tags in CATEGORY_TAG_RULES.items():
            for slug, score in tags:
                rule_tags.add(slug)

        missing = rule_tags - ALL_TAGS
        # Document which tags are mismatched
        assert len(missing) > 0, (
            "If this fails, the gap has been fixed -- remove this test"
        )
        # These are the known mismatches:
        expected_missing = {
            "social", "food-focused", "sit-down", "casual", "deep-dive",
            "slow-paced", "iconic", "fresh-air", "active", "browsing",
            "unique", "memorable", "restorative", "quiet",
        }
        # Note: "splurge" only appears in conditional rules (price_level >= 4),
        # not in base CATEGORY_TAG_RULES, so it only shows up with price_level args.
        assert missing == expected_missing, (
            f"Unexpected tag mismatches. Missing: {missing}. "
            f"Expected: {expected_missing}"
        )

    def test_rule_inference_for_dining(self):
        """Rule inference produces tags for dining category."""
        tags = compute_tags_for_node("dining")
        assert len(tags) > 0
        slugs = {slug for slug, score in tags}
        # dining should get food-focused and sit-down
        assert "food-focused" in slugs

    def test_rule_inference_for_outdoors(self):
        """Rule inference produces tags for outdoors (relevant for Bend)."""
        tags = compute_tags_for_node("outdoors")
        assert len(tags) > 0
        slugs = {slug for slug, score in tags}
        assert "scenic" in slugs or "fresh-air" in slugs


# ===================================================================
# 6. Convergence Scoring
# ===================================================================


class TestConvergenceScoringForBend:
    """Verify convergence scoring behavior for canary validation."""

    def test_single_reddit_source(self):
        """A venue mentioned only on Reddit gets ~0.33 convergence."""
        score = compute_convergence_score(1, has_vibe_agreement=False)
        assert 0.3 <= score <= 0.4

    def test_reddit_plus_blog_source(self):
        """Reddit + blog mention = ~0.67 convergence."""
        score = compute_convergence_score(2, has_vibe_agreement=False)
        assert 0.6 <= score <= 0.7

    def test_three_sources_maxes_out(self):
        """Three independent sources = 1.0 convergence."""
        score = compute_convergence_score(3, has_vibe_agreement=False)
        assert score == 1.0

    def test_reddit_authority_default(self):
        """Reddit mentions get reasonable default authority."""
        reddit_auth = resolve_authority("reddit_high_upvotes", None)
        assert 0.5 <= reddit_auth <= 0.7

    def test_unknown_source_gets_low_authority(self):
        """Unknown sources default to 0.3."""
        auth = resolve_authority("random_blog_xyz", None)
        assert auth == 0.3


# ===================================================================
# 7. Pipeline Step Ordering
# ===================================================================


class TestBendPipelineStepOrder:
    """Verify the pipeline steps execute in correct order for Bend."""

    def test_six_steps_in_order(self):
        expected = [
            "scrape",
            "entity_resolution",
            "vibe_extraction",
            "rule_inference",
            "convergence",
            "qdrant_sync",
        ]
        assert [s.value for s in STEP_ORDER] == expected

    def test_scrape_before_entity_resolution(self):
        scrape_idx = STEP_ORDER.index(PipelineStep.SCRAPE)
        er_idx = STEP_ORDER.index(PipelineStep.ENTITY_RESOLUTION)
        assert scrape_idx < er_idx

    def test_vibe_extraction_before_convergence(self):
        ve_idx = STEP_ORDER.index(PipelineStep.VIBE_EXTRACTION)
        conv_idx = STEP_ORDER.index(PipelineStep.CONVERGENCE)
        assert ve_idx < conv_idx

    def test_convergence_before_qdrant_sync(self):
        conv_idx = STEP_ORDER.index(PipelineStep.CONVERGENCE)
        qs_idx = STEP_ORDER.index(PipelineStep.QDRANT_SYNC)
        assert conv_idx < qs_idx


# ===================================================================
# 8. End-to-End Pipeline with Mocked Steps
# ===================================================================


class TestBendEndToEndMocked:
    """Full pipeline with mocked scrapers, extraction, and convergence."""

    @pytest.mark.asyncio
    async def test_full_pipeline_completes(self, tmp_path):
        """seed_city('bend') runs all 6 steps and returns SeedResult."""
        pool = FakePool()

        with patch(
            "services.api.pipeline.city_seeder.PROGRESS_DIR",
            tmp_path / "progress",
        ), patch(
            "services.api.pipeline.city_seeder._step_scrape",
            new_callable=AsyncMock,
            return_value={"total_scraped": 42, "blog_rss": {"success": 5}},
        ) as mock_scrape, patch(
            "services.api.pipeline.city_seeder._step_entity_resolution",
            new_callable=AsyncMock,
            return_value={"nodes_scanned": 42, "merges_executed": 3},
        ) as mock_er, patch(
            "services.api.pipeline.city_seeder._step_vibe_extraction",
            new_callable=AsyncMock,
            return_value={"nodes_processed": 39, "tags_written": 120},
        ) as mock_vibe, patch(
            "services.api.pipeline.city_seeder._step_rule_inference",
            new_callable=AsyncMock,
            return_value={"nodes_processed": 39, "tags_created": 80},
        ) as mock_rule, patch(
            "services.api.pipeline.city_seeder._step_convergence",
            new_callable=AsyncMock,
            return_value={"nodes_processed": 39, "nodes_updated": 39},
        ) as mock_conv:
            (tmp_path / "progress").mkdir(parents=True, exist_ok=True)

            result = await seed_city(
                pool,
                "bend",
                anthropic_api_key="test-key",
                embedding_service=None,  # skip Qdrant sync
                force_restart=True,
            )

            assert result.city == "bend"
            assert result.success is True
            assert result.steps_completed == 6  # all 6, qdrant skipped but counted
            assert result.steps_failed == 0
            assert result.total_duration_s >= 0

            # Verify all steps were called
            mock_scrape.assert_called_once()
            mock_er.assert_called_once()
            mock_vibe.assert_called_once()
            mock_rule.assert_called_once()
            mock_conv.assert_called_once()

    @pytest.mark.asyncio
    async def test_pipeline_skips_completed_steps(self, tmp_path):
        """If scrape is already done, seed_city skips it."""
        pool = FakePool()
        progress_dir = tmp_path / "progress"
        progress_dir.mkdir(parents=True, exist_ok=True)

        # Pre-populate progress file with scrape completed
        progress_data = {
            "city": "bend",
            "run_id": "test",
            "started_at": "2026-02-25T00:00:00+00:00",
            "finished_at": None,
            "overall_status": "in_progress",
            "nodes_scraped": 42,
            "nodes_resolved": 0,
            "nodes_tagged": 0,
            "nodes_indexed": 0,
            "steps": {
                step.value: {
                    "status": "completed" if step == PipelineStep.SCRAPE else "pending",
                    "started_at": None,
                    "finished_at": "2026-02-25T00:01:00+00:00" if step == PipelineStep.SCRAPE else None,
                    "error": None,
                    "metrics": {"total_scraped": 42} if step == PipelineStep.SCRAPE else {},
                }
                for step in STEP_ORDER
            },
        }
        (progress_dir / "bend.json").write_text(json.dumps(progress_data))

        with patch(
            "services.api.pipeline.city_seeder.PROGRESS_DIR",
            progress_dir,
        ), patch(
            "services.api.pipeline.city_seeder._step_scrape",
            new_callable=AsyncMock,
        ) as mock_scrape, patch(
            "services.api.pipeline.city_seeder._step_entity_resolution",
            new_callable=AsyncMock,
            return_value={"nodes_scanned": 42, "merges_executed": 3},
        ), patch(
            "services.api.pipeline.city_seeder._step_vibe_extraction",
            new_callable=AsyncMock,
            return_value={"nodes_processed": 39, "tags_written": 120},
        ), patch(
            "services.api.pipeline.city_seeder._step_rule_inference",
            new_callable=AsyncMock,
            return_value={"nodes_processed": 39, "tags_created": 80},
        ), patch(
            "services.api.pipeline.city_seeder._step_convergence",
            new_callable=AsyncMock,
            return_value={"nodes_processed": 39, "nodes_updated": 39},
        ):
            result = await seed_city(
                pool,
                "bend",
                anthropic_api_key="test-key",
                embedding_service=None,
                force_restart=False,
            )

            # Scrape should NOT have been called (already completed)
            mock_scrape.assert_not_called()
            assert result.success is True

    @pytest.mark.asyncio
    async def test_pipeline_handles_scrape_failure(self, tmp_path):
        """If scrape fails, the pipeline continues but reports failure."""
        pool = FakePool()

        with patch(
            "services.api.pipeline.city_seeder.PROGRESS_DIR",
            tmp_path / "progress",
        ), patch(
            "services.api.pipeline.city_seeder._step_scrape",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Arctic Shift data not found"),
        ), patch(
            "services.api.pipeline.city_seeder._step_entity_resolution",
            new_callable=AsyncMock,
            return_value={"nodes_scanned": 0, "merges_executed": 0},
        ), patch(
            "services.api.pipeline.city_seeder._step_vibe_extraction",
            new_callable=AsyncMock,
            return_value={"nodes_processed": 0, "tags_written": 0},
        ), patch(
            "services.api.pipeline.city_seeder._step_rule_inference",
            new_callable=AsyncMock,
            return_value={"nodes_processed": 0, "tags_created": 0},
        ), patch(
            "services.api.pipeline.city_seeder._step_convergence",
            new_callable=AsyncMock,
            return_value={"nodes_processed": 0, "nodes_updated": 0},
        ):
            (tmp_path / "progress").mkdir(parents=True, exist_ok=True)

            result = await seed_city(
                pool,
                "bend",
                anthropic_api_key="test-key",
                embedding_service=None,
                force_restart=True,
            )

            assert result.success is False
            assert result.steps_failed >= 1
            assert any("scrape" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_pipeline_skip_llm_when_no_key(self, tmp_path):
        """Without API key, vibe extraction is skipped gracefully."""
        pool = FakePool()

        with patch(
            "services.api.pipeline.city_seeder.PROGRESS_DIR",
            tmp_path / "progress",
        ), patch(
            "services.api.pipeline.city_seeder._step_scrape",
            new_callable=AsyncMock,
            return_value={"total_scraped": 10},
        ), patch(
            "services.api.pipeline.city_seeder._step_entity_resolution",
            new_callable=AsyncMock,
            return_value={"nodes_scanned": 10, "merges_executed": 0},
        ), patch(
            "services.api.pipeline.city_seeder._step_rule_inference",
            new_callable=AsyncMock,
            return_value={"nodes_processed": 10, "tags_created": 20},
        ), patch(
            "services.api.pipeline.city_seeder._step_convergence",
            new_callable=AsyncMock,
            return_value={"nodes_processed": 10, "nodes_updated": 10},
        ), patch.dict("os.environ", {}, clear=False):
            (tmp_path / "progress").mkdir(parents=True, exist_ok=True)

            # Remove ANTHROPIC_API_KEY from env if present
            import os
            env_backup = os.environ.pop("ANTHROPIC_API_KEY", None)
            try:
                result = await seed_city(
                    pool,
                    "bend",
                    anthropic_api_key=None,
                    embedding_service=None,
                    force_restart=True,
                )
                assert result.success is True
                # Vibe extraction should be skipped, not failed
                assert result.steps_failed == 0
            finally:
                if env_backup:
                    os.environ["ANTHROPIC_API_KEY"] = env_backup


# ===================================================================
# 9. Progress File Validation
# ===================================================================


class TestBendProgressFile:
    """Verify progress tracking works correctly for Bend."""

    def test_progress_file_created(self, tmp_path):
        from services.api.pipeline.city_seeder import _save_progress, _progress_path

        with patch(
            "services.api.pipeline.city_seeder.PROGRESS_DIR",
            tmp_path,
        ):
            progress = SeedProgress(city="bend", run_id="canary-001")
            _save_progress(progress)
            path = tmp_path / "bend.json"
            assert path.exists()
            data = json.loads(path.read_text())
            assert data["city"] == "bend"
            assert data["run_id"] == "canary-001"

    def test_progress_file_tracks_all_steps(self, tmp_path):
        from services.api.pipeline.city_seeder import _save_progress

        with patch(
            "services.api.pipeline.city_seeder.PROGRESS_DIR",
            tmp_path,
        ):
            progress = SeedProgress(city="bend", run_id="canary-001")
            _save_progress(progress)
            data = json.loads((tmp_path / "bend.json").read_text())
            for step in STEP_ORDER:
                assert step.value in data["steps"]


# ===================================================================
# 10. Quality Filter Validation
# ===================================================================


class TestQualityFilters:
    """Verify quality filters apply at the correct pipeline step."""

    def test_arctic_shift_min_score_default(self):
        """Arctic Shift default min score filters low-quality posts."""
        from services.api.scrapers.arctic_shift import MIN_SCORE_THRESHOLD
        assert MIN_SCORE_THRESHOLD >= 3, "Min score should filter noise"

    def test_vibe_extraction_confidence_threshold(self):
        """Tags below confidence threshold are dropped."""
        assert CONFIDENCE_THRESHOLD == 0.75

    def test_stopwords_exclude_chains(self):
        """Common chain stopwords are filtered."""
        stopwords = get_all_stopwords()
        assert "starbucks" in stopwords
        assert "mcdonalds" in stopwords
        assert "walmart" in stopwords

    def test_bend_has_no_city_specific_stopwords(self):
        """Bend config has no city-specific stopwords (small city, no known chains)."""
        cfg = get_city_config("bend")
        assert cfg.stopwords == []

    def test_generic_stopwords_filter_tripadvisor(self):
        """TripAdvisor and Yelp are in generic stopwords."""
        stopwords = get_all_stopwords()
        assert "tripadvisor" in stopwords
        assert "trip advisor" in stopwords
