"""
Tests for services/api/persona/effective.py

Coverage:
  1. Cold user (no PersonaDimension rows) -> default dimensions, confidence 0.5
  2. User with onboarding data -> DB values returned correctly
  3. Cache hit -> TripPersonaCache data returned, DB NOT queried
  4. Cache version stale -> falls through to DB
  5. Destination prior applied -> low-confidence dimensions get prior blended in
  6. Destination prior NOT applied -> high-confidence dimensions are untouched
  7. CF blend stub -> returns dimensions unchanged, no crash
  8. Negative tag affinities -> correctly extracted from PersonaDimension rows
  9. Redis unavailable (None) -> graceful degradation, falls through to DB
 10. Redis error (exception) -> graceful degradation, falls through to DB
 11. DB unavailable -> exception propagated (fatal)
 12. get_persona_for_ranking -> correct flat dict format
 13. get_persona_for_ranking pace/budget extraction
 14. get_persona_for_ranking vibes filtering by confidence threshold
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.api.persona.effective import (
    effective_persona,
    get_persona_for_ranking,
)
from services.api.persona.types import DimensionValue, PersonaSnapshot


# ---------------------------------------------------------------------------
# Mock builders
# ---------------------------------------------------------------------------


def _make_row(
    dimension: str,
    value: str,
    confidence: float = 0.8,
    source: str = "onboarding",
    negative_tag_affinities: dict | None = None,
    version: int = 1,
) -> MagicMock:
    """Build a mock asyncpg Record-like object for a PersonaDimension row."""
    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "dimension": dimension,
        "value": value,
        "confidence": confidence,
        "source": source,
        "negativeTagAffinities": (
            json.dumps(negative_tag_affinities) if negative_tag_affinities else None
        ),
        "version": version,
    }[key]
    return row


def _make_version_row(version: int = 1) -> MagicMock:
    """Build a mock row for the version pre-fetch query."""
    row = MagicMock()
    row.__getitem__ = lambda self, key: {"version": version}[key]
    return row


def _make_conn(
    persona_rows: list | None = None,
    version_rows: list | None = None,
) -> AsyncMock:
    """
    Build a mock asyncpg connection.

    fetch() returns persona_rows (or version_rows for the version pre-fetch).
    We distinguish by the SQL string passed to fetch() — version pre-fetch
    uses LIMIT 1 with only 'version' column.
    """
    conn = AsyncMock()

    # Track fetch call count to differentiate version pre-fetch vs full persona fetch
    call_tracker: dict[str, int] = {"count": 0}

    async def _fetch(sql: str, *args: object) -> list:
        if "LIMIT 1" in sql and "version" in sql and "negativeTagAffinities" not in sql:
            # This is the version pre-fetch (only selects version, not full row)
            return version_rows if version_rows is not None else []
        # This is the full PersonaDimension fetch
        return persona_rows if persona_rows is not None else []

    conn.fetch = AsyncMock(side_effect=_fetch)
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value=None)

    txn = AsyncMock()
    txn.__aenter__ = AsyncMock(return_value=txn)
    txn.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=txn)

    return conn


def _make_pool(conn: AsyncMock) -> MagicMock:
    """Wrap a mock connection in a mock pool."""
    pool = MagicMock()
    acquire_ctx = AsyncMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn)
    acquire_ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=acquire_ctx)
    return pool


def _make_redis(
    cache_data: dict | None = None,
    raises: Exception | None = None,
) -> AsyncMock:
    """
    Build a mock Redis client.

    If raises is set, hgetall() raises that exception.
    If cache_data is None, hgetall() returns empty dict (miss).
    """
    redis = AsyncMock()

    async def _hgetall(key: str) -> dict:
        if raises is not None:
            raise raises
        return cache_data or {}

    redis.hgetall = AsyncMock(side_effect=_hgetall)
    return redis


def _make_cached_snapshot(
    user_id: str,
    trip_id: str,
    version: int = 1,
) -> dict:
    """Build a Redis hash payload representing a cached PersonaSnapshot."""
    dims = {
        "food_priority": {"value": "food_driven", "confidence": 0.9, "source": "trip_cache"},
        "pace_preference": {"value": "slow_traveler", "confidence": 0.7, "source": "trip_cache"},
    }
    return {
        "nightly_sync_version": str(version),
        "dimensions": json.dumps(dims),
        "negative_tag_affinities": json.dumps({"party-central": -0.8}),
        "source_breakdown": json.dumps({"food_priority": "trip_cache"}),
        "confidence": "0.8",
        "resolved_at": "2026-02-25T03:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# Test: Cold user (no DB rows)
# ---------------------------------------------------------------------------


class TestColdUser:
    @pytest.mark.asyncio
    async def test_cold_user_returns_default_dimensions(self):
        """Cold user with no PersonaDimension rows gets default dimensions."""
        conn = _make_conn(persona_rows=[], version_rows=[])
        pool = _make_pool(conn)

        snapshot = await effective_persona("user-cold", pool=pool)

        assert isinstance(snapshot, PersonaSnapshot)
        assert snapshot.user_id == "user-cold"
        assert snapshot.trip_id is None
        assert snapshot.cache_hit is False
        # Should have default dimensions
        assert len(snapshot.dimensions) > 0
        # All defaults have confidence 0.5
        for dv in snapshot.dimensions.values():
            assert dv.confidence == 0.5
        # Overall confidence should be 0.5
        assert snapshot.confidence == pytest.approx(0.5, abs=0.01)

    @pytest.mark.asyncio
    async def test_cold_user_default_source_is_onboarding(self):
        """Default dimensions are attributed to 'onboarding' source."""
        conn = _make_conn(persona_rows=[], version_rows=[])
        pool = _make_pool(conn)

        snapshot = await effective_persona("user-cold", pool=pool)

        for dv in snapshot.dimensions.values():
            assert dv.source == "onboarding"

    @pytest.mark.asyncio
    async def test_cold_user_no_negative_tags(self):
        """Cold user has empty negative tag affinities."""
        conn = _make_conn(persona_rows=[], version_rows=[])
        pool = _make_pool(conn)

        snapshot = await effective_persona("user-cold", pool=pool)

        assert snapshot.negative_tag_affinities == {}

    @pytest.mark.asyncio
    async def test_cold_user_resolved_at_is_set(self):
        """resolved_at is always a non-empty ISO timestamp."""
        conn = _make_conn(persona_rows=[], version_rows=[])
        pool = _make_pool(conn)

        snapshot = await effective_persona("user-cold", pool=pool)

        assert snapshot.resolved_at
        assert "T" in snapshot.resolved_at  # ISO format check


# ---------------------------------------------------------------------------
# Test: User with onboarding data
# ---------------------------------------------------------------------------


class TestUserWithOnboardingData:
    @pytest.mark.asyncio
    async def test_db_dimensions_returned(self):
        """User with PersonaDimension rows gets those values."""
        rows = [
            _make_row("food_priority", "food_driven", confidence=0.85, source="onboarding"),
            _make_row("pace_preference", "slow_traveler", confidence=0.70, source="behavioral_ema"),
        ]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        snapshot = await effective_persona("user-123", pool=pool)

        assert "food_priority" in snapshot.dimensions
        assert snapshot.dimensions["food_priority"].value == "food_driven"
        assert snapshot.dimensions["food_priority"].confidence == pytest.approx(0.85)
        assert snapshot.dimensions["food_priority"].source == "onboarding"

        assert "pace_preference" in snapshot.dimensions
        assert snapshot.dimensions["pace_preference"].value == "slow_traveler"
        assert snapshot.dimensions["pace_preference"].source == "behavioral_ema"

    @pytest.mark.asyncio
    async def test_source_breakdown_matches_db(self):
        """source_breakdown dict mirrors sources from DB."""
        rows = [
            _make_row("food_priority", "food_driven", source="behavioral_ema"),
            _make_row("culture_engagement", "culture_immersive", source="onboarding"),
        ]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        snapshot = await effective_persona("user-123", pool=pool)

        assert snapshot.source_breakdown["food_priority"] == "behavioral_ema"
        assert snapshot.source_breakdown["culture_engagement"] == "onboarding"

    @pytest.mark.asyncio
    async def test_overall_confidence_is_mean(self):
        """Overall confidence = mean of dimension confidences."""
        rows = [
            _make_row("food_priority", "food_driven", confidence=0.8),
            _make_row("pace_preference", "slow_traveler", confidence=0.6),
        ]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        snapshot = await effective_persona("user-123", pool=pool)

        expected = (0.8 + 0.6) / 2
        assert snapshot.confidence == pytest.approx(expected, abs=0.01)

    @pytest.mark.asyncio
    async def test_cache_hit_false_when_no_redis(self):
        """cache_hit is False when Redis is not provided."""
        rows = [_make_row("food_priority", "food_driven")]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        snapshot = await effective_persona("user-123", pool=pool, redis_client=None)

        assert snapshot.cache_hit is False


# ---------------------------------------------------------------------------
# Test: Cache hit
# ---------------------------------------------------------------------------


class TestCacheHit:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_snapshot(self):
        """Valid cache hit returns cached data and sets cache_hit=True."""
        cached = _make_cached_snapshot("user-123", "trip-456", version=5)
        redis = _make_redis(cache_data=cached)

        # DB returns the same version
        conn = _make_conn(version_rows=[_make_version_row(5)])
        pool = _make_pool(conn)

        snapshot = await effective_persona(
            "user-123", trip_id="trip-456", pool=pool, redis_client=redis
        )

        assert snapshot.cache_hit is True
        assert snapshot.user_id == "user-123"
        assert snapshot.trip_id == "trip-456"
        assert "food_priority" in snapshot.dimensions
        assert snapshot.dimensions["food_priority"].value == "food_driven"
        assert snapshot.negative_tag_affinities == {"party-central": -0.8}

    @pytest.mark.asyncio
    async def test_cache_hit_does_not_call_full_persona_fetch(self):
        """On cache hit, we only do the version pre-fetch, not the full PersonaDimension query."""
        cached = _make_cached_snapshot("user-123", "trip-456", version=3)
        redis = _make_redis(cache_data=cached)

        fetch_calls: list[str] = []

        async def _tracked_fetch(sql: str, *args: object) -> list:
            fetch_calls.append(sql)
            if "LIMIT 1" in sql and "version" in sql and "negativeTagAffinities" not in sql:
                return [_make_version_row(3)]
            # Should NOT reach here on a cache hit
            return []

        conn = AsyncMock()
        conn.fetch = AsyncMock(side_effect=_tracked_fetch)
        txn = AsyncMock()
        txn.__aenter__ = AsyncMock(return_value=txn)
        txn.__aexit__ = AsyncMock(return_value=False)
        conn.transaction = MagicMock(return_value=txn)
        pool = _make_pool(conn)

        await effective_persona(
            "user-123", trip_id="trip-456", pool=pool, redis_client=redis
        )

        # Only the version pre-fetch should have been called.
        # The full PersonaDimension fetch is distinguished by selecting
        # 'negativeTagAffinities' — the version pre-fetch only selects 'version'.
        full_persona_calls = [
            s for s in fetch_calls
            if "negativeTagAffinities" in s
        ]
        assert len(full_persona_calls) == 0, (
            f"Full PersonaDimension fetch was called on a cache hit: {full_persona_calls}"
        )


# ---------------------------------------------------------------------------
# Test: Cache version stale
# ---------------------------------------------------------------------------


class TestCacheVersionStale:
    @pytest.mark.asyncio
    async def test_stale_cache_falls_through_to_db(self):
        """Version mismatch causes cache bypass; DB dimensions are returned."""
        # Cache has version=2, but DB has version=5
        cached = _make_cached_snapshot("user-123", "trip-456", version=2)
        redis = _make_redis(cache_data=cached)

        db_rows = [
            _make_row("food_priority", "food_balanced", confidence=0.6, version=5),
        ]
        conn = _make_conn(persona_rows=db_rows, version_rows=[_make_version_row(5)])
        pool = _make_pool(conn)

        snapshot = await effective_persona(
            "user-123", trip_id="trip-456", pool=pool, redis_client=redis
        )

        # Should return DB data, not cache data
        assert snapshot.cache_hit is False
        assert snapshot.dimensions["food_priority"].value == "food_balanced"

    @pytest.mark.asyncio
    async def test_stale_cache_snapshot_user_id_from_db(self):
        """When cache is stale, snapshot user_id still matches the request."""
        cached = _make_cached_snapshot("user-123", "trip-456", version=1)
        redis = _make_redis(cache_data=cached)

        db_rows = [_make_row("food_priority", "food_driven", version=99)]
        conn = _make_conn(persona_rows=db_rows, version_rows=[_make_version_row(99)])
        pool = _make_pool(conn)

        snapshot = await effective_persona(
            "user-123", trip_id="trip-456", pool=pool, redis_client=redis
        )

        assert snapshot.user_id == "user-123"
        assert snapshot.cache_hit is False


# ---------------------------------------------------------------------------
# Test: Destination prior applied
# ---------------------------------------------------------------------------


class TestDestinationPriorApplied:
    @pytest.mark.asyncio
    async def test_low_confidence_dimension_gets_prior(self):
        """Dimension with confidence < 0.3 gets destination prior blended in."""
        # User has food_priority with very low confidence
        rows = [
            _make_row("food_priority", "food_balanced", confidence=0.1),
        ]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        snapshot = await effective_persona(
            "user-123", pool=pool, city_slug="austin"
        )

        # austin has food_priority prior -> should be injected for dimensions not present
        # We had food_priority with confidence 0.1 < 0.3 gate -> prior injected
        food_dim = snapshot.dimensions.get("food_priority")
        assert food_dim is not None
        # The injected prior replaces the low-confidence user value
        # destination_prior source confirms injection
        assert food_dim.source == "destination_prior"

    @pytest.mark.asyncio
    async def test_missing_dimension_gets_prior(self):
        """Dimension entirely absent from user data gets filled by destination prior."""
        # User has no nightlife_interest dimension
        rows = [
            _make_row("food_priority", "food_driven", confidence=0.85),
        ]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        snapshot = await effective_persona(
            "user-123", pool=pool, city_slug="new-orleans"
        )

        # new-orleans has a strong nightlife_interest prior; user has none
        nightlife = snapshot.dimensions.get("nightlife_interest")
        assert nightlife is not None
        assert nightlife.source == "destination_prior"

    @pytest.mark.asyncio
    async def test_source_breakdown_updated_for_prior_dims(self):
        """source_breakdown reflects 'destination_prior' for injected dimensions."""
        rows = []  # Cold user — all dimensions missing
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        snapshot = await effective_persona(
            "user-cold", pool=pool, city_slug="bend"
        )

        # bend has very strong outdoor_affinity prior
        assert snapshot.source_breakdown.get("outdoor_affinity") == "destination_prior"


# ---------------------------------------------------------------------------
# Test: Destination prior NOT applied for high-confidence dims
# ---------------------------------------------------------------------------


class TestDestinationPriorNotApplied:
    @pytest.mark.asyncio
    async def test_high_confidence_dimension_unchanged(self):
        """Dimension with confidence >= 0.3 is NOT overwritten by destination prior."""
        rows = [
            _make_row("food_priority", "food_driven", confidence=0.9, source="behavioral_ema"),
        ]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        snapshot = await effective_persona(
            "user-123", pool=pool, city_slug="austin"
        )

        food_dim = snapshot.dimensions["food_priority"]
        # Should keep the user's behavioral_ema value, not destination_prior
        assert food_dim.source == "behavioral_ema"
        assert food_dim.value == "food_driven"
        assert food_dim.confidence == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_at_gate_boundary_not_overwritten(self):
        """Confidence exactly at 0.3 (== CONFIDENCE_GATE) is NOT overwritten."""
        rows = [
            _make_row("food_priority", "food_driven", confidence=0.3, source="onboarding"),
        ]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        snapshot = await effective_persona(
            "user-123", pool=pool, city_slug="austin"
        )

        food_dim = snapshot.dimensions["food_priority"]
        assert food_dim.source == "onboarding"

    @pytest.mark.asyncio
    async def test_no_city_slug_skips_prior(self):
        """Without city_slug, destination prior layer is not applied."""
        rows = [
            _make_row("food_priority", "food_balanced", confidence=0.1, source="onboarding"),
        ]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        snapshot = await effective_persona(
            "user-123", pool=pool, city_slug=None
        )

        food_dim = snapshot.dimensions["food_priority"]
        # Prior not applied — user's low-confidence value remains as-is
        assert food_dim.source == "onboarding"
        assert food_dim.value == "food_balanced"


# ---------------------------------------------------------------------------
# Test: CF blend stub
# ---------------------------------------------------------------------------


class TestCfBlendStub:
    @pytest.mark.asyncio
    async def test_cf_blend_stub_does_not_crash(self):
        """CF blend stub is a no-op and does not raise."""
        rows = [_make_row("food_priority", "food_driven", confidence=0.8)]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        # Should not raise
        snapshot = await effective_persona("user-123", pool=pool)
        assert snapshot is not None

    @pytest.mark.asyncio
    async def test_cf_blend_stub_returns_unchanged_dimensions(self):
        """CF blend stub leaves dimensions identical to DB values."""
        rows = [
            _make_row("food_priority", "food_driven", confidence=0.8),
            _make_row("pace_preference", "slow_traveler", confidence=0.6),
        ]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        snapshot = await effective_persona("user-123", pool=pool)

        # Dimensions should be exactly what the DB returned
        assert snapshot.dimensions["food_priority"].value == "food_driven"
        assert snapshot.dimensions["food_priority"].confidence == pytest.approx(0.8)
        assert snapshot.dimensions["pace_preference"].value == "slow_traveler"


# ---------------------------------------------------------------------------
# Test: Negative tag affinities
# ---------------------------------------------------------------------------


class TestNegativeTagAffinities:
    @pytest.mark.asyncio
    async def test_negative_tags_extracted_from_first_non_null_row(self):
        """negativeTagAffinities from the first non-null DB row is used."""
        neg_tags = {"party-central": -0.8, "tourist-trap": -0.5}
        rows = [
            _make_row(
                "food_priority",
                "food_driven",
                negative_tag_affinities=neg_tags,
            ),
            _make_row(
                "pace_preference",
                "slow_traveler",
                negative_tag_affinities=None,
            ),
        ]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        snapshot = await effective_persona("user-123", pool=pool)

        assert snapshot.negative_tag_affinities == {
            "party-central": -0.8,
            "tourist-trap": -0.5,
        }

    @pytest.mark.asyncio
    async def test_negative_tags_are_floats(self):
        """All negative tag affinity values are floats, not strings."""
        rows = [
            _make_row(
                "food_priority",
                "food_driven",
                negative_tag_affinities={"hidden-gem": -0.3},
            )
        ]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        snapshot = await effective_persona("user-123", pool=pool)

        for tag, weight in snapshot.negative_tag_affinities.items():
            assert isinstance(weight, float), f"Tag {tag!r} has non-float weight: {weight!r}"

    @pytest.mark.asyncio
    async def test_no_negative_tags_returns_empty_dict(self):
        """User with all-null negativeTagAffinities gets empty dict."""
        rows = [
            _make_row("food_priority", "food_driven", negative_tag_affinities=None),
        ]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        snapshot = await effective_persona("user-123", pool=pool)

        assert snapshot.negative_tag_affinities == {}

    @pytest.mark.asyncio
    async def test_negative_tags_skips_null_rows_uses_first_non_null(self):
        """Rows with null negativeTagAffinities are skipped; first non-null is used."""
        neg_tags = {"party-central": -0.9}
        rows = [
            # First row: null
            _make_row("food_priority", "food_driven", negative_tag_affinities=None),
            # Second row: has tags
            _make_row("pace_preference", "slow_traveler", negative_tag_affinities=neg_tags),
        ]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        snapshot = await effective_persona("user-123", pool=pool)

        assert snapshot.negative_tag_affinities == {"party-central": -0.9}


# ---------------------------------------------------------------------------
# Test: Redis unavailable
# ---------------------------------------------------------------------------


class TestRedisUnavailable:
    @pytest.mark.asyncio
    async def test_redis_none_falls_through_to_db(self):
        """When redis_client=None, gracefully skip cache and read from DB."""
        rows = [_make_row("food_priority", "food_driven", confidence=0.85)]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        snapshot = await effective_persona(
            "user-123", trip_id="trip-456", pool=pool, redis_client=None
        )

        assert snapshot.cache_hit is False
        assert snapshot.dimensions["food_priority"].value == "food_driven"

    @pytest.mark.asyncio
    async def test_redis_error_falls_through_to_db(self):
        """When Redis raises an exception, gracefully fall through to DB."""
        redis = _make_redis(raises=ConnectionError("Redis down"))

        rows = [_make_row("food_priority", "food_driven", confidence=0.85)]
        conn = _make_conn(persona_rows=rows, version_rows=[_make_version_row(1)])
        pool = _make_pool(conn)

        # Should not raise — Redis error is non-fatal
        snapshot = await effective_persona(
            "user-123", trip_id="trip-456", pool=pool, redis_client=redis
        )

        assert snapshot.cache_hit is False
        assert "food_priority" in snapshot.dimensions

    @pytest.mark.asyncio
    async def test_redis_empty_response_is_cache_miss(self):
        """Empty dict from hgetall() is treated as cache miss."""
        redis = _make_redis(cache_data={})

        rows = [_make_row("food_priority", "food_driven")]
        conn = _make_conn(persona_rows=rows, version_rows=[_make_version_row(1)])
        pool = _make_pool(conn)

        snapshot = await effective_persona(
            "user-123", trip_id="trip-456", pool=pool, redis_client=redis
        )

        assert snapshot.cache_hit is False


# ---------------------------------------------------------------------------
# Test: DB unavailable
# ---------------------------------------------------------------------------


class TestDbUnavailable:
    @pytest.mark.asyncio
    async def test_db_failure_raises_exception(self):
        """DB failure is fatal — exception must propagate."""
        pool = MagicMock()
        acquire_ctx = AsyncMock()
        conn = AsyncMock()
        conn.fetch = AsyncMock(side_effect=OSError("DB connection refused"))
        acquire_ctx.__aenter__ = AsyncMock(return_value=conn)
        acquire_ctx.__aexit__ = AsyncMock(return_value=False)
        pool.acquire = MagicMock(return_value=acquire_ctx)

        with pytest.raises(OSError, match="DB connection refused"):
            await effective_persona("user-123", pool=pool)

    @pytest.mark.asyncio
    async def test_no_pool_raises_value_error(self):
        """Calling effective_persona without a pool raises ValueError."""
        with pytest.raises(ValueError, match="pool"):
            await effective_persona("user-123", pool=None)


# ---------------------------------------------------------------------------
# Test: get_persona_for_ranking
# ---------------------------------------------------------------------------


class TestGetPersonaForRanking:
    @pytest.mark.asyncio
    async def test_returns_expected_keys(self):
        """get_persona_for_ranking returns dict with required ranker keys."""
        rows = [
            _make_row("food_priority", "food_driven", confidence=0.85),
            _make_row("pace_preference", "slow_traveler", confidence=0.7),
        ]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        result = await get_persona_for_ranking(
            "user-123", "trip-456", pool=pool
        )

        assert "vibes" in result
        assert "pace" in result
        assert "budget" in result
        assert "dimensions" in result
        assert "negative_tags" in result

    @pytest.mark.asyncio
    async def test_pace_slow_mapped_correctly(self):
        """'slow_traveler' pace_preference maps to 'slow' in ranker output."""
        rows = [
            _make_row("pace_preference", "slow_traveler", confidence=0.8),
        ]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        result = await get_persona_for_ranking("user-123", "trip-456", pool=pool)

        assert result["pace"] == "slow"

    @pytest.mark.asyncio
    async def test_pace_moderate_as_default(self):
        """No pace_preference dimension results in 'moderate' pace."""
        rows = [_make_row("food_priority", "food_driven", confidence=0.8)]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        result = await get_persona_for_ranking("user-123", "trip-456", pool=pool)

        assert result["pace"] == "moderate"

    @pytest.mark.asyncio
    async def test_budget_mid_as_default(self):
        """No budget_orientation dimension results in 'mid' budget."""
        rows = [_make_row("food_priority", "food_driven", confidence=0.8)]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        result = await get_persona_for_ranking("user-123", "trip-456", pool=pool)

        assert result["budget"] == "mid"

    @pytest.mark.asyncio
    async def test_vibes_filtered_by_confidence_threshold(self):
        """Only dimensions with confidence >= 0.4 appear in vibes."""
        rows = [
            # Above threshold — should appear
            _make_row("food_priority", "food_driven", confidence=0.85),
            # Below threshold — should NOT appear
            _make_row("nightlife_interest", "nightlife_seeker", confidence=0.2),
        ]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        result = await get_persona_for_ranking("user-123", "trip-456", pool=pool)

        # food_priority is a vibe dimension — should be present
        vibe_labels = result["vibes"]
        assert any("food" in v for v in vibe_labels)
        # nightlife_seeker is below 0.4 threshold — should NOT be present
        assert not any("nightlife" in v for v in vibe_labels)

    @pytest.mark.asyncio
    async def test_vibes_values_hyphenated(self):
        """Vibe values use hyphens, not underscores."""
        rows = [
            _make_row("food_priority", "food_driven", confidence=0.85),
        ]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        result = await get_persona_for_ranking("user-123", "trip-456", pool=pool)

        for vibe in result["vibes"]:
            assert "_" not in vibe, f"Vibe {vibe!r} contains underscore — expected hyphens"

    @pytest.mark.asyncio
    async def test_dimensions_flat_dict_format(self):
        """dimensions dict has {dim: {value, confidence}} shape."""
        rows = [
            _make_row("food_priority", "food_driven", confidence=0.85),
        ]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        result = await get_persona_for_ranking("user-123", "trip-456", pool=pool)

        food_entry = result["dimensions"]["food_priority"]
        assert "value" in food_entry
        assert "confidence" in food_entry
        assert food_entry["value"] == "food_driven"
        assert food_entry["confidence"] == pytest.approx(0.85)

    @pytest.mark.asyncio
    async def test_negative_tags_forwarded(self):
        """negative_tags in ranker output matches snapshot.negative_tag_affinities."""
        neg_tags = {"party-central": -0.8}
        rows = [
            _make_row("food_priority", "food_driven", negative_tag_affinities=neg_tags),
        ]
        conn = _make_conn(persona_rows=rows)
        pool = _make_pool(conn)

        result = await get_persona_for_ranking("user-123", "trip-456", pool=pool)

        assert result["negative_tags"] == {"party-central": -0.8}

    @pytest.mark.asyncio
    async def test_cache_hit_still_returns_correct_ranker_format(self):
        """Cache hit path also produces valid ranker dict."""
        cached = _make_cached_snapshot("user-123", "trip-456", version=1)
        redis = _make_redis(cache_data=cached)

        conn = _make_conn(version_rows=[_make_version_row(1)])
        pool = _make_pool(conn)

        result = await get_persona_for_ranking(
            "user-123", "trip-456", pool=pool, redis_client=redis
        )

        assert "vibes" in result
        assert "pace" in result
        assert "budget" in result
        assert "dimensions" in result
        assert "negative_tags" in result
        assert result["negative_tags"] == {"party-central": -0.8}
