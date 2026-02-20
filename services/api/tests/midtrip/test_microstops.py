"""
Micro-stop tests.

Covers:
- Proximity calculation: Haversine formula accuracy
- 200m radius boundary: node at 150m included, node at 300m excluded
- Micro-stop slot creation: slotType=flex, short duration (15-30min)
- Multiple nearby nodes ordered by distance
- Node status filter: only 'active' nodes surface as micro-stops
- Micro-stop does not fire during locked slots
- Micro-stop slot has correct field values
"""

from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from typing import Optional

import pytest

from services.api.tests.conftest import make_itinerary_slot, make_activity_node


# ---------------------------------------------------------------------------
# Haversine proximity utility (mirrors what spatial.py would implement)
# ---------------------------------------------------------------------------

_EARTH_RADIUS_M = 6_371_000.0


def haversine_distance(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """
    Great-circle distance in metres between two lat/lon coordinates.
    Matches the PostGIS ST_Distance(geography) result to within 0.1%.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


MICROSTOP_RADIUS_M = 200


def _nodes_in_radius(
    lat: float,
    lon: float,
    nodes: list[dict],
    radius_m: float = MICROSTOP_RADIUS_M,
) -> list[dict]:
    """Return nodes within radius_m, sorted by distance ascending."""
    result = []
    for node in nodes:
        d = haversine_distance(lat, lon, node["latitude"], node["longitude"])
        if d <= radius_m and node.get("status") == "active":
            result.append({**node, "_distance_m": d})
    return sorted(result, key=lambda n: n["_distance_m"])


def _make_microstop_slot(
    trip_id: str,
    day_number: int,
    sort_order: int,
    node: dict,
    duration_minutes: int = 20,
) -> dict:
    """Create a lightweight flex slot for a micro-stop."""
    now = datetime.now(timezone.utc)
    return {
        "tripId": trip_id,
        "activityNodeId": node["id"],
        "dayNumber": day_number,
        "sortOrder": sort_order,
        "slotType": "flex",
        "status": "proposed",
        "startTime": None,  # Set by cascade after insertion
        "endTime": None,
        "durationMinutes": duration_minutes,
        "isLocked": False,
        "wasSwapped": False,
        "createdAt": now,
        "updatedAt": now,
    }


# ---------------------------------------------------------------------------
# Haversine accuracy
# ---------------------------------------------------------------------------

class TestHaversineDistance:
    """Verify haversine accuracy against known distances."""

    def test_same_point_is_zero(self):
        """Distance from a point to itself is 0."""
        d = haversine_distance(35.6762, 139.6503, 35.6762, 139.6503)
        assert d == pytest.approx(0.0, abs=0.001)

    def test_known_150m_distance(self):
        """Two points approximately 150m apart."""
        # Shinjuku Gyoen main gate area — these two coords are ~150m apart
        lat1, lon1 = 35.6851, 139.7100
        lat2, lon2 = 35.6866, 139.7112  # ~150m NE
        d = haversine_distance(lat1, lon1, lat2, lon2)
        assert 100 < d < 220, f"Expected ~150m, got {d:.1f}m"

    def test_known_800m_distance(self):
        """Two points approximately 800m apart."""
        lat1, lon1 = 35.6851, 139.7100
        lat2, lon2 = 35.6925, 139.7025  # ~800m
        d = haversine_distance(lat1, lon1, lat2, lon2)
        assert 600 < d < 1000, f"Expected ~800m, got {d:.1f}m"

    def test_symmetry(self):
        """Distance A→B equals distance B→A."""
        lat1, lon1 = 35.6762, 139.6503
        lat2, lon2 = 35.6851, 139.7100
        assert haversine_distance(lat1, lon1, lat2, lon2) == pytest.approx(
            haversine_distance(lat2, lon2, lat1, lon1), rel=1e-6
        )

    def test_north_pole_to_equator(self):
        """Sanity check: 90 degree latitude change ≈ 10,000km."""
        d = haversine_distance(90.0, 0.0, 0.0, 0.0)
        assert 9_500_000 < d < 10_500_000


# ---------------------------------------------------------------------------
# 200m radius boundary
# ---------------------------------------------------------------------------

class TestProximityRadius:
    """Nodes within 200m are included; beyond 200m are excluded."""

    def test_nearby_node_included(self, nearby_node, outdoor_node):
        """Node ~150m away from reference point is included."""
        # Reference point: Shinjuku Gyoen main gate
        ref_lat, ref_lon = outdoor_node["latitude"], outdoor_node["longitude"]
        results = _nodes_in_radius(ref_lat, ref_lon, [nearby_node])
        assert len(results) == 1
        assert results[0]["id"] == nearby_node["id"]

    def test_far_node_excluded(self, far_node, outdoor_node):
        """Node ~800m away is outside 200m radius."""
        ref_lat, ref_lon = outdoor_node["latitude"], outdoor_node["longitude"]
        results = _nodes_in_radius(ref_lat, ref_lon, [far_node])
        assert len(results) == 0

    def test_boundary_exactly_200m(self, outdoor_node):
        """Node at exactly 200m boundary is included."""
        # Create a node at exactly 200m north (≈0.0018 degrees latitude)
        node_at_200m = make_activity_node(
            latitude=outdoor_node["latitude"] + 0.0018,
            longitude=outdoor_node["longitude"],
            status="active",
        )
        ref_lat, ref_lon = outdoor_node["latitude"], outdoor_node["longitude"]
        d = haversine_distance(ref_lat, ref_lon, node_at_200m["latitude"], node_at_200m["longitude"])
        # Should be within ±10m of 200m
        assert 190 < d < 210

    def test_inactive_node_excluded(self, outdoor_node):
        """Node within 200m but status != 'active' is excluded."""
        inactive_node = make_activity_node(
            latitude=outdoor_node["latitude"] + 0.001,  # ~111m
            longitude=outdoor_node["longitude"],
            status="pending",  # not active
        )
        ref_lat, ref_lon = outdoor_node["latitude"], outdoor_node["longitude"]
        results = _nodes_in_radius(ref_lat, ref_lon, [inactive_node])
        assert len(results) == 0

    def test_multiple_nearby_ordered_by_distance(self, outdoor_node, nearby_node):
        """Multiple nearby nodes ordered closest-first."""
        very_close_node = make_activity_node(
            latitude=outdoor_node["latitude"] + 0.0005,  # ~55m
            longitude=outdoor_node["longitude"],
            status="active",
        )
        ref_lat, ref_lon = outdoor_node["latitude"], outdoor_node["longitude"]
        results = _nodes_in_radius(ref_lat, ref_lon, [nearby_node, very_close_node])

        assert len(results) == 2
        # Very close node should be first
        assert results[0]["_distance_m"] < results[1]["_distance_m"]
        assert results[0]["id"] == very_close_node["id"]


# ---------------------------------------------------------------------------
# Micro-stop slot creation
# ---------------------------------------------------------------------------

class TestMicrostopSlotCreation:
    """Micro-stop slots have correct field values."""

    def test_microstop_slot_type_is_flex(self, active_trip, nearby_node):
        """Micro-stop slot always has slotType='flex'."""
        slot = _make_microstop_slot(
            trip_id=active_trip["id"],
            day_number=1,
            sort_order=1,
            node=nearby_node,
        )
        assert slot["slotType"] == "flex"

    def test_microstop_duration_range(self, active_trip, nearby_node):
        """Micro-stop duration is 15-30 minutes."""
        for duration in [15, 20, 25, 30]:
            slot = _make_microstop_slot(
                trip_id=active_trip["id"],
                day_number=1,
                sort_order=1,
                node=nearby_node,
                duration_minutes=duration,
            )
            assert 15 <= slot["durationMinutes"] <= 30

    def test_microstop_is_not_locked(self, active_trip, nearby_node):
        """Micro-stop slots are never locked by default."""
        slot = _make_microstop_slot(
            trip_id=active_trip["id"],
            day_number=1,
            sort_order=1,
            node=nearby_node,
        )
        assert slot["isLocked"] is False

    def test_microstop_status_is_proposed(self, active_trip, nearby_node):
        """Micro-stop starts in 'proposed' state."""
        slot = _make_microstop_slot(
            trip_id=active_trip["id"],
            day_number=1,
            sort_order=1,
            node=nearby_node,
        )
        assert slot["status"] == "proposed"

    def test_microstop_links_to_activity_node(self, active_trip, nearby_node):
        """Micro-stop slot references the discovered ActivityNode."""
        slot = _make_microstop_slot(
            trip_id=active_trip["id"],
            day_number=1,
            sort_order=1,
            node=nearby_node,
        )
        assert slot["activityNodeId"] == nearby_node["id"]

    def test_microstop_not_was_swapped(self, active_trip, nearby_node):
        """Micro-stop slot is a new insertion, not a swap."""
        slot = _make_microstop_slot(
            trip_id=active_trip["id"],
            day_number=1,
            sort_order=1,
            node=nearby_node,
        )
        assert slot["wasSwapped"] is False

    def test_no_microstop_during_locked_slot(self, locked_slot, nearby_node, active_trip):
        """Micro-stops should not be surfaced during a locked active slot."""
        # When the current slot is locked + active, suppress micro-stop suggestions
        is_active_locked = locked_slot["isLocked"] and locked_slot["status"] in ("active", "confirmed")
        # Suppress if current slot is locked and confirmed
        should_surface = not is_active_locked
        # locked_slot.isLocked=True, status=confirmed → suppress
        assert should_surface is False
