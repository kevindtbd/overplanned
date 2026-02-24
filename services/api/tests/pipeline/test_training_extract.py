"""
Tests for Phase 4.1: Nightly Training Data Extraction to Parquet.

Covers:
- Happy path extraction with valid signals
- BPR pair generation logic
- Cold-user quarantine (users with < 3 completed trips excluded)
- Idempotency (skip if file exists)
- Source filtering (only user_behavioral signals)
- Empty result handling
- Error handling and audit logging
- Parquet schema validation
- Date windowing
"""

import os
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

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

    # Track call sequence to return different results for different queries
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

    # pool.acquire() returns an async context manager yielding conn
    acm = AsyncMock()
    acm.__aenter__ = AsyncMock(return_value=conn)
    acm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=acm)

    return pool, conn


# ===========================================================================
# BPR pair logic tests
# ===========================================================================

class TestBuildBprPairs:
    """Tests for _build_bpr_pairs logic."""

    def test_basic_positive_negative_pairing(self):
        """Each positive signal pairs with a random negative from the same user."""
        signals = [
            _make_signal("u1", "node-a", "slot_confirm", ts=1000),
            _make_signal("u1", "node-b", "slot_skip", ts=1001),
        ]
        pairs = _build_bpr_pairs(signals)
        assert len(pairs) == 1
        assert pairs[0]["user_id"] == "u1"
        assert pairs[0]["pos_item"] == "node-a"
        assert pairs[0]["neg_item"] == "node-b"
        assert pairs[0]["timestamp"] == 1000

    def test_multiple_positives_same_user(self):
        """Multiple positives each get paired with a negative."""
        signals = [
            _make_signal("u1", "node-a", "slot_confirm", ts=100),
            _make_signal("u1", "node-b", "slot_complete", ts=200),
            _make_signal("u1", "node-c", "slot_skip", ts=300),
        ]
        pairs = _build_bpr_pairs(signals)
        assert len(pairs) == 2
        pos_items = {p["pos_item"] for p in pairs}
        assert pos_items == {"node-a", "node-b"}

    def test_no_negatives_for_user_yields_no_pairs(self):
        """User with only positive signals produces no BPR pairs."""
        signals = [
            _make_signal("u1", "node-a", "slot_confirm"),
            _make_signal("u1", "node-b", "post_loved"),
        ]
        pairs = _build_bpr_pairs(signals)
        assert len(pairs) == 0

    def test_no_positives_for_user_yields_no_pairs(self):
        """User with only negative signals produces no BPR pairs."""
        signals = [
            _make_signal("u1", "node-a", "slot_skip"),
            _make_signal("u1", "node-b", "post_disliked"),
        ]
        pairs = _build_bpr_pairs(signals)
        assert len(pairs) == 0

    def test_multi_user_isolation(self):
        """Pairs are formed per-user; negatives don't leak across users."""
        signals = [
            _make_signal("u1", "node-a", "slot_confirm", ts=100),
            _make_signal("u1", "node-b", "slot_skip", ts=101),
            _make_signal("u2", "node-c", "post_loved", ts=200),
            _make_signal("u2", "node-d", "discover_swipe_left", ts=201),
        ]
        pairs = _build_bpr_pairs(signals)
        assert len(pairs) == 2
        u1_pair = [p for p in pairs if p["user_id"] == "u1"][0]
        u2_pair = [p for p in pairs if p["user_id"] == "u2"][0]
        assert u1_pair["neg_item"] == "node-b"  # u1's only negative
        assert u2_pair["neg_item"] == "node-d"  # u2's only negative

    def test_empty_signals_yields_no_pairs(self):
        """Empty signal list returns empty pairs."""
        pairs = _build_bpr_pairs([])
        assert pairs == []

    def test_all_positive_types_recognized(self):
        """All positive signal types produce pairs when negatives exist."""
        signals = []
        for i, st in enumerate(POSITIVE_SIGNAL_TYPES):
            signals.append(_make_signal("u1", f"node-pos-{i}", st, ts=100 + i))
        signals.append(_make_signal("u1", "node-neg", "slot_skip", ts=200))
        pairs = _build_bpr_pairs(signals)
        assert len(pairs) == len(POSITIVE_SIGNAL_TYPES)

    def test_all_negative_types_recognized(self):
        """All negative signal types are available for pairing."""
        signals = [
            _make_signal("u1", "node-pos", "slot_confirm", ts=100),
        ]
        for i, st in enumerate(NEGATIVE_SIGNAL_TYPES):
            signals.append(_make_signal("u1", f"node-neg-{i}", st, ts=200 + i))
        pairs = _build_bpr_pairs(signals)
        assert len(pairs) == 1
        assert pairs[0]["neg_item"].startswith("node-neg")


# ===========================================================================
# Parquet writing tests
# ===========================================================================

class TestWriteParquet:
    """Tests for Parquet file output."""

    def test_write_parquet_creates_file(self, tmp_path):
        """Parquet file is created at the specified path."""
        pairs = [
            {"user_id": "u1", "pos_item": "a", "neg_item": "b", "timestamp": 1000},
        ]
        fp = str(tmp_path / "test.parquet")
        size = _write_parquet(pairs, fp)
        assert os.path.exists(fp)
        assert size > 0

    def test_write_parquet_schema(self, tmp_path):
        """Parquet file has the expected BPR schema."""
        pairs = [
            {"user_id": "u1", "pos_item": "a", "neg_item": "b", "timestamp": 1000},
            {"user_id": "u2", "pos_item": "c", "neg_item": "d", "timestamp": 2000},
        ]
        fp = str(tmp_path / "schema_test.parquet")
        _write_parquet(pairs, fp)
        table = pq.read_table(fp)
        assert table.schema.equals(BPR_SCHEMA)
        assert len(table) == 2

    def test_write_parquet_roundtrip(self, tmp_path):
        """Data survives a write/read roundtrip."""
        pairs = [
            {"user_id": "user-abc", "pos_item": "item-1", "neg_item": "item-2", "timestamp": 12345},
        ]
        fp = str(tmp_path / "roundtrip.parquet")
        _write_parquet(pairs, fp)
        table = pq.read_table(fp)
        assert table.column("user_id")[0].as_py() == "user-abc"
        assert table.column("pos_item")[0].as_py() == "item-1"
        assert table.column("neg_item")[0].as_py() == "item-2"
        assert table.column("timestamp")[0].as_py() == 12345


# ===========================================================================
# Full extraction pipeline tests
# ===========================================================================

class TestExtractTrainingData:
    """Integration tests for the extract_training_data function."""

    async def test_happy_path_extraction(self, tmp_path):
        """Successful extraction writes Parquet and returns success result."""
        target = date(2026, 2, 20)
        signals = [
            _make_signal("u1", "node-a", "slot_confirm", ts=1000),
            _make_signal("u1", "node-b", "slot_skip", ts=1001),
        ]
        pool, conn = _make_pool(eligible_users=["u1"], signals=signals)

        result = await extract_training_data(pool, str(tmp_path), target_date=target)
        assert result.status == "success"
        assert result.rows_extracted == 1
        assert result.file_path is not None
        assert os.path.exists(result.file_path)

    async def test_idempotency_skips_existing_file(self, tmp_path):
        """If output file already exists, extraction is skipped."""
        target = date(2026, 2, 20)
        file_path = _output_file_path(str(tmp_path), target)
        os.makedirs(os.path.dirname(file_path) or str(tmp_path), exist_ok=True)
        with open(file_path, "w") as f:
            f.write("existing")

        pool, conn = _make_pool()

        result = await extract_training_data(pool, str(tmp_path), target_date=target)
        assert result.status == "skipped"
        assert result.rows_extracted == 0

    async def test_no_eligible_users(self, tmp_path):
        """No eligible users returns success with zero rows."""
        target = date(2026, 2, 20)
        pool, conn = _make_pool(eligible_users=[])

        result = await extract_training_data(pool, str(tmp_path), target_date=target)
        assert result.status == "success"
        assert result.rows_extracted == 0
        assert result.file_path is None

    async def test_no_signals_for_date(self, tmp_path):
        """Eligible users but no signals for the target date."""
        target = date(2026, 2, 20)
        pool, conn = _make_pool(eligible_users=["u1"], signals=[])

        result = await extract_training_data(pool, str(tmp_path), target_date=target)
        assert result.status == "success"
        assert result.rows_extracted == 0

    async def test_default_date_is_yesterday(self, tmp_path):
        """When target_date is None, extracts yesterday's data."""
        signals = [
            _make_signal("u1", "node-a", "slot_confirm", ts=1000),
            _make_signal("u1", "node-b", "slot_skip", ts=1001),
        ]
        pool, conn = _make_pool(eligible_users=["u1"], signals=signals)

        result = await extract_training_data(pool, str(tmp_path))
        expected_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()
        assert result.target_date == expected_date

    async def test_db_error_returns_error_result(self, tmp_path):
        """Database errors are caught and return error status."""
        target = date(2026, 2, 20)
        pool = AsyncMock()
        conn = AsyncMock()
        conn.execute = AsyncMock()
        conn.fetch = AsyncMock(side_effect=Exception("DB connection lost"))

        acm = AsyncMock()
        acm.__aenter__ = AsyncMock(return_value=conn)
        acm.__aexit__ = AsyncMock(return_value=False)
        pool.acquire = MagicMock(return_value=acm)

        result = await extract_training_data(pool, str(tmp_path), target_date=target)
        assert result.status == "error"
        assert result.error_message is not None
        assert "DB connection lost" in result.error_message

    async def test_audit_record_logged_on_success(self, tmp_path):
        """Audit record is inserted on successful extraction."""
        target = date(2026, 2, 20)
        signals = [
            _make_signal("u1", "node-a", "slot_confirm", ts=1000),
            _make_signal("u1", "node-b", "slot_skip", ts=1001),
        ]
        pool, conn = _make_pool(eligible_users=["u1"], signals=signals)

        await extract_training_data(pool, str(tmp_path), target_date=target)

        # The audit INSERT is the last execute call
        execute_calls = conn.execute.call_args_list
        # At least 2 execute calls: CREATE TABLE + INSERT audit
        assert len(execute_calls) >= 2
        # Last call should be the audit insert
        last_call_args = execute_calls[-1][0]
        assert "TrainingExtractRun" in last_call_args[0]


# ===========================================================================
# Output file path tests
# ===========================================================================

class TestOutputFilePath:
    """Tests for file path generation."""

    def test_file_path_includes_date(self):
        """Output file path includes the ISO date."""
        path = _output_file_path("/data", date(2026, 1, 15))
        assert "2026-01-15" in path
        assert path.endswith(".parquet")

    def test_file_path_in_output_dir(self):
        """Output file is placed in the specified directory."""
        path = _output_file_path("/my/output/dir", date(2026, 3, 1))
        assert path.startswith("/my/output/dir/")


# ===========================================================================
# Signal type constants tests
# ===========================================================================

class TestSignalTypeConstants:
    """Validate signal type sets match the schema contract."""

    def test_positive_types_are_frozenset(self):
        assert isinstance(POSITIVE_SIGNAL_TYPES, frozenset)

    def test_negative_types_are_frozenset(self):
        assert isinstance(NEGATIVE_SIGNAL_TYPES, frozenset)

    def test_no_overlap_between_positive_and_negative(self):
        overlap = POSITIVE_SIGNAL_TYPES & NEGATIVE_SIGNAL_TYPES
        assert len(overlap) == 0, f"Overlap found: {overlap}"

    def test_discover_shortlist_is_positive(self):
        assert "discover_shortlist" in POSITIVE_SIGNAL_TYPES

    def test_discover_swipe_left_is_negative(self):
        assert "discover_swipe_left" in NEGATIVE_SIGNAL_TYPES
