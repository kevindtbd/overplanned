"""
Phase 6.10 -- GPS Feature Integration (DATA-GATED)

GPS pings are NEVER uploaded. Only compressed stay points are computed
client-side and sent up. Used to upgrade `likely_attended` to
`confirmed_attended` signals.

DATA-GATED: Requires v2 mobile app with GPS stay-point upload.
Full feature extraction logic is built but not-yet-active.

Raw GPS pings are never persisted. Only StayPoints. StayPoints retained
90 days post-trip.

CPU-only: pure numpy / math, no PyTorch/TensorFlow.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime

import numpy as np

logger = logging.getLogger(__name__)

# Earth radius in meters
_EARTH_RADIUS_M = 6_371_000


@dataclass(frozen=True)
class GPSConfig:
    """Configuration for GPS feature extraction."""

    stay_radius_meters: float = 100.0
    stay_duration_minutes: float = 15.0
    max_speed_kmh: float = 5.0


@dataclass
class StayPoint:
    """A compressed stay point derived from GPS pings.

    Raw pings are never stored. Only StayPoints are retained, for 90 days
    post-trip.
    """

    lat: float
    lng: float
    arrival_time: datetime
    departure_time: datetime
    duration_minutes: float


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Compute haversine distance between two points in meters.

    Standard haversine formula, pure math. No external libs.

    Args:
        lat1, lng1: First point (decimal degrees)
        lat2, lng2: Second point (decimal degrees)

    Returns:
        Distance in meters.
    """
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS_M * c


class GPSFeatureExtractor:
    """Extract stay points from GPS pings and upgrade completion signals.

    DATA-GATED: Returns empty results until GPS_FEATURES_ENABLED env var
    is set and the v2 mobile app starts uploading stay points.
    """

    def __init__(self, config: GPSConfig | None = None) -> None:
        self.config = config or GPSConfig()

    def is_active(self) -> bool:
        """Check if GPS features are enabled via feature flag."""
        return os.environ.get("GPS_FEATURES_ENABLED", "").lower() in ("1", "true", "yes")

    def extract_stay_points(self, gps_pings: list[dict]) -> list[StayPoint]:
        """Extract stay points from sequential GPS pings.

        Clusters sequential pings within stay_radius_meters, then keeps only
        clusters with duration >= stay_duration_minutes.

        Each ping dict must have: lat (float), lng (float), timestamp (datetime).

        Args:
            gps_pings: Chronologically ordered list of GPS ping dicts.

        Returns:
            List of StayPoint instances.
        """
        if not gps_pings:
            return []

        stay_points: list[StayPoint] = []
        cluster: list[dict] = [gps_pings[0]]

        for ping in gps_pings[1:]:
            # Check distance from cluster centroid
            centroid_lat = np.mean([p["lat"] for p in cluster])
            centroid_lng = np.mean([p["lng"] for p in cluster])

            dist = haversine_distance(
                centroid_lat, centroid_lng, ping["lat"], ping["lng"]
            )

            if dist <= self.config.stay_radius_meters:
                cluster.append(ping)
            else:
                # Finalize current cluster if it qualifies
                sp = self._finalize_cluster(cluster)
                if sp is not None:
                    stay_points.append(sp)
                # Start new cluster
                cluster = [ping]

        # Finalize last cluster
        sp = self._finalize_cluster(cluster)
        if sp is not None:
            stay_points.append(sp)

        return stay_points

    def _finalize_cluster(self, cluster: list[dict]) -> StayPoint | None:
        """Convert a cluster of pings to a StayPoint if duration qualifies."""
        if not cluster:
            return None

        arrival = cluster[0]["timestamp"]
        departure = cluster[-1]["timestamp"]
        duration_minutes = (departure - arrival).total_seconds() / 60.0

        if duration_minutes < self.config.stay_duration_minutes:
            return None

        lat = float(np.mean([p["lat"] for p in cluster]))
        lng = float(np.mean([p["lng"] for p in cluster]))

        return StayPoint(
            lat=lat,
            lng=lng,
            arrival_time=arrival,
            departure_time=departure,
            duration_minutes=duration_minutes,
        )

    def match_stay_to_slot(
        self,
        stay_point: StayPoint,
        slot_lat: float,
        slot_lng: float,
        slot_start: datetime,
        slot_end: datetime,
    ) -> bool:
        """Check if a stay point matches a slot's location and time.

        Match criteria:
          - Haversine distance < stay_radius_meters
          - Time overlap between stay point and slot

        Args:
            stay_point: The stay point to check.
            slot_lat, slot_lng: Slot location.
            slot_start, slot_end: Slot time window.

        Returns:
            True if the stay point matches the slot.
        """
        dist = haversine_distance(
            stay_point.lat, stay_point.lng, slot_lat, slot_lng
        )
        if dist >= self.config.stay_radius_meters:
            return False

        # Check time overlap
        latest_start = max(stay_point.arrival_time, slot_start)
        earliest_end = min(stay_point.departure_time, slot_end)
        return latest_start < earliest_end

    def upgrade_completion_signals(
        self,
        stay_points: list[StayPoint],
        slots: list[dict],
    ) -> list[dict]:
        """Upgrade likely_attended signals to confirmed_attended where stay points match.

        For each slot with status 'likely_attended', checks if a stay point
        matches. If matched, produces an upgrade signal with signal_weight 1.0.

        Each slot dict must have: id, lat, lng, start_time, end_time, status.

        Args:
            stay_points: List of StayPoint instances from the trip.
            slots: List of slot dicts with location and time data.

        Returns:
            List of upgrade signal dicts ready for insertion.
        """
        if not self.is_active():
            return []

        upgrades: list[dict] = []
        for slot in slots:
            if slot.get("status") != "likely_attended":
                continue

            for sp in stay_points:
                if self.match_stay_to_slot(
                    sp,
                    slot["lat"],
                    slot["lng"],
                    slot["start_time"],
                    slot["end_time"],
                ):
                    upgrades.append({
                        "slot_id": slot["id"],
                        "signal_type": "confirmed_attended",
                        "signal_value": 1.0,
                        "signal_weight": 1.0,
                        "stay_point": {
                            "lat": sp.lat,
                            "lng": sp.lng,
                            "arrival_time": sp.arrival_time.isoformat(),
                            "departure_time": sp.departure_time.isoformat(),
                            "duration_minutes": sp.duration_minutes,
                        },
                    })
                    break  # One match per slot is sufficient

        return upgrades
