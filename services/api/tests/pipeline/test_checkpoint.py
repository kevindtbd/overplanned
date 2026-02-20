"""
Checkpoint/resume tests.

Covers:
- Simulate crash mid-pipeline -> restart -> verify resumes from correct step
- Progress file persistence and loading
- Step state transitions
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from services.api.pipeline.city_seeder import (
    PipelineStep,
    SeedProgress,
    StepStatus,
    StepProgress,
    STEP_ORDER,
    _load_progress,
    _save_progress,
    _should_run_step,
    _mark_step_start,
    _mark_step_done,
    _mark_step_failed,
    _progress_path,
)


class TestCheckpointResume:
    """Test that pipeline resumes from the correct step after a crash."""

    def test_resume_after_scrape_completed(self, tmp_progress_dir):
        """If scrape completed but entity_resolution didn't, resume from entity_resolution."""
        with patch(
            "services.api.pipeline.city_seeder.PROGRESS_DIR",
            tmp_progress_dir,
        ):
            # Simulate: scrape completed, then "crash"
            progress = SeedProgress(city="tokyo", run_id="run1")
            _mark_step_done(progress, PipelineStep.SCRAPE, {"total_scraped": 100})

            # Reload (as if new process)
            loaded = _load_progress("tokyo")

            # Scrape should not re-run
            assert _should_run_step(loaded, PipelineStep.SCRAPE) is False
            # Entity resolution should run
            assert _should_run_step(loaded, PipelineStep.ENTITY_RESOLUTION) is True
            # All subsequent steps should run
            assert _should_run_step(loaded, PipelineStep.VIBE_EXTRACTION) is True
            assert _should_run_step(loaded, PipelineStep.CONVERGENCE) is True
            assert _should_run_step(loaded, PipelineStep.QDRANT_SYNC) is True

    def test_resume_after_mid_pipeline_crash(self, tmp_progress_dir):
        """If scrape + entity_resolution + vibe completed, resume from rule_inference."""
        with patch(
            "services.api.pipeline.city_seeder.PROGRESS_DIR",
            tmp_progress_dir,
        ):
            progress = SeedProgress(city="kyoto", run_id="run2")
            _mark_step_done(progress, PipelineStep.SCRAPE, {"total_scraped": 50})
            _mark_step_done(progress, PipelineStep.ENTITY_RESOLUTION, {"merges": 3})
            _mark_step_done(progress, PipelineStep.VIBE_EXTRACTION, {"tags_written": 20})

            loaded = _load_progress("kyoto")

            assert _should_run_step(loaded, PipelineStep.SCRAPE) is False
            assert _should_run_step(loaded, PipelineStep.ENTITY_RESOLUTION) is False
            assert _should_run_step(loaded, PipelineStep.VIBE_EXTRACTION) is False
            assert _should_run_step(loaded, PipelineStep.RULE_INFERENCE) is True
            assert _should_run_step(loaded, PipelineStep.CONVERGENCE) is True

    def test_resume_after_all_completed(self, tmp_progress_dir):
        """If everything completed, nothing should re-run."""
        with patch(
            "services.api.pipeline.city_seeder.PROGRESS_DIR",
            tmp_progress_dir,
        ):
            progress = SeedProgress(city="osaka", run_id="run3")
            for step in STEP_ORDER:
                _mark_step_done(progress, step)

            loaded = _load_progress("osaka")
            for step in STEP_ORDER:
                assert _should_run_step(loaded, step) is False

    def test_failed_step_should_re_run(self, tmp_progress_dir):
        """A failed step should be re-run on resume."""
        with patch(
            "services.api.pipeline.city_seeder.PROGRESS_DIR",
            tmp_progress_dir,
        ):
            progress = SeedProgress(city="tokyo", run_id="run4")
            _mark_step_done(progress, PipelineStep.SCRAPE)
            _mark_step_failed(progress, PipelineStep.ENTITY_RESOLUTION, "DB connection lost")

            loaded = _load_progress("tokyo")
            assert _should_run_step(loaded, PipelineStep.SCRAPE) is False
            assert _should_run_step(loaded, PipelineStep.ENTITY_RESOLUTION) is True

    def test_in_progress_step_should_re_run(self, tmp_progress_dir):
        """An in_progress step (crash during execution) should be re-run."""
        with patch(
            "services.api.pipeline.city_seeder.PROGRESS_DIR",
            tmp_progress_dir,
        ):
            progress = SeedProgress(city="tokyo", run_id="run5")
            _mark_step_done(progress, PipelineStep.SCRAPE)
            _mark_step_start(progress, PipelineStep.ENTITY_RESOLUTION)
            # "crash" here — step left as in_progress

            loaded = _load_progress("tokyo")
            assert _should_run_step(loaded, PipelineStep.SCRAPE) is False
            assert _should_run_step(loaded, PipelineStep.ENTITY_RESOLUTION) is True


class TestProgressPersistence:
    """Test progress file JSON serialization."""

    def test_progress_path_generation(self, tmp_progress_dir):
        with patch(
            "services.api.pipeline.city_seeder.PROGRESS_DIR",
            tmp_progress_dir,
        ):
            path = _progress_path("tokyo")
            assert path.name == "tokyo.json"
            assert path.parent == tmp_progress_dir

    def test_progress_path_normalizes_spaces(self, tmp_progress_dir):
        with patch(
            "services.api.pipeline.city_seeder.PROGRESS_DIR",
            tmp_progress_dir,
        ):
            path = _progress_path("New York")
            assert path.name == "new_york.json"

    def test_load_nonexistent_returns_fresh(self, tmp_progress_dir):
        with patch(
            "services.api.pipeline.city_seeder.PROGRESS_DIR",
            tmp_progress_dir,
        ):
            progress = _load_progress("nonexistent_city")
            assert progress.city == "nonexistent_city"
            assert progress.overall_status == StepStatus.PENDING

    def test_corrupt_file_returns_fresh(self, tmp_progress_dir):
        with patch(
            "services.api.pipeline.city_seeder.PROGRESS_DIR",
            tmp_progress_dir,
        ):
            # Write corrupt JSON
            path = _progress_path("corrupt_city")
            path.write_text("{bad json!!!}")

            progress = _load_progress("corrupt_city")
            assert progress.overall_status == StepStatus.PENDING

    def test_metrics_preserved_across_save_load(self, tmp_progress_dir):
        with patch(
            "services.api.pipeline.city_seeder.PROGRESS_DIR",
            tmp_progress_dir,
        ):
            progress = SeedProgress(city="tokyo", run_id="metricstest")
            progress.nodes_scraped = 42
            progress.nodes_resolved = 5
            _mark_step_done(progress, PipelineStep.SCRAPE, {
                "blog_rss": {"success": 10},
                "foursquare": {"success": 32},
            })

            loaded = _load_progress("tokyo")
            assert loaded.nodes_scraped == 42
            assert loaded.nodes_resolved == 5
            metrics = loaded.steps[PipelineStep.SCRAPE.value].metrics
            assert metrics["blog_rss"]["success"] == 10


class TestStepTransitions:
    """Test step status state machine."""

    def test_pending_to_in_progress(self, tmp_progress_dir):
        with patch(
            "services.api.pipeline.city_seeder.PROGRESS_DIR",
            tmp_progress_dir,
        ):
            progress = SeedProgress(city="tokyo")
            _mark_step_start(progress, PipelineStep.SCRAPE)
            assert progress.steps[PipelineStep.SCRAPE.value].status == StepStatus.IN_PROGRESS
            assert progress.steps[PipelineStep.SCRAPE.value].started_at is not None

    def test_in_progress_to_completed(self, tmp_progress_dir):
        with patch(
            "services.api.pipeline.city_seeder.PROGRESS_DIR",
            tmp_progress_dir,
        ):
            progress = SeedProgress(city="tokyo")
            _mark_step_start(progress, PipelineStep.SCRAPE)
            _mark_step_done(progress, PipelineStep.SCRAPE, {"count": 10})

            step = progress.steps[PipelineStep.SCRAPE.value]
            assert step.status == StepStatus.COMPLETED
            assert step.finished_at is not None
            assert step.metrics["count"] == 10

    def test_in_progress_to_failed(self, tmp_progress_dir):
        with patch(
            "services.api.pipeline.city_seeder.PROGRESS_DIR",
            tmp_progress_dir,
        ):
            progress = SeedProgress(city="tokyo")
            _mark_step_start(progress, PipelineStep.SCRAPE)
            _mark_step_failed(progress, PipelineStep.SCRAPE, "timeout")

            step = progress.steps[PipelineStep.SCRAPE.value]
            assert step.status == StepStatus.FAILED
            assert step.error == "timeout"
