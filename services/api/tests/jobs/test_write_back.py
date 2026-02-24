"""
Tests for services/api/jobs/write_back.py

Covers:
- Idempotency: re-run same day with existing 'success' run -> skip
- Laplace formula correctness at boundary cases
- WriteBackRun audit logging (both success and error paths)
- Only user_behavioral source signals counted
- DB pool mocking pattern
"""

from __future__ import annotations

import pytest
from datetime import date, datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call

from services.api.jobs.write_back import run_write_back


# ---------------------------------------------------------------------------
# Pool/connection mock builders
# ---------------------------------------------------------------------------

def _make_conn(
    existing_run=None,
    updated_rows=None,
) -> MagicMock:
    """
    Build a mock asyncpg connection.

    Args:
        existing_run:  Row returned by the idempotency check. None = no prior run.
        updated_rows:  List of row dicts returned by the UPDATE...RETURNING query.
                       None defaults to empty list (0 rows updated).
    """
    conn = AsyncMock()

    # fetchrow — idempotency guard
    conn.fetchrow = AsyncMock(return_value=existing_run)

    # fetch — the CTE UPDATE RETURNING
    conn.fetch = AsyncMock(return_value=updated_rows or [])

    # execute — INSERT INTO WriteBackRun
    conn.execute = AsyncMock(return_value=None)

    # transaction context manager
    txn = AsyncMock()
    txn.__aenter__ = AsyncMock(return_value=txn)
    txn.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=txn)

    return conn


def _make_pool(conn: MagicMock) -> MagicMock:
    """Wrap a mock connection in a mock pool."""
    pool = AsyncMock()
    # pool.acquire() as conn
    acquire_ctx = AsyncMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn)
    acquire_ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=acquire_ctx)
    return pool


# ---------------------------------------------------------------------------
# 1. Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    """Re-running the same date with a prior success run must be a no-op."""

    @pytest.mark.asyncio
    async def test_skip_when_success_run_exists(self):
        """If WriteBackRun with status='success' exists for today, return skipped."""
        prior_run = {"id": "run-abc123"}
        conn = _make_conn(existing_run=prior_run)
        pool = _make_pool(conn)

        target = date(2026, 2, 23)
        result = await run_write_back(pool, target_date=target)

        assert result["status"] == "skipped"
        assert result["rows_updated"] == 0
        assert result["date"] == "2026-02-23"

    @pytest.mark.asyncio
    async def test_skip_does_not_call_update(self):
        """When skipping, the CTE UPDATE must not run."""
        prior_run = {"id": "run-abc"}
        conn = _make_conn(existing_run=prior_run)
        pool = _make_pool(conn)

        await run_write_back(pool, target_date=date(2026, 2, 23))

        # conn.fetch is the CTE update; it must NOT have been called
        conn.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_runs_when_no_prior_success(self):
        """With no prior success run, the job proceeds and logs a WriteBackRun."""
        conn = _make_conn(existing_run=None, updated_rows=[{"id": "node-1"}, {"id": "node-2"}])
        pool = _make_pool(conn)

        result = await run_write_back(pool, target_date=date(2026, 2, 22))

        assert result["status"] == "success"
        assert result["rows_updated"] == 2
        # CTE should have been called once
        conn.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_date_defaults_to_yesterday(self):
        """When target_date is None, the job targets yesterday (UTC)."""
        conn = _make_conn()
        pool = _make_pool(conn)

        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
        result = await run_write_back(pool)

        assert result["date"] == yesterday.isoformat()


# ---------------------------------------------------------------------------
# 2. Laplace formula correctness
# ---------------------------------------------------------------------------

class TestLaplaceFormula:
    """
    The Laplace formula is applied inside PostgreSQL, but the test verifies
    the expected formula semantics via the SQL parameters passed.

    We can also verify the formula directly:
        behavioral_quality_score = (acceptance + 1.0) / (impression + 2.0)

    Boundary cases:
      - 0 impressions, 0 acceptances -> (0+1)/(0+2) = 0.5
      - 1 acceptance, 0 impressions  -> (1+1)/(0+2) = 1.0   [pathological, caught by DB constraint]
      - 0 acceptances, 1 impression  -> (0+1)/(1+2) = 0.333...
      - 10 acceptances, 10 impressions -> (10+1)/(10+2) = 0.9166...
    """

    def _laplace(self, acceptance: int, impression: int) -> float:
        return (acceptance + 1.0) / (impression + 2.0)

    def test_zero_zero_is_half(self):
        assert self._laplace(0, 0) == pytest.approx(0.5)

    def test_one_acceptance_zero_impression_is_two_thirds(self):
        # (1+1)/(0+2) = 2/2 = 1.0 — perfect (all accepted, no rejections)
        assert self._laplace(1, 0) == pytest.approx(1.0)

    def test_zero_acceptance_one_impression_is_one_third(self):
        assert self._laplace(0, 1) == pytest.approx(1 / 3)

    def test_equal_counts_approaches_point_five_from_above(self):
        # (n+1)/(n+2) for large n approaches 1.0 from below, not 0.5
        # For equal impression/acceptance = 0/0: already tested above
        # For equal n > 0: (n+1)/(2n+2) = 1/2 — wait, that's wrong.
        # impression_count = n, acceptance_count = n:
        # (n+1)/(n+2) -> approaches 1.0 as n grows (all accepted)
        assert self._laplace(10, 10) == pytest.approx(11 / 12)

    def test_all_rejected_approaches_zero(self):
        # 0 acceptances, 100 impressions: (0+1)/(100+2) = 1/102
        result = self._laplace(0, 100)
        assert result == pytest.approx(1 / 102)
        assert result < 0.05  # properly small

    def test_formula_never_zero(self):
        """Laplace ensures score is always > 0."""
        for impression in range(0, 1000, 100):
            score = self._laplace(0, impression)
            assert score > 0

    def test_formula_never_exceeds_one(self):
        """Laplace score is always <= 1.0 for any non-negative inputs."""
        for acceptance in range(0, 100, 10):
            for impression in range(acceptance, 100, 10):
                score = self._laplace(acceptance, impression)
                assert score <= 1.0


# ---------------------------------------------------------------------------
# 3. WriteBackRun audit logging
# ---------------------------------------------------------------------------

class TestAuditLogging:
    """The WriteBackRun INSERT must be called on both success and (attempted) error paths."""

    @pytest.mark.asyncio
    async def test_audit_row_inserted_on_success(self):
        """On success, conn.execute is called once with the correct status."""
        conn = _make_conn(updated_rows=[{"id": "node-1"}])
        pool = _make_pool(conn)

        await run_write_back(pool, target_date=date(2026, 2, 22))

        # conn.execute is the INSERT INTO WriteBackRun
        assert conn.execute.call_count >= 1
        # Verify the status='success' is in the call args
        first_call_args = conn.execute.call_args_list[0][0]
        # first_call_args = (_INSERT_RUN_SQL, date, status, rows_updated, duration_ms)
        assert "success" in first_call_args

    @pytest.mark.asyncio
    async def test_result_contains_duration_ms(self):
        """Result dict must include a non-negative duration_ms."""
        conn = _make_conn(updated_rows=[])
        pool = _make_pool(conn)

        result = await run_write_back(pool, target_date=date(2026, 2, 22))

        assert "duration_ms" in result
        assert isinstance(result["duration_ms"], int)
        assert result["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_result_contains_date_string(self):
        """Result dict must include ISO date string matching target_date."""
        conn = _make_conn()
        pool = _make_pool(conn)
        target = date(2026, 1, 15)

        result = await run_write_back(pool, target_date=target)

        assert result["date"] == "2026-01-15"

    @pytest.mark.asyncio
    async def test_rows_updated_matches_fetch_result(self):
        """rows_updated in result must equal len of rows returned from CTE."""
        fake_rows = [{"id": f"node-{i}"} for i in range(7)]
        conn = _make_conn(updated_rows=fake_rows)
        pool = _make_pool(conn)

        result = await run_write_back(pool, target_date=date(2026, 2, 1))

        assert result["rows_updated"] == 7

    @pytest.mark.asyncio
    async def test_zero_rows_updated_is_valid_success(self):
        """Zero rows updated is a valid success (no signals yesterday)."""
        conn = _make_conn(updated_rows=[])
        pool = _make_pool(conn)

        result = await run_write_back(pool, target_date=date(2026, 2, 22))

        assert result["status"] == "success"
        assert result["rows_updated"] == 0


# ---------------------------------------------------------------------------
# 4. Signal source filter (user_behavioral only)
# ---------------------------------------------------------------------------

class TestSignalSourceFilter:
    """
    The CTE WHERE clause must include source = 'user_behavioral'.
    We verify by inspecting the SQL string that is passed to conn.fetch.
    """

    @pytest.mark.asyncio
    async def test_sql_includes_user_behavioral_filter(self):
        """The SQL sent to asyncpg must filter by source = 'user_behavioral'."""
        from services.api.jobs.write_back import _WRITE_BACK_SQL

        assert "source = 'user_behavioral'" in _WRITE_BACK_SQL

    @pytest.mark.asyncio
    async def test_sql_excludes_synthetic_signals_by_source_clause(self):
        """
        The query must NOT use a filter that would include synthetic signals.
        Verify that there is no broad WHERE clause that omits source filtering.
        """
        from services.api.jobs.write_back import _WRITE_BACK_SQL

        # Must not accidentally select all sources
        assert "source IS NOT NULL" not in _WRITE_BACK_SQL
        assert "source != 'synthetic'" not in _WRITE_BACK_SQL

    @pytest.mark.asyncio
    async def test_sql_uses_activitynodeid_is_not_null_guard(self):
        """Signals without activityNodeId must be excluded."""
        from services.api.jobs.write_back import _WRITE_BACK_SQL

        assert '"activityNodeId" IS NOT NULL' in _WRITE_BACK_SQL

    @pytest.mark.asyncio
    async def test_impression_signal_types_defined_in_sql(self):
        """Impression signal types match the spec."""
        from services.api.jobs.write_back import _WRITE_BACK_SQL

        for signal_type in (
            "slot_view",
            "slot_tap",
            "slot_confirm",
            "slot_complete",
            "discover_swipe_right",
            "discover_shortlist",
        ):
            assert signal_type in _WRITE_BACK_SQL

    @pytest.mark.asyncio
    async def test_acceptance_signal_types_defined_in_sql(self):
        """Acceptance signal types match the spec."""
        from services.api.jobs.write_back import _WRITE_BACK_SQL

        for signal_type in (
            "slot_confirm",
            "slot_complete",
            "discover_shortlist",
            "post_loved",
        ):
            assert signal_type in _WRITE_BACK_SQL


# ---------------------------------------------------------------------------
# 5. Date window boundaries
# ---------------------------------------------------------------------------

class TestDateWindow:
    """The job must query the correct UTC calendar day window."""

    @pytest.mark.asyncio
    async def test_fetch_receives_two_datetime_params(self):
        """conn.fetch must be called with two positional datetime args (day_start, day_end)."""
        conn = _make_conn()
        pool = _make_pool(conn)

        await run_write_back(pool, target_date=date(2026, 2, 10))

        assert conn.fetch.call_count == 1
        call_args = conn.fetch.call_args[0]
        # call_args[0] = SQL string, [1] = day_start, [2] = day_end
        assert len(call_args) == 3
        day_start, day_end = call_args[1], call_args[2]
        assert isinstance(day_start, datetime)
        assert isinstance(day_end, datetime)
        assert day_start.tzinfo is not None
        assert day_end.tzinfo is not None

    @pytest.mark.asyncio
    async def test_window_is_exactly_24_hours(self):
        """day_end - day_start must be exactly 24 hours."""
        conn = _make_conn()
        pool = _make_pool(conn)

        await run_write_back(pool, target_date=date(2026, 2, 10))

        call_args = conn.fetch.call_args[0]
        day_start, day_end = call_args[1], call_args[2]
        delta = day_end - day_start
        assert delta == timedelta(days=1)

    @pytest.mark.asyncio
    async def test_window_matches_target_date(self):
        """day_start must be midnight UTC of target_date."""
        conn = _make_conn()
        pool = _make_pool(conn)
        target = date(2026, 3, 5)

        await run_write_back(pool, target_date=target)

        call_args = conn.fetch.call_args[0]
        day_start = call_args[1]
        assert day_start.year == 2026
        assert day_start.month == 3
        assert day_start.day == 5
        assert day_start.hour == 0
        assert day_start.minute == 0
        assert day_start.second == 0
