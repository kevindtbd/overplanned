"""
Unit tests: Off-Plan Signal Handler — Phase 1.4.

Covers:
- Matched path: creates BehavioralSignal with correct fields
- Unmatched path: creates CorpusIngestionRequest with correct fields
- Deduplication: second call for same (user, venue, trip) returns "duplicate"
- Input validation: empty user_id / trip_id / place_name raises ValueError
- db_pool is mocked — no real DB needed
- Returned dicts have correct "type" discriminator
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.api.signals.off_plan_handler import handle_off_plan_add


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _build_db_pool(
    dedup_result=None,
    fetchrow_results: list | None = None,
) -> AsyncMock:
    """
    Build a mock asyncpg-style db_pool.

    Args:
        dedup_result:    Value returned by the first fetchrow() call (dedup check).
                         None means no duplicate found.
        fetchrow_results: Ordered list of values for subsequent fetchrow() calls.
                          Defaults to a generic success record.
    """
    pool = AsyncMock()

    now = _now()
    default_signal_record = {
        "id": _id(),
        "signalType": "slot_confirm",
        "subflow": "onthefly_add",
        "source": "user_behavioral",
        "createdAt": now,
    }
    default_ingestion_record = {
        "id": _id(),
        "rawPlaceName": "Test Place",
        "source": "off_plan_add",
        "status": "pending",
        "createdAt": now,
    }

    if fetchrow_results is None:
        fetchrow_results = [default_signal_record]

    call_queue = [dedup_result] + fetchrow_results

    call_index = 0

    async def _fetchrow(sql, *args):
        nonlocal call_index
        val = call_queue[call_index] if call_index < len(call_queue) else None
        call_index += 1
        return val

    pool.fetchrow = AsyncMock(side_effect=_fetchrow)
    return pool


# ===================================================================
# 1. Matched path
# ===================================================================

class TestMatchedPath:
    """activityNodeId provided — creates a BehavioralSignal."""

    @pytest.mark.asyncio
    async def test_matched_returns_signal_type(self):
        node_id = _id()
        now = _now()
        record = {
            "id": _id(),
            "signalType": "slot_confirm",
            "subflow": "onthefly_add",
            "source": "user_behavioral",
            "createdAt": now,
        }
        pool = _build_db_pool(dedup_result=None, fetchrow_results=[record])

        result = await handle_off_plan_add(
            user_id=_id(),
            trip_id=_id(),
            place_name="Tsukiji Market",
            activity_node_id=node_id,
            db_pool=pool,
        )

        assert result["type"] == "signal"
        assert result["activityNodeId"] == node_id
        assert result["signalType"] == "slot_confirm"
        assert result["subflow"] == "onthefly_add"
        assert result["source"] == "user_behavioral"

    @pytest.mark.asyncio
    async def test_matched_result_has_created_at_string(self):
        node_id = _id()
        now = _now()
        record = {
            "id": _id(),
            "signalType": "slot_confirm",
            "subflow": "onthefly_add",
            "source": "user_behavioral",
            "createdAt": now,
        }
        pool = _build_db_pool(dedup_result=None, fetchrow_results=[record])

        result = await handle_off_plan_add(
            user_id=_id(),
            trip_id=_id(),
            place_name="Meiji Shrine",
            activity_node_id=node_id,
            db_pool=pool,
        )

        assert isinstance(result["createdAt"], str)
        # Should be a valid ISO-8601 string
        datetime.fromisoformat(result["createdAt"])

    @pytest.mark.asyncio
    async def test_matched_db_called_twice(self):
        """Two fetchrow calls expected: dedup check + signal insert."""
        node_id = _id()
        now = _now()
        record = {
            "id": _id(),
            "signalType": "slot_confirm",
            "subflow": "onthefly_add",
            "source": "user_behavioral",
            "createdAt": now,
        }
        pool = _build_db_pool(dedup_result=None, fetchrow_results=[record])

        await handle_off_plan_add(
            user_id=_id(),
            trip_id=_id(),
            place_name="Senso-ji",
            activity_node_id=node_id,
            db_pool=pool,
        )

        assert pool.fetchrow.call_count == 2


# ===================================================================
# 2. Unmatched path
# ===================================================================

class TestUnmatchedPath:
    """No activityNodeId — creates a CorpusIngestionRequest."""

    @pytest.mark.asyncio
    async def test_unmatched_returns_ingestion_request_type(self):
        now = _now()
        record = {
            "id": _id(),
            "rawPlaceName": "Hidden Gem Bar",
            "source": "off_plan_add",
            "status": "pending",
            "createdAt": now,
        }
        pool = _build_db_pool(dedup_result=None, fetchrow_results=[record])

        result = await handle_off_plan_add(
            user_id=_id(),
            trip_id=_id(),
            place_name="Hidden Gem Bar",
            activity_node_id=None,
            db_pool=pool,
        )

        assert result["type"] == "ingestion_request"
        assert result["source"] == "off_plan_add"
        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_unmatched_result_has_place_name(self):
        now = _now()
        place = "Obscure Ramen Shop"
        record = {
            "id": _id(),
            "rawPlaceName": place,
            "source": "off_plan_add",
            "status": "pending",
            "createdAt": now,
        }
        pool = _build_db_pool(dedup_result=None, fetchrow_results=[record])

        result = await handle_off_plan_add(
            user_id=_id(),
            trip_id=_id(),
            place_name=place,
            activity_node_id=None,
            db_pool=pool,
        )

        assert result["rawPlaceName"] == place

    @pytest.mark.asyncio
    async def test_unmatched_created_at_is_iso_string(self):
        now = _now()
        record = {
            "id": _id(),
            "rawPlaceName": "Local Izakaya",
            "source": "off_plan_add",
            "status": "pending",
            "createdAt": now,
        }
        pool = _build_db_pool(dedup_result=None, fetchrow_results=[record])

        result = await handle_off_plan_add(
            user_id=_id(),
            trip_id=_id(),
            place_name="Local Izakaya",
            activity_node_id=None,
            db_pool=pool,
        )

        assert isinstance(result["createdAt"], str)
        datetime.fromisoformat(result["createdAt"])

    @pytest.mark.asyncio
    async def test_unmatched_db_called_twice(self):
        """Two fetchrow calls expected: dedup check + ingestion insert."""
        now = _now()
        record = {
            "id": _id(),
            "rawPlaceName": "SomePlace",
            "source": "off_plan_add",
            "status": "pending",
            "createdAt": now,
        }
        pool = _build_db_pool(dedup_result=None, fetchrow_results=[record])

        await handle_off_plan_add(
            user_id=_id(),
            trip_id=_id(),
            place_name="SomePlace",
            activity_node_id=None,
            db_pool=pool,
        )

        assert pool.fetchrow.call_count == 2


# ===================================================================
# 3. Deduplication
# ===================================================================

class TestDeduplication:
    """Second call for same (user, venue, trip) returns 'duplicate'."""

    @pytest.mark.asyncio
    async def test_dedup_matched_path(self):
        """Duplicate matched-path call returns duplicate type."""
        # Simulate dedup check returning a row (already recorded)
        pool = _build_db_pool(dedup_result={"id": _id()}, fetchrow_results=[])

        result = await handle_off_plan_add(
            user_id=_id(),
            trip_id=_id(),
            place_name="Tsukiji Market",
            activity_node_id=_id(),
            db_pool=pool,
        )

        assert result["type"] == "duplicate"
        assert "message" in result

    @pytest.mark.asyncio
    async def test_dedup_unmatched_path(self):
        """Duplicate unmatched-path call returns duplicate type."""
        pool = _build_db_pool(dedup_result={"id": _id()}, fetchrow_results=[])

        result = await handle_off_plan_add(
            user_id=_id(),
            trip_id=_id(),
            place_name="Unknown Tavern",
            activity_node_id=None,
            db_pool=pool,
        )

        assert result["type"] == "duplicate"

    @pytest.mark.asyncio
    async def test_dedup_only_fetches_once_when_duplicate(self):
        """On duplicate, only the dedup check fetchrow is called (no insert)."""
        pool = _build_db_pool(dedup_result={"id": _id()}, fetchrow_results=[])

        await handle_off_plan_add(
            user_id=_id(),
            trip_id=_id(),
            place_name="Same Venue",
            activity_node_id=_id(),
            db_pool=pool,
        )

        # Only 1 call: the dedup check. No insert attempted.
        assert pool.fetchrow.call_count == 1

    @pytest.mark.asyncio
    async def test_duplicate_message_mentions_place_name(self):
        """The duplicate message should reference the place name."""
        pool = _build_db_pool(dedup_result={"id": _id()}, fetchrow_results=[])
        place = "Shibuya Crossing Cafe"

        result = await handle_off_plan_add(
            user_id=_id(),
            trip_id=_id(),
            place_name=place,
            activity_node_id=None,
            db_pool=pool,
        )

        assert place in result["message"]


# ===================================================================
# 4. Input validation
# ===================================================================

class TestInputValidation:
    """Empty required fields raise ValueError before any DB access."""

    @pytest.mark.asyncio
    async def test_empty_user_id_raises(self):
        pool = AsyncMock()
        with pytest.raises(ValueError, match="user_id"):
            await handle_off_plan_add(
                user_id="",
                trip_id=_id(),
                place_name="Some Place",
                activity_node_id=None,
                db_pool=pool,
            )
        pool.fetchrow.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_trip_id_raises(self):
        pool = AsyncMock()
        with pytest.raises(ValueError, match="trip_id"):
            await handle_off_plan_add(
                user_id=_id(),
                trip_id="",
                place_name="Some Place",
                activity_node_id=None,
                db_pool=pool,
            )
        pool.fetchrow.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_place_name_raises(self):
        pool = AsyncMock()
        with pytest.raises(ValueError, match="place_name"):
            await handle_off_plan_add(
                user_id=_id(),
                trip_id=_id(),
                place_name="",
                activity_node_id=None,
                db_pool=pool,
            )
        pool.fetchrow.assert_not_called()

    @pytest.mark.asyncio
    async def test_whitespace_only_place_name_raises(self):
        pool = AsyncMock()
        with pytest.raises(ValueError, match="place_name"):
            await handle_off_plan_add(
                user_id=_id(),
                trip_id=_id(),
                place_name="   ",
                activity_node_id=None,
                db_pool=pool,
            )


# ===================================================================
# 5. Return dict shape completeness
# ===================================================================

class TestReturnShape:
    """Each return type has the expected keys."""

    @pytest.mark.asyncio
    async def test_matched_result_keys(self):
        node_id = _id()
        now = _now()
        record = {
            "id": _id(),
            "signalType": "slot_confirm",
            "subflow": "onthefly_add",
            "source": "user_behavioral",
            "createdAt": now,
        }
        pool = _build_db_pool(dedup_result=None, fetchrow_results=[record])
        user_id = _id()
        trip_id = _id()

        result = await handle_off_plan_add(
            user_id=user_id,
            trip_id=trip_id,
            place_name="Test Venue",
            activity_node_id=node_id,
            db_pool=pool,
        )

        expected_keys = {"type", "id", "userId", "tripId", "activityNodeId",
                         "signalType", "subflow", "source", "createdAt"}
        assert expected_keys.issubset(result.keys())

    @pytest.mark.asyncio
    async def test_ingestion_result_keys(self):
        now = _now()
        record = {
            "id": _id(),
            "rawPlaceName": "Test Venue",
            "source": "off_plan_add",
            "status": "pending",
            "createdAt": now,
        }
        pool = _build_db_pool(dedup_result=None, fetchrow_results=[record])

        result = await handle_off_plan_add(
            user_id=_id(),
            trip_id=_id(),
            place_name="Test Venue",
            activity_node_id=None,
            db_pool=pool,
        )

        expected_keys = {"type", "id", "rawPlaceName", "source", "status", "createdAt"}
        assert expected_keys.issubset(result.keys())

    @pytest.mark.asyncio
    async def test_duplicate_result_keys(self):
        pool = _build_db_pool(dedup_result={"id": _id()}, fetchrow_results=[])

        result = await handle_off_plan_add(
            user_id=_id(),
            trip_id=_id(),
            place_name="Duplicate Venue",
            activity_node_id=None,
            db_pool=pool,
        )

        assert "type" in result
        assert "message" in result
        assert result["type"] == "duplicate"
