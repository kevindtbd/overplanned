"""
Tests for Phase 6.10 -- GPS Feature Integration (DATA-GATED).

Covers:
- Haversine distance (known distances, equator, poles, dateline)
- Stay point extraction (clustering, duration filtering)
- Slot matching (location + time overlap)
- Completion signal upgrade
- Feature flag off returns nothing
- Edge cases
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from services.api.models.gps_features import (
    GPSConfig,
    GPSFeatureExtractor,
    StayPoint,
    haversine_distance,
)


# ===================================================================
# Haversine distance
# ===================================================================


class TestHaversineDistance:
    def test_same_point_is_zero(self):
        d = haversine_distance(35.6762, 139.6503, 35.6762, 139.6503)
        assert d == 0.0

    def test_known_distance_tokyo_to_osaka(self):
        """Tokyo Station to Osaka Station is roughly 400km."""
        d = haversine_distance(35.6812, 139.7671, 34.7025, 135.4959)
        assert 390_000 < d < 410_000  # 390-410 km

    def test_short_distance(self):
        """Two points 100m apart in Tokyo."""
        # Approximately 100m north of a point at 35.6762
        lat_offset = 100 / 111_320  # ~1 degree latitude = 111.32 km
        d = haversine_distance(35.6762, 139.6503, 35.6762 + lat_offset, 139.6503)
        assert 95 < d < 105

    def test_equator(self):
        """Points on the equator."""
        d = haversine_distance(0.0, 0.0, 0.0, 1.0)
        # 1 degree longitude at equator = ~111.32 km
        assert 110_000 < d < 112_000

    def test_poles(self):
        """Distance from north pole to a nearby point."""
        d = haversine_distance(90.0, 0.0, 89.0, 0.0)
        # 1 degree latitude = ~111.32 km
        assert 110_000 < d < 112_000

    def test_dateline(self):
        """Points crossing the international dateline."""
        d = haversine_distance(0.0, 179.0, 0.0, -179.0)
        # 2 degrees longitude at equator ~ 222.6 km
        assert 220_000 < d < 225_000

    def test_antipodal_points(self):
        """North pole to south pole = half earth circumference."""
        d = haversine_distance(90.0, 0.0, -90.0, 0.0)
        # Should be approximately pi * R = ~20,015 km
        assert 19_900_000 < d < 20_100_000


# ===================================================================
# Stay point extraction
# ===================================================================


class TestExtractStayPoints:
    def setup_method(self):
        self.extractor = GPSFeatureExtractor(
            GPSConfig(stay_radius_meters=100, stay_duration_minutes=15)
        )

    def test_single_cluster_qualifies(self):
        """Pings in same location for 20 minutes -> 1 stay point."""
        base_time = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
        pings = [
            {"lat": 35.6762, "lng": 139.6503, "timestamp": base_time + timedelta(minutes=i)}
            for i in range(21)  # 21 pings, 1 per minute
        ]
        result = self.extractor.extract_stay_points(pings)
        assert len(result) == 1
        assert result[0].duration_minutes == 20.0
        assert abs(result[0].lat - 35.6762) < 0.001

    def test_short_stay_filtered_out(self):
        """Pings for only 10 minutes -> no stay point (below 15 min threshold)."""
        base_time = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
        pings = [
            {"lat": 35.6762, "lng": 139.6503, "timestamp": base_time + timedelta(minutes=i)}
            for i in range(11)
        ]
        result = self.extractor.extract_stay_points(pings)
        assert len(result) == 0

    def test_two_distinct_clusters(self):
        """Two locations visited for 20 min each -> 2 stay points."""
        base_time = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
        # First location
        pings = [
            {"lat": 35.6762, "lng": 139.6503, "timestamp": base_time + timedelta(minutes=i)}
            for i in range(21)
        ]
        # Second location (far away)
        pings.extend([
            {"lat": 34.7025, "lng": 135.4959, "timestamp": base_time + timedelta(minutes=30 + i)}
            for i in range(21)
        ])
        result = self.extractor.extract_stay_points(pings)
        assert len(result) == 2

    def test_empty_pings(self):
        result = self.extractor.extract_stay_points([])
        assert result == []

    def test_single_ping(self):
        """Single ping cannot form a stay point (0 duration)."""
        pings = [{"lat": 35.0, "lng": 139.0, "timestamp": datetime.now(timezone.utc)}]
        result = self.extractor.extract_stay_points(pings)
        assert len(result) == 0


# ===================================================================
# Slot matching
# ===================================================================


class TestMatchStayToSlot:
    def setup_method(self):
        self.extractor = GPSFeatureExtractor(
            GPSConfig(stay_radius_meters=100)
        )

    def test_match_within_radius_and_time(self):
        base_time = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
        sp = StayPoint(
            lat=35.6762, lng=139.6503,
            arrival_time=base_time,
            departure_time=base_time + timedelta(minutes=30),
            duration_minutes=30,
        )
        result = self.extractor.match_stay_to_slot(
            sp, 35.6762, 139.6503,
            base_time - timedelta(minutes=5),
            base_time + timedelta(minutes=60),
        )
        assert result is True

    def test_no_match_too_far(self):
        base_time = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
        sp = StayPoint(
            lat=35.6762, lng=139.6503,
            arrival_time=base_time,
            departure_time=base_time + timedelta(minutes=30),
            duration_minutes=30,
        )
        # Slot is in Osaka
        result = self.extractor.match_stay_to_slot(
            sp, 34.7025, 135.4959,
            base_time, base_time + timedelta(minutes=60),
        )
        assert result is False

    def test_no_match_no_time_overlap(self):
        base_time = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
        sp = StayPoint(
            lat=35.6762, lng=139.6503,
            arrival_time=base_time,
            departure_time=base_time + timedelta(minutes=30),
            duration_minutes=30,
        )
        # Slot is 2 hours later
        result = self.extractor.match_stay_to_slot(
            sp, 35.6762, 139.6503,
            base_time + timedelta(hours=2),
            base_time + timedelta(hours=3),
        )
        assert result is False


# ===================================================================
# Completion signal upgrade
# ===================================================================


class TestUpgradeCompletionSignals:
    def test_upgrades_likely_attended(self):
        extractor = GPSFeatureExtractor(GPSConfig(stay_radius_meters=100))
        base_time = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)

        stay_points = [
            StayPoint(
                lat=35.6762, lng=139.6503,
                arrival_time=base_time,
                departure_time=base_time + timedelta(minutes=30),
                duration_minutes=30,
            )
        ]
        slots = [
            {
                "id": "slot-1",
                "lat": 35.6762,
                "lng": 139.6503,
                "start_time": base_time,
                "end_time": base_time + timedelta(hours=1),
                "status": "likely_attended",
            }
        ]

        with patch.dict(os.environ, {"GPS_FEATURES_ENABLED": "true"}):
            result = extractor.upgrade_completion_signals(stay_points, slots)

        assert len(result) == 1
        assert result[0]["signal_type"] == "confirmed_attended"
        assert result[0]["signal_weight"] == 1.0
        assert result[0]["slot_id"] == "slot-1"

    def test_skips_non_likely_attended(self):
        extractor = GPSFeatureExtractor()
        base_time = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)

        stay_points = [
            StayPoint(
                lat=35.6762, lng=139.6503,
                arrival_time=base_time,
                departure_time=base_time + timedelta(minutes=30),
                duration_minutes=30,
            )
        ]
        slots = [
            {
                "id": "slot-1",
                "lat": 35.6762,
                "lng": 139.6503,
                "start_time": base_time,
                "end_time": base_time + timedelta(hours=1),
                "status": "confirmed",  # Not likely_attended
            }
        ]

        with patch.dict(os.environ, {"GPS_FEATURES_ENABLED": "true"}):
            result = extractor.upgrade_completion_signals(stay_points, slots)

        assert len(result) == 0

    def test_inactive_returns_empty(self):
        """Feature flag off -> no upgrades."""
        extractor = GPSFeatureExtractor()
        base_time = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)

        stay_points = [
            StayPoint(
                lat=35.6762, lng=139.6503,
                arrival_time=base_time,
                departure_time=base_time + timedelta(minutes=30),
                duration_minutes=30,
            )
        ]
        slots = [
            {
                "id": "slot-1",
                "lat": 35.6762,
                "lng": 139.6503,
                "start_time": base_time,
                "end_time": base_time + timedelta(hours=1),
                "status": "likely_attended",
            }
        ]

        with patch.dict(os.environ, {}, clear=True):
            # Ensure GPS_FEATURES_ENABLED is not set
            os.environ.pop("GPS_FEATURES_ENABLED", None)
            result = extractor.upgrade_completion_signals(stay_points, slots)

        assert result == []


# ===================================================================
# Feature flag
# ===================================================================


class TestFeatureFlag:
    def test_active_when_true(self):
        extractor = GPSFeatureExtractor()
        with patch.dict(os.environ, {"GPS_FEATURES_ENABLED": "true"}):
            assert extractor.is_active() is True

    def test_active_when_one(self):
        extractor = GPSFeatureExtractor()
        with patch.dict(os.environ, {"GPS_FEATURES_ENABLED": "1"}):
            assert extractor.is_active() is True

    def test_inactive_when_missing(self):
        extractor = GPSFeatureExtractor()
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GPS_FEATURES_ENABLED", None)
            assert extractor.is_active() is False

    def test_inactive_when_false(self):
        extractor = GPSFeatureExtractor()
        with patch.dict(os.environ, {"GPS_FEATURES_ENABLED": "false"}):
            assert extractor.is_active() is False
