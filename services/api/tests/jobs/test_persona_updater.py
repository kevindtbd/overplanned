"""
Tests for services/api/jobs/persona_updater.py (nightly EMA persona update).

Covers:
- EMA computation correctness
- Mid-trip 3x alpha boost
- New user handling (no existing PersonaDimension rows)
- Idempotency (skip if prior success run exists)
- Category-to-dimension mapping
- Min-signals cold-start guard
- Audit logging
- Date window
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.api.jobs.persona_updater import (
    CATEGORY_DIMENSION_MAP,
    DEFAULT_CONFIDENCE,
    EMA_ALPHA,
    MID_TRIP_ALPHA_MULTIPLIER,
    MIN_SIGNALS_FOR_UPDATE,
    NEGATIVE_SIGNAL_TYPES,
    POSITIVE_SIGNAL_TYPES,
    _build_dimension_updates,
    _default_value_for_dimension,
    _effective_alpha,
    compute_ema,
    run_persona_update,
)


# ---------------------------------------------------------------------------
# Pool / connection mock builders
# ---------------------------------------------------------------------------

def _make_conn(
    existing_run=None,
    signal_rows=None,
    persona_rows=None,
):
    """
    Build a mock asyncpg connection.

    Args:
        existing_run:  Row returned by idempotency check. None = no prior run.
        signal_rows:   Rows from _SIGNALS_WITH_CATEGORY_SQL.
        persona_rows:  Rows from _GET_PERSONA_SQL (per-user).
    """
    conn = AsyncMock()

    # execute — CREATE TABLE, INSERT audit, UPSERT persona
    conn.execute = AsyncMock(return_value=None)

    # fetchrow — idempotency guard
    conn.fetchrow = AsyncMock(return_value=existing_run)

    # fetch — multiplex based on call order:
    # 1st call: signals query -> signal_rows
    # 2nd+ call: persona query -> persona_rows
    fetch_call_count = 0

    async def _fetch_side_effect(*args, **kwargs):
        nonlocal fetch_call_count
        fetch_call_count += 1
        if fetch_call_count == 1:
            return signal_rows or []
        return persona_rows or []

    conn.fetch = AsyncMock(side_effect=_fetch_side_effect)

    # transaction context manager
    txn = AsyncMock()
    txn.__aenter__ = AsyncMock(return_value=txn)
    txn.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=txn)

    return conn


def _make_pool(conn: MagicMock) -> MagicMock:
    """Wrap a mock connection in a mock pool."""
    pool = AsyncMock()
    acquire_ctx = AsyncMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn)
    acquire_ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=acquire_ctx)
    return pool


def _signal_row(user_id, signal_type, category, trip_phase="pre_trip"):
    """Build a signal row dict matching the SQL query shape."""
    return {
        "userId": user_id,
        "signalType": signal_type,
        "tripPhase": trip_phase,
        "category": category,
    }


def _persona_row(dimension, value, confidence=0.5, source="onboarding"):
    """Build a PersonaDimension row dict."""
    return {
        "dimension": dimension,
        "value": value,
        "confidence": confidence,
        "source": source,
    }


# ===========================================================================
# 1. EMA computation
# ===========================================================================

class TestComputeEma:
    """Tests for the compute_ema function."""

    def test_positive_signal_increases_confidence(self):
        """A positive signal nudges confidence toward 1.0."""
        result = compute_ema(0.5, 1.0, alpha=0.3, weight=1.0)
        assert result > 0.5

    def test_negative_signal_decreases_confidence(self):
        """A negative signal nudges confidence toward 0.0."""
        result = compute_ema(0.5, -1.0, alpha=0.3, weight=1.0)
        assert result < 0.5

    def test_clamped_above_minimum(self):
        """Confidence never drops below 0.05."""
        # Many negative signals
        conf = 0.05
        for _ in range(100):
            conf = compute_ema(conf, -1.0, alpha=0.9, weight=1.0)
        assert conf >= 0.05

    def test_clamped_below_maximum(self):
        """Confidence never exceeds 0.98."""
        conf = 0.98
        for _ in range(100):
            conf = compute_ema(conf, 1.0, alpha=0.9, weight=1.0)
        assert conf <= 0.98

    def test_weight_zero_preserves_confidence(self):
        """Weight=0 means no change (effective_alpha = 0)."""
        result = compute_ema(0.7, 1.0, alpha=0.3, weight=0.0)
        assert result == pytest.approx(0.7)

    def test_weight_scales_alpha(self):
        """Lower weight means smaller update."""
        high_weight = compute_ema(0.5, 1.0, alpha=0.3, weight=1.0)
        low_weight = compute_ema(0.5, 1.0, alpha=0.3, weight=0.3)
        # Both should increase, but high_weight more
        assert high_weight > low_weight > 0.5

    def test_alpha_one_jumps_to_target(self):
        """Alpha=1.0 with weight=1.0 jumps to the target (clamped)."""
        pos = compute_ema(0.2, 1.0, alpha=1.0, weight=1.0)
        assert pos == pytest.approx(0.98)  # clamped at max

        neg = compute_ema(0.8, -1.0, alpha=1.0, weight=1.0)
        assert neg == pytest.approx(0.05)  # clamped at min

    def test_exact_ema_value(self):
        """Verify exact EMA formula: alpha*weight*target + (1-alpha*weight)*current."""
        # positive: target=1.0, alpha=0.3, weight=1.0, current=0.5
        # new = 0.3*1.0 + 0.7*0.5 = 0.3 + 0.35 = 0.65
        result = compute_ema(0.5, 1.0, alpha=0.3, weight=1.0)
        assert result == pytest.approx(0.65)


# ===========================================================================
# 2. Mid-trip 3x alpha boost
# ===========================================================================

class TestMidTripBoost:

    def test_active_phase_alpha_is_3x(self):
        """tripPhase='active' returns alpha * 3."""
        alpha = _effective_alpha("active")
        assert alpha == pytest.approx(EMA_ALPHA * MID_TRIP_ALPHA_MULTIPLIER)

    def test_active_alpha_capped_at_1(self):
        """Even with 3x, alpha cannot exceed 1.0."""
        assert _effective_alpha("active") <= 1.0

    def test_pre_trip_uses_base_alpha(self):
        assert _effective_alpha("pre_trip") == pytest.approx(EMA_ALPHA)

    def test_post_trip_uses_base_alpha(self):
        assert _effective_alpha("post_trip") == pytest.approx(EMA_ALPHA)

    def test_active_signals_update_more(self):
        """Active-phase signal moves confidence more than pre_trip."""
        current = {"food_priority": {"value": "food_balanced", "confidence": 0.5, "source": "onboarding"}}

        pre_trip_signals = [
            _signal_row("u1", "slot_confirm", "restaurant", "pre_trip"),
            _signal_row("u1", "slot_confirm", "restaurant", "pre_trip"),
        ]
        active_signals = [
            _signal_row("u1", "slot_confirm", "restaurant", "active"),
            _signal_row("u1", "slot_confirm", "restaurant", "active"),
        ]

        pre_updates = _build_dimension_updates(pre_trip_signals, current)
        active_updates = _build_dimension_updates(active_signals, current)

        # Active signals should produce higher confidence
        pre_conf = pre_updates.get("food_priority", 0.5)
        active_conf = active_updates.get("food_priority", 0.5)
        assert active_conf > pre_conf


# ===========================================================================
# 3. New user handling
# ===========================================================================

class TestNewUserHandling:

    def test_empty_persona_gets_default_confidence(self):
        """A user with no PersonaDimension rows starts at DEFAULT_CONFIDENCE."""
        signals = [
            _signal_row("u1", "slot_confirm", "restaurant"),
            _signal_row("u1", "slot_confirm", "restaurant"),
        ]
        updates = _build_dimension_updates(signals, {})
        assert "food_priority" in updates
        # Starting from 0.5 (default) and moving up
        assert updates["food_priority"] > DEFAULT_CONFIDENCE

    def test_default_values_cover_all_10_dimensions(self):
        """All 10 persona dimensions have a default value."""
        from services.api.nlp.patterns import VALID_DIMENSIONS

        for dim in VALID_DIMENSIONS:
            val = _default_value_for_dimension(dim)
            assert val != "unknown", f"No default for {dim}"


# ===========================================================================
# 4. Idempotency
# ===========================================================================

class TestIdempotency:

    @pytest.mark.asyncio
    async def test_skip_when_success_run_exists(self):
        """Prior successful run for same date -> skip."""
        conn = _make_conn(existing_run={"id": 42})
        pool = _make_pool(conn)

        result = await run_persona_update(pool, target_date=date(2026, 2, 24))

        assert result["status"] == "skipped"
        assert result["users_updated"] == 0
        assert result["dimensions_updated"] == 0

    @pytest.mark.asyncio
    async def test_runs_when_no_prior_success(self):
        """No prior run -> job proceeds."""
        signals = [
            _signal_row("u1", "slot_confirm", "restaurant"),
            _signal_row("u1", "slot_confirm", "restaurant"),
        ]
        conn = _make_conn(
            existing_run=None,
            signal_rows=signals,
            persona_rows=[_persona_row("food_priority", "food_balanced", 0.5)],
        )
        pool = _make_pool(conn)

        result = await run_persona_update(pool, target_date=date(2026, 2, 24))
        assert result["status"] == "success"


# ===========================================================================
# 5. Category-to-dimension mapping
# ===========================================================================

class TestCategoryMapping:

    def test_restaurant_maps_to_food_priority(self):
        """Restaurant category affects food_priority."""
        dims = [m["dimension"] for m in CATEGORY_DIMENSION_MAP["restaurant"]]
        assert "food_priority" in dims

    def test_hike_maps_to_nature_and_energy(self):
        """Hike category affects nature_preference and energy_level."""
        dims = [m["dimension"] for m in CATEGORY_DIMENSION_MAP["hike"]]
        assert "nature_preference" in dims
        assert "energy_level" in dims

    def test_museum_maps_to_culture(self):
        dims = [m["dimension"] for m in CATEGORY_DIMENSION_MAP["museum"]]
        assert "culture_engagement" in dims

    def test_club_maps_to_nightlife(self):
        dims = [m["dimension"] for m in CATEGORY_DIMENSION_MAP["club"]]
        assert "nightlife_interest" in dims

    def test_all_weights_in_range(self):
        """Every mapping weight is between 0.0 and 1.0."""
        for category, mappings in CATEGORY_DIMENSION_MAP.items():
            for m in mappings:
                assert 0.0 < m["weight"] <= 1.0, f"Bad weight for {category} -> {m['dimension']}"

    def test_unknown_category_produces_no_updates(self):
        """Signals with unmapped categories are silently ignored."""
        signals = [
            _signal_row("u1", "slot_confirm", "unknown_category"),
            _signal_row("u1", "slot_confirm", "unknown_category"),
        ]
        updates = _build_dimension_updates(signals, {})
        assert updates == {}


# ===========================================================================
# 6. Min-signals cold-start guard
# ===========================================================================

class TestMinSignalsGuard:

    def test_single_signal_insufficient(self):
        """One signal per dimension is below MIN_SIGNALS_FOR_UPDATE."""
        assert MIN_SIGNALS_FOR_UPDATE >= 2
        signals = [_signal_row("u1", "slot_confirm", "restaurant")]
        updates = _build_dimension_updates(signals, {})
        assert "food_priority" not in updates

    def test_two_signals_sufficient(self):
        """Two signals for a dimension passes the guard."""
        signals = [
            _signal_row("u1", "slot_confirm", "restaurant"),
            _signal_row("u1", "slot_complete", "restaurant"),
        ]
        updates = _build_dimension_updates(signals, {})
        assert "food_priority" in updates


# ===========================================================================
# 7. Build dimension updates
# ===========================================================================

class TestBuildDimensionUpdates:

    def test_positive_signals_increase_confidence(self):
        """Accepting restaurant slots increases food_priority confidence."""
        current = {"food_priority": {"value": "food_balanced", "confidence": 0.5, "source": "onboarding"}}
        signals = [
            _signal_row("u1", "slot_confirm", "restaurant"),
            _signal_row("u1", "slot_complete", "restaurant"),
        ]
        updates = _build_dimension_updates(signals, current)
        assert updates["food_priority"] > 0.5

    def test_negative_signals_decrease_confidence(self):
        """Rejecting restaurant slots decreases food_priority confidence."""
        current = {"food_priority": {"value": "food_driven", "confidence": 0.8, "source": "onboarding"}}
        signals = [
            _signal_row("u1", "slot_skip", "restaurant"),
            _signal_row("u1", "slot_skip", "restaurant"),
        ]
        updates = _build_dimension_updates(signals, current)
        assert updates["food_priority"] < 0.8

    def test_mixed_signals_partial_update(self):
        """Mix of accept/reject produces a value between extremes."""
        current = {"food_priority": {"value": "food_balanced", "confidence": 0.5, "source": "onboarding"}}
        signals = [
            _signal_row("u1", "slot_confirm", "restaurant"),
            _signal_row("u1", "slot_skip", "restaurant"),
        ]
        updates = _build_dimension_updates(signals, current)
        # Depending on order, should be close to 0.5 (one up, one down)
        assert 0.3 < updates["food_priority"] < 0.7

    def test_multiple_dimensions_updated(self):
        """Hike signals update both nature_preference and energy_level."""
        current = {
            "nature_preference": {"value": "nature_curious", "confidence": 0.5, "source": "onboarding"},
            "energy_level": {"value": "medium_energy", "confidence": 0.5, "source": "onboarding"},
        }
        signals = [
            _signal_row("u1", "slot_confirm", "hike"),
            _signal_row("u1", "slot_complete", "hike"),
        ]
        updates = _build_dimension_updates(signals, current)
        assert "nature_preference" in updates
        assert "energy_level" in updates
        assert updates["nature_preference"] > 0.5
        assert updates["energy_level"] > 0.5


# ===========================================================================
# 8. Date window
# ===========================================================================

class TestDateWindow:

    @pytest.mark.asyncio
    async def test_default_date_is_yesterday(self):
        """target_date defaults to yesterday UTC."""
        conn = _make_conn()
        pool = _make_pool(conn)

        result = await run_persona_update(pool)
        expected = (datetime.now(timezone.utc) - timedelta(days=1)).date()
        assert result["date"] == expected.isoformat()

    @pytest.mark.asyncio
    async def test_result_contains_date(self):
        conn = _make_conn()
        pool = _make_pool(conn)
        target = date(2026, 3, 1)

        result = await run_persona_update(pool, target_date=target)
        assert result["date"] == "2026-03-01"


# ===========================================================================
# 9. Audit logging
# ===========================================================================

class TestAuditLogging:

    @pytest.mark.asyncio
    async def test_audit_table_created(self):
        """PersonaUpdateRun table is created on every run."""
        conn = _make_conn()
        pool = _make_pool(conn)

        await run_persona_update(pool, target_date=date(2026, 2, 24))

        # First execute call should be CREATE TABLE
        first_call = conn.execute.call_args_list[0][0][0]
        assert "PersonaUpdateRun" in first_call

    @pytest.mark.asyncio
    async def test_audit_row_on_no_signals(self):
        """Audit row is inserted even when there are zero signals."""
        conn = _make_conn(signal_rows=[])
        pool = _make_pool(conn)

        result = await run_persona_update(pool, target_date=date(2026, 2, 24))
        assert result["status"] == "success"

        # Should have: CREATE TABLE + INSERT audit = 2 execute calls
        assert conn.execute.call_count >= 2

    @pytest.mark.asyncio
    async def test_result_has_duration_ms(self):
        conn = _make_conn()
        pool = _make_pool(conn)

        result = await run_persona_update(pool, target_date=date(2026, 2, 24))
        assert "duration_ms" in result
        assert isinstance(result["duration_ms"], int)
        assert result["duration_ms"] >= 0


# ===========================================================================
# 10. Constants validation
# ===========================================================================

class TestConstants:

    def test_ema_alpha_in_range(self):
        assert 0.0 < EMA_ALPHA < 1.0

    def test_mid_trip_multiplier_is_3(self):
        assert MID_TRIP_ALPHA_MULTIPLIER == 3

    def test_min_signals_is_at_least_2(self):
        assert MIN_SIGNALS_FOR_UPDATE >= 2

    def test_positive_negative_no_overlap(self):
        assert len(POSITIVE_SIGNAL_TYPES & NEGATIVE_SIGNAL_TYPES) == 0
