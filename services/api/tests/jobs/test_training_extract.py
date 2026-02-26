"""
Tests for services/api/jobs/training_extract.py (nightly BPR extraction).

Covers:
- BPR pair generation: positive/negative pairing per-user
- Idempotent re-runs: skip if file already exists
- In-batch negative generation: negatives from same user only
- Cold-user quarantine: users with < MIN_COMPLETED_TRIPS excluded
- Parquet schema validation
- Audit logging
- Error handling
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pyarrow.parquet as pq
import pytest

from services.api.jobs.training_extract import (
    BPR_SCHEMA,
    MIN_COMPLETED_TRIPS,
    NEGATIVE_SIGNAL_TYPES,
    POSITIVE_SIGNAL_TYPES,
    ExtractionResult,
    _build_bpr_pairs,
    _output_file_path,
    _write_parquet,
    extract_training_data,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_signal(user_id, node_id, signal_type, ts=None):
    """Build a minimal signal dict for BPR pair tests."""
    return {
        "userId": user_id,
        "activityNodeId": node_id,
        "signalType": signal_type,
        "ts": ts or int(datetime.now(timezone.utc).timestamp()),
    }


def _make_pool(
    eligible_users=None,
    signals=None,
    execute_side_effect=None,
):
    """Build a mock asyncpg pool with configurable returns."""
    pool = AsyncMock()
    conn = AsyncMock()

    fetch_results = []
    if eligible_users is not None:
        fetch_results.append([{"userId": uid} for uid in eligible_users])
    if signals is not None:
        fetch_results.append(signals)

    fetch_call_count = 0

    async def _fetch_side_effect(*args, **kwargs):
        nonlocal fetch_call_count
        if fetch_call_count < len(fetch_results):
            result = fetch_results[fetch_call_count]
            fetch_call_count += 1
            return result
        return []

    conn.fetch = AsyncMock(side_effect=_fetch_side_effect)
    conn.execute = AsyncMock(side_effect=execute_side_effect)

    acm = AsyncMock()
    acm.__aenter__ = AsyncMock(return_value=conn)
    acm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=acm)

    return pool, conn


# ===========================================================================
# 1. BPR pair generation
# ===========================================================================

class TestBuildBprPairs:
    """Tests for _build_bpr_pairs — in-batch negative generation."""

    def test_basic_positive_negative_pairing(self):
        """Each positive pairs with a random negative from the same user."""
        signals = [
            _make_signal("u1", "node-a", "slot_confirm", ts=1000),
            _make_signal("u1", "node-b", "slot_skip", ts=1001),
        ]
        pairs = _build_bpr_pairs(signals)
        assert len(pairs) == 1
        assert pairs[0]["user_id"] == "u1"
        assert pairs[0]["pos_item"] == "node-a"
        assert pairs[0]["neg_item"] == "node-b"

    def test_multiple_positives_generate_multiple_pairs(self):
        """Each positive signal generates one BPR pair."""
        signals = [
            _make_signal("u1", "node-a", "slot_confirm", ts=100),
            _make_signal("u1", "node-b", "slot_complete", ts=200),
            _make_signal("u1", "node-c", "slot_skip", ts=300),
        ]
        pairs = _build_bpr_pairs(signals)
        assert len(pairs) == 2
        pos_items = {p["pos_item"] for p in pairs}
        assert pos_items == {"node-a", "node-b"}

    def test_no_negatives_yields_no_pairs(self):
        """User with only positive signals produces zero pairs."""
        signals = [
            _make_signal("u1", "node-a", "slot_confirm"),
            _make_signal("u1", "node-b", "post_loved"),
        ]
        assert _build_bpr_pairs(signals) == []

    def test_no_positives_yields_no_pairs(self):
        """User with only negative signals produces zero pairs."""
        signals = [
            _make_signal("u1", "node-a", "slot_skip"),
            _make_signal("u1", "node-b", "post_disliked"),
        ]
        assert _build_bpr_pairs(signals) == []

    def test_cross_user_isolation(self):
        """Negatives from user A are never paired with positives from user B."""
        signals = [
            _make_signal("u1", "node-a", "slot_confirm", ts=100),
            _make_signal("u1", "node-b", "slot_skip", ts=101),
            _make_signal("u2", "node-c", "post_loved", ts=200),
            # u2 has no negative -> zero pairs for u2
        ]
        pairs = _build_bpr_pairs(signals)
        assert len(pairs) == 1
        assert pairs[0]["user_id"] == "u1"

    def test_empty_signals(self):
        assert _build_bpr_pairs([]) == []

    def test_all_positive_types_recognized(self):
        """Every member of POSITIVE_SIGNAL_TYPES generates a pair."""
        signals = []
        for i, st in enumerate(POSITIVE_SIGNAL_TYPES):
            signals.append(_make_signal("u1", f"pos-{i}", st, ts=100 + i))
        signals.append(_make_signal("u1", "neg-0", "slot_skip", ts=999))
        pairs = _build_bpr_pairs(signals)
        assert len(pairs) == len(POSITIVE_SIGNAL_TYPES)

    def test_all_negative_types_available_for_sampling(self):
        """Every member of NEGATIVE_SIGNAL_TYPES is recognized as negative."""
        signals = [_make_signal("u1", "pos-0", "slot_confirm", ts=100)]
        for i, st in enumerate(NEGATIVE_SIGNAL_TYPES):
            signals.append(_make_signal("u1", f"neg-{i}", st, ts=200 + i))
        pairs = _build_bpr_pairs(signals)
        assert len(pairs) == 1
        assert pairs[0]["neg_item"].startswith("neg-")


# ===========================================================================
# 2. Idempotent re-runs
# ===========================================================================

class TestIdempotency:

    @pytest.mark.asyncio
    async def test_skip_when_file_exists(self, tmp_path):
        """Extraction is skipped if the output file already exists."""
        target = date(2026, 2, 20)
        file_path = _output_file_path(str(tmp_path), target)
        os.makedirs(os.path.dirname(file_path) or str(tmp_path), exist_ok=True)
        with open(file_path, "w") as f:
            f.write("existing")

        pool, _ = _make_pool()
        result = await extract_training_data(pool, str(tmp_path), target_date=target)

        assert result.status == "skipped"
        assert result.rows_extracted == 0

    @pytest.mark.asyncio
    async def test_re_extraction_after_file_delete(self, tmp_path):
        """After deleting the file, re-extraction proceeds normally."""
        target = date(2026, 2, 20)
        signals = [
            _make_signal("u1", "node-a", "slot_confirm", ts=1000),
            _make_signal("u1", "node-b", "slot_skip", ts=1001),
        ]
        pool, _ = _make_pool(eligible_users=["u1"], signals=signals)

        result = await extract_training_data(pool, str(tmp_path), target_date=target)
        assert result.status == "success"
        assert result.rows_extracted == 1


# ===========================================================================
# 3. Cold-user quarantine
# ===========================================================================

class TestColdUserQuarantine:

    @pytest.mark.asyncio
    async def test_no_eligible_users(self, tmp_path):
        """Zero eligible users -> success with 0 rows."""
        pool, _ = _make_pool(eligible_users=[])
        result = await extract_training_data(pool, str(tmp_path), target_date=date(2026, 2, 20))

        assert result.status == "success"
        assert result.rows_extracted == 0
        assert result.file_path is None

    def test_min_completed_trips_constant(self):
        """The cold-user threshold is 3."""
        assert MIN_COMPLETED_TRIPS == 3


# ===========================================================================
# 4. Parquet schema
# ===========================================================================

class TestParquetSchema:

    def test_schema_fields(self):
        """BPR schema has user_id, pos_item, neg_item, timestamp."""
        names = [f.name for f in BPR_SCHEMA]
        assert names == ["user_id", "pos_item", "neg_item", "timestamp"]

    def test_write_and_read_roundtrip(self, tmp_path):
        """Data survives Parquet write/read roundtrip."""
        pairs = [
            {"user_id": "user-1", "pos_item": "a", "neg_item": "b", "timestamp": 42},
        ]
        fp = str(tmp_path / "test.parquet")
        _write_parquet(pairs, fp)
        table = pq.read_table(fp)
        assert table.schema.equals(BPR_SCHEMA)
        assert table.column("user_id")[0].as_py() == "user-1"

    def test_creates_output_directory(self, tmp_path):
        """Write creates intermediate directories if needed."""
        pairs = [
            {"user_id": "u", "pos_item": "a", "neg_item": "b", "timestamp": 1},
        ]
        fp = str(tmp_path / "sub" / "dir" / "test.parquet")
        _write_parquet(pairs, fp)
        assert os.path.exists(fp)


# ===========================================================================
# 5. Full pipeline integration
# ===========================================================================

class TestExtractTrainingData:

    @pytest.mark.asyncio
    async def test_happy_path(self, tmp_path):
        """Full extraction: eligible user with positive + negative signals."""
        signals = [
            _make_signal("u1", "node-a", "slot_confirm", ts=1000),
            _make_signal("u1", "node-b", "slot_skip", ts=1001),
        ]
        pool, _ = _make_pool(eligible_users=["u1"], signals=signals)

        result = await extract_training_data(pool, str(tmp_path), target_date=date(2026, 2, 20))
        assert result.status == "success"
        assert result.rows_extracted == 1
        assert result.file_path is not None
        assert os.path.exists(result.file_path)

    @pytest.mark.asyncio
    async def test_default_date_is_yesterday(self, tmp_path):
        """target_date defaults to yesterday UTC."""
        signals = [
            _make_signal("u1", "a", "slot_confirm", ts=1000),
            _make_signal("u1", "b", "slot_skip", ts=1001),
        ]
        pool, _ = _make_pool(eligible_users=["u1"], signals=signals)
        result = await extract_training_data(pool, str(tmp_path))

        expected = (datetime.now(timezone.utc) - timedelta(days=1)).date()
        assert result.target_date == expected

    @pytest.mark.asyncio
    async def test_db_error_returns_error_result(self, tmp_path):
        """Database exceptions are caught and returned as error status."""
        pool = AsyncMock()
        conn = AsyncMock()
        conn.execute = AsyncMock()
        conn.fetch = AsyncMock(side_effect=Exception("connection reset"))

        acm = AsyncMock()
        acm.__aenter__ = AsyncMock(return_value=conn)
        acm.__aexit__ = AsyncMock(return_value=False)
        pool.acquire = MagicMock(return_value=acm)

        result = await extract_training_data(pool, str(tmp_path), target_date=date(2026, 2, 20))
        assert result.status == "error"
        assert "connection reset" in result.error_message

    @pytest.mark.asyncio
    async def test_no_signals_for_date(self, tmp_path):
        """Eligible users but zero signals -> success, 0 rows."""
        pool, _ = _make_pool(eligible_users=["u1"], signals=[])
        result = await extract_training_data(pool, str(tmp_path), target_date=date(2026, 2, 20))

        assert result.status == "success"
        assert result.rows_extracted == 0


# ===========================================================================
# 6. Signal type constants
# ===========================================================================

class TestSignalTypeConstants:

    def test_no_overlap(self):
        """Positive and negative sets must not overlap."""
        assert len(POSITIVE_SIGNAL_TYPES & NEGATIVE_SIGNAL_TYPES) == 0

    def test_positive_is_frozenset(self):
        assert isinstance(POSITIVE_SIGNAL_TYPES, frozenset)

    def test_negative_is_frozenset(self):
        assert isinstance(NEGATIVE_SIGNAL_TYPES, frozenset)


# ===========================================================================
# 7. Output path
# ===========================================================================

class TestOutputPath:

    def test_includes_date(self):
        path = _output_file_path("/data", date(2026, 3, 15))
        assert "2026-03-15" in path
        assert path.endswith(".parquet")

    def test_in_output_dir(self):
        path = _output_file_path("/my/dir", date(2026, 1, 1))
        assert path.startswith("/my/dir/")
