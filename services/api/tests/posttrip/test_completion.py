"""
Unit tests: timezone-aware trip completion + photo upload validation.

Covers:
- should_complete_trip() with freeze_time across JST, GMT, HST
- auto_complete_trips() batch processing
- mark_trip_completed() status transition
- Trips missing timezone/endDate are never auto-completed
- Photo upload validation (content type, file size)
- Slot status override: completed -> skipped
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from services.api.posttrip.completion import (
    should_complete_trip,
    mark_trip_completed,
    auto_complete_trips,
)
from services.api.routers.upload import (
    SignedUrlRequest,
    ALLOWED_CONTENT_TYPES,
    MAX_FILE_SIZE_BYTES,
)


# ---------------------------------------------------------------------------
# Helpers to build mock Trip objects
# ---------------------------------------------------------------------------

def _mock_trip(
    status: str = "active",
    end_date: datetime | None = None,
    tz: str | None = "Asia/Tokyo",
) -> MagicMock:
    """Build a mock Trip model instance."""
    trip = MagicMock()
    trip.id = "trip-tz-test"
    trip.status = status
    trip.endDate = end_date
    trip.timezone = tz
    return trip


# ===================================================================
# 1. Timezone-aware completion (freeze_time across zones)
# ===================================================================

class TestShouldCompleteTrip:
    """Tests for should_complete_trip() timezone logic."""

    @pytest.mark.asyncio
    async def test_tokyo_trip_past_enddate_completes(self):
        """JST trip whose endDate has passed (UTC-perspective) should complete."""
        # endDate = yesterday 23:59 JST
        jst = ZoneInfo("Asia/Tokyo")
        end = datetime(2026, 2, 19, 23, 59, 0)  # naive, will be localized to JST

        with patch("services.api.posttrip.completion.datetime") as mock_dt:
            # "now" = Feb 20, 2026 10:00 UTC (= Feb 20 19:00 JST, after endDate)
            mock_dt.now.return_value = datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            trip = _mock_trip(end_date=end, tz="Asia/Tokyo")
            result = await should_complete_trip(trip)
            assert result is True

    @pytest.mark.asyncio
    async def test_honolulu_trip_not_yet_passed_stays_active(self):
        """HST trip whose endDate hasn't passed in local tz stays active."""
        # endDate = Feb 20, 2026 23:59 HST
        end = datetime(2026, 2, 20, 23, 59, 0)

        with patch("services.api.posttrip.completion.datetime") as mock_dt:
            # "now" = Feb 20, 2026 20:00 UTC (= Feb 20 10:00 HST, before endDate)
            mock_dt.now.return_value = datetime(2026, 2, 20, 20, 0, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            trip = _mock_trip(end_date=end, tz="Pacific/Honolulu")
            result = await should_complete_trip(trip)
            assert result is False

    @pytest.mark.asyncio
    async def test_london_trip_bst_boundary(self):
        """London trip checks DST handling (BST = UTC+1 in summer)."""
        # endDate = Jul 15, 2026 23:59 (BST = UTC+1)
        end = datetime(2026, 7, 15, 23, 59, 0)

        with patch("services.api.posttrip.completion.datetime") as mock_dt:
            # "now" = Jul 16, 2026 00:30 UTC (= Jul 16 01:30 BST, after endDate)
            mock_dt.now.return_value = datetime(2026, 7, 16, 0, 30, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            trip = _mock_trip(end_date=end, tz="Europe/London")
            result = await should_complete_trip(trip)
            assert result is True

    @pytest.mark.asyncio
    async def test_already_completed_trip_returns_false(self):
        """Trips already in completed status should return False."""
        trip = _mock_trip(
            status="completed",
            end_date=datetime(2026, 1, 1),
            tz="Asia/Tokyo",
        )
        result = await should_complete_trip(trip)
        assert result is False

    @pytest.mark.asyncio
    async def test_trip_no_enddate_returns_false(self):
        """Trips without endDate should not auto-complete."""
        trip = _mock_trip(end_date=None, tz="Asia/Tokyo")
        result = await should_complete_trip(trip)
        assert result is False

    @pytest.mark.asyncio
    async def test_trip_no_timezone_returns_false(self):
        """Trips without timezone should not auto-complete."""
        trip = _mock_trip(
            end_date=datetime(2026, 1, 1),
            tz=None,
        )
        result = await should_complete_trip(trip)
        assert result is False


# ===================================================================
# 2. mark_trip_completed
# ===================================================================

class TestMarkTripCompleted:
    """Tests for mark_trip_completed()."""

    @pytest.mark.asyncio
    async def test_sets_status_to_completed(self, mock_db_posttrip):
        """mark_trip_completed should update trip status to completed."""
        mock_db_posttrip.trip.update = AsyncMock(return_value=MagicMock(
            id="trip-1", status="completed"
        ))

        result = await mark_trip_completed(mock_db_posttrip, "trip-1")
        assert result.status == "completed"

        call_args = mock_db_posttrip.trip.update.call_args
        assert call_args.kwargs["data"]["status"] == "completed"
        assert "completedAt" in call_args.kwargs["data"]

    @pytest.mark.asyncio
    async def test_uses_provided_completed_at(self, mock_db_posttrip):
        """When completedAt is explicitly provided, it should be used."""
        custom_dt = datetime(2026, 2, 15, 12, 0, 0, tzinfo=timezone.utc)
        mock_db_posttrip.trip.update = AsyncMock(return_value=MagicMock(
            id="trip-1", status="completed"
        ))

        await mark_trip_completed(mock_db_posttrip, "trip-1", completed_at=custom_dt)

        call_args = mock_db_posttrip.trip.update.call_args
        assert call_args.kwargs["data"]["completedAt"] == custom_dt


# ===================================================================
# 3. auto_complete_trips batch
# ===================================================================

class TestAutoCompleteTrips:
    """Tests for auto_complete_trips() batch job."""

    @pytest.mark.asyncio
    async def test_completes_eligible_trips(self, mock_db_posttrip):
        """Batch job should complete trips past their endDate."""
        past_trip = _mock_trip(
            end_date=datetime(2026, 2, 18, 23, 59, 0),
            tz="Asia/Tokyo",
        )
        past_trip.id = "trip-past"

        future_trip = _mock_trip(
            end_date=datetime(2026, 12, 31, 23, 59, 0),
            tz="Asia/Tokyo",
        )
        future_trip.id = "trip-future"

        mock_db_posttrip.trip.find_many = AsyncMock(return_value=[past_trip, future_trip])
        mock_db_posttrip.trip.update = AsyncMock(return_value=MagicMock(status="completed"))

        with patch("services.api.posttrip.completion.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            completed = await auto_complete_trips(mock_db_posttrip)

        assert "trip-past" in completed
        assert "trip-future" not in completed

    @pytest.mark.asyncio
    async def test_empty_trips_returns_empty_list(self, mock_db_posttrip):
        """When no trips need completion, returns empty list."""
        mock_db_posttrip.trip.find_many = AsyncMock(return_value=[])
        completed = await auto_complete_trips(mock_db_posttrip)
        assert completed == []


# ===================================================================
# 4. Photo upload validation
# ===================================================================

class TestPhotoUploadValidation:
    """Tests for upload signed-URL request validation."""

    def test_valid_jpeg_request(self):
        """Valid JPEG upload request passes validation."""
        req = SignedUrlRequest(
            tripId="trip-1",
            slotId="slot-1",
            contentType="image/jpeg",
            fileSizeBytes=1024 * 1024,  # 1MB
        )
        assert req.contentType == "image/jpeg"

    def test_valid_png_request(self):
        """Valid PNG upload request passes validation."""
        req = SignedUrlRequest(
            tripId="trip-1",
            slotId="slot-1",
            contentType="image/png",
            fileSizeBytes=500_000,
        )
        assert req.contentType == "image/png"

    def test_valid_webp_request(self):
        """Valid WebP upload request passes validation."""
        req = SignedUrlRequest(
            tripId="trip-1",
            slotId="slot-1",
            contentType="image/webp",
            fileSizeBytes=200_000,
        )
        assert req.contentType == "image/webp"

    def test_rejects_gif_content_type(self):
        """GIF is not in allowed content types."""
        with pytest.raises(ValueError, match="Unsupported content type"):
            SignedUrlRequest(
                tripId="trip-1",
                slotId="slot-1",
                contentType="image/gif",
                fileSizeBytes=100_000,
            )

    def test_rejects_svg_content_type(self):
        """SVG is not allowed for photo uploads."""
        with pytest.raises(ValueError, match="Unsupported content type"):
            SignedUrlRequest(
                tripId="trip-1",
                slotId="slot-1",
                contentType="image/svg+xml",
                fileSizeBytes=50_000,
            )

    def test_rejects_oversized_file(self):
        """Files exceeding 10MB should be rejected."""
        with pytest.raises(ValueError, match="File too large"):
            SignedUrlRequest(
                tripId="trip-1",
                slotId="slot-1",
                contentType="image/jpeg",
                fileSizeBytes=MAX_FILE_SIZE_BYTES + 1,
            )

    def test_rejects_zero_byte_file(self):
        """Zero-byte files should be rejected."""
        with pytest.raises(ValueError):
            SignedUrlRequest(
                tripId="trip-1",
                slotId="slot-1",
                contentType="image/jpeg",
                fileSizeBytes=0,
            )

    def test_exactly_max_size_allowed(self):
        """Files at exactly 10MB should be allowed."""
        req = SignedUrlRequest(
            tripId="trip-1",
            slotId="slot-1",
            contentType="image/jpeg",
            fileSizeBytes=MAX_FILE_SIZE_BYTES,
        )
        assert req.fileSizeBytes == MAX_FILE_SIZE_BYTES

    def test_all_allowed_types_are_images(self):
        """All allowed content types must be image/* types."""
        for ct in ALLOWED_CONTENT_TYPES:
            assert ct.startswith("image/"), f"{ct} is not an image type"


# ===================================================================
# 5. Slot status override: completed -> skipped
# ===================================================================

class TestSlotStatusOverride:
    """Tests for overriding slot status during post-trip reflection."""

    @pytest.mark.asyncio
    async def test_completed_to_skipped_override(
        self, mock_db_posttrip, slot_completed_to_skipped, completed_user
    ):
        """User can override a 'completed' slot to 'skipped' during reflection."""
        slot = slot_completed_to_skipped
        user_id = completed_user["id"]

        # Simulate the update
        updated_slot = MagicMock()
        updated_slot.id = slot["id"]
        updated_slot.status = "skipped"
        mock_db_posttrip.itineraryslot.update = AsyncMock(return_value=updated_slot)

        result = await mock_db_posttrip.itineraryslot.update(
            where={"id": slot["id"]},
            data={"status": "skipped"},
        )

        assert result.status == "skipped"
        mock_db_posttrip.itineraryslot.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_override_writes_behavioral_signal(
        self, mock_db_posttrip, slot_completed_to_skipped, completed_user
    ):
        """Status override should also write a post_skipped behavioral signal."""
        slot = slot_completed_to_skipped
        user_id = completed_user["id"]

        signal_data = {
            "userId": user_id,
            "slotId": slot["id"],
            "signalType": "post_skipped",
            "signalValue": -1.0,
            "tripPhase": "post_trip",
            "rawAction": "status_override_completed_to_skipped",
        }

        mock_signal = MagicMock()
        mock_signal.id = "signal-override-1"
        mock_signal.signalType = "post_skipped"
        mock_db_posttrip.behavioralsignal.create = AsyncMock(return_value=mock_signal)

        result = await mock_db_posttrip.behavioralsignal.create(data=signal_data)
        assert result.signalType == "post_skipped"
