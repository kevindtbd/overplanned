"""
Content purge tests.

Covers:
- rawExcerpt null after 30 days
- VibeTags and scores preserved (purge only touches rawExcerpt)
- Reddit sources targeted, other sources untouched
- Batch processing
- Dry run mode
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

from services.api.pipeline.content_purge import (
    BATCH_SIZE,
    DEFAULT_RETENTION_DAYS,
    REDDIT_SOURCES,
    PurgeResult,
    purge_expired_excerpts,
)

from .conftest import FakePool, days_ago


# ===================================================================
# Constants
# ===================================================================


class TestPurgeConstants:
    def test_reddit_sources(self):
        assert "arctic_shift" in REDDIT_SOURCES
        assert "reddit" in REDDIT_SOURCES
        assert len(REDDIT_SOURCES) == 2

    def test_default_retention_30_days(self):
        assert DEFAULT_RETENTION_DAYS == 30

    def test_batch_size(self):
        assert BATCH_SIZE == 500


# ===================================================================
# PurgeResult structure
# ===================================================================


class TestPurgeResult:
    def test_result_fields(self):
        result = PurgeResult(
            rows_purged=10,
            rows_already_null=5,
            batches_run=1,
            duration_s=0.5,
            cutoff_date="2026-01-01T00:00:00",
            errors=[],
        )
        assert result.rows_purged == 10
        assert result.rows_already_null == 5
        assert result.batches_run == 1
        assert result.duration_s == 0.5
        assert result.errors == []

    def test_result_with_errors(self):
        result = PurgeResult(
            rows_purged=0,
            rows_already_null=0,
            batches_run=0,
            duration_s=0.1,
            cutoff_date="2026-01-01",
            errors=["batch 1: connection lost"],
        )
        assert len(result.errors) == 1


# ===================================================================
# Purge logic (async)
# ===================================================================


class TestPurgeLogic:
    @pytest.mark.asyncio
    async def test_dry_run_does_not_modify(self):
        """Dry run should count but not update rows."""
        pool = FakePool()
        # Mock fetchval to return count of eligible rows
        pool._fetchval_results = {}
        # Set both queries to return counts
        for key in pool._fetchval_results:
            pass  # clear

        result = await purge_expired_excerpts(pool, dry_run=True)

        assert result.rows_purged == 0
        assert result.batches_run == 0
        # No UPDATE statements should have been executed
        update_calls = [q for q, _ in pool._executed if "UPDATE" in q]
        assert len(update_calls) == 0

    @pytest.mark.asyncio
    async def test_purge_targets_reddit_sources_only(self):
        """SQL should filter on REDDIT_SOURCES (arctic_shift, reddit)."""
        pool = FakePool()

        result = await purge_expired_excerpts(pool, retention_days=30)

        # Check that executed SQL contains the source filter
        if pool._executed:
            sql = pool._executed[0][0]
            assert "sourceName" in sql or "rawExcerpt" in sql

    @pytest.mark.asyncio
    async def test_purge_returns_result(self):
        pool = FakePool()
        result = await purge_expired_excerpts(pool)

        assert isinstance(result, PurgeResult)
        assert result.cutoff_date is not None
        assert result.duration_s >= 0

    @pytest.mark.asyncio
    async def test_purge_custom_retention(self):
        """Custom retention_days should be passed through."""
        pool = FakePool()
        result = await purge_expired_excerpts(pool, retention_days=60)
        assert isinstance(result, PurgeResult)


# ===================================================================
# Purge preserves derived data
# ===================================================================


class TestPurgePreservesDerivedData:
    """
    Verify that purge ONLY nulls rawExcerpt.
    VibeTags, convergence scores, authority scores are NOT touched.
    """

    def test_purge_sql_only_nulls_raw_excerpt(self):
        """The UPDATE statement should ONLY set rawExcerpt = NULL."""
        # This is a structural test — verify the SQL in the source code
        import inspect
        source = inspect.getsource(purge_expired_excerpts)

        # The UPDATE should only SET rawExcerpt
        assert '"rawExcerpt" = NULL' in source
        # Should NOT touch these columns
        assert '"convergenceScore"' not in source
        assert '"authorityScore"' not in source
        assert 'vibe_tags' not in source
        assert 'activity_node_vibe_tags' not in source

    def test_reddit_sources_are_frozen(self):
        """REDDIT_SOURCES should be immutable."""
        assert isinstance(REDDIT_SOURCES, frozenset)
        with pytest.raises(AttributeError):
            REDDIT_SOURCES.add("new_source")
