"""
Spatial queries for micro-stop discovery.

Uses PostGIS to find ActivityNodes within 200m of the straight-line transit
path between two geographic waypoints.

PostGIS functions used:
  ST_MakeLine       — construct a linestring from two points
  ST_Buffer         — create a 200m buffer in EPSG:3857 (meters), cast back
  ST_Transform      — reproject between EPSG:4326 (lon/lat) and EPSG:3857
  ST_MakePoint      — construct a point from longitude, latitude
  ST_SetSRID        — assign SRID to geometry
  ST_DWithin        — fast distance filter using GIST index

The GIST index on activity_nodes (created in add_gist_index.sql) accelerates
all spatial queries here.

Filtering rules:
  - Only 'approved' ActivityNodes
  - Exclude the origin and destination nodes themselves
  - Exclude nodes already present in the trip itinerary for that day
  - Maximum 5 results per transit segment, ranked by convergenceScore DESC
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Buffer radius in meters around the transit path
TRANSIT_BUFFER_METERS = 200

# Maximum candidates returned per transit segment
MAX_CANDIDATES = 5

# Minimum convergence score threshold for micro-stop candidates
MIN_CONVERGENCE_SCORE = 0.4


@dataclass
class SpatialCandidate:
    """An ActivityNode candidate returned by spatial query."""

    activity_node_id: str
    name: str
    latitude: float
    longitude: float
    category: str
    price_level: int | None
    convergence_score: float | None
    description_short: str | None
    primary_image_url: str | None
    neighborhood: str | None
    duration_minutes: int | None  # estimated, sourced from category defaults


# Rough default durations by category for micro-stop scheduling
_CATEGORY_DEFAULT_DURATION: dict[str, int] = {
    "dining": 30,
    "drinks": 20,
    "culture": 25,
    "outdoors": 20,
    "active": 30,
    "entertainment": 30,
    "shopping": 20,
    "experience": 25,
    "nightlife": 25,
    "wellness": 20,
}
_DEFAULT_MICRO_DURATION = 20


def _estimate_duration(category: str) -> int:
    """Return a reasonable micro-stop duration for a given category."""
    return min(30, max(15, _CATEGORY_DEFAULT_DURATION.get(category, _DEFAULT_MICRO_DURATION)))


async def find_nodes_along_path(
    *,
    db: Any,
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
    trip_id: str,
    day_number: int,
    exclude_node_ids: list[str] | None = None,
) -> list[SpatialCandidate]:
    """
    Find approved ActivityNodes within TRANSIT_BUFFER_METERS of the transit
    path from (origin_lat, origin_lon) to (destination_lat, destination_lon).

    Uses the GIST index on (ST_MakePoint(longitude, latitude)) for fast
    bounding box pre-filtering via ST_DWithin before the exact buffer check.

    Args:
        db: asyncpg connection / pool.
        origin_lat, origin_lon: Starting point of the transit segment.
        destination_lat, destination_lon: Ending point.
        trip_id: Used to exclude nodes already in today's itinerary.
        day_number: Today's day number for exclusion query.
        exclude_node_ids: Additional node IDs to exclude (e.g. origin/dest nodes).

    Returns:
        Up to MAX_CANDIDATES SpatialCandidate objects ranked by convergenceScore.
    """
    excluded = list(exclude_node_ids or [])

    # Fetch nodes already scheduled today to avoid duplication
    already_scheduled = await db.fetch(
        """
        SELECT "activityNodeId"
        FROM "ItinerarySlot"
        WHERE "tripId" = $1
          AND "dayNumber" = $2
          AND "activityNodeId" IS NOT NULL
          AND status NOT IN ('skipped', 'completed')
        """,
        trip_id,
        day_number,
    )
    excluded.extend(row["activityNodeId"] for row in already_scheduled if row["activityNodeId"])

    # Deduplicate exclusion list
    excluded_set = list(set(excluded))

    try:
        rows = await db.fetch(
            """
            WITH transit_path AS (
                SELECT ST_Transform(
                    ST_SetSRID(
                        ST_MakeLine(
                            ST_MakePoint($1, $2),
                            ST_MakePoint($3, $4)
                        ),
                        4326
                    ),
                    3857
                ) AS path_3857
            ),
            buffered AS (
                SELECT ST_Transform(
                    ST_Buffer(path_3857, $5),
                    4326
                ) AS zone
                FROM transit_path
            )
            SELECT
                an.id,
                an.name,
                an.latitude,
                an.longitude,
                an.category,
                an."priceLevel",
                an."convergenceScore",
                an."descriptionShort",
                an."primaryImageUrl",
                an.neighborhood
            FROM "ActivityNode" an, buffered
            WHERE
                an.status = 'approved'
                AND an."isCanonical" = true
                AND (an."convergenceScore" IS NULL OR an."convergenceScore" >= $6)
                AND (
                    $7::text[] IS NULL
                    OR array_length($7::text[], 1) = 0
                    OR an.id != ALL($7::text[])
                )
                AND ST_Within(
                    ST_SetSRID(ST_MakePoint(an.longitude, an.latitude), 4326),
                    buffered.zone
                )
            ORDER BY an."convergenceScore" DESC NULLS LAST
            LIMIT $8
            """,
            origin_lon,
            origin_lat,
            destination_lon,
            destination_lat,
            TRANSIT_BUFFER_METERS,
            MIN_CONVERGENCE_SCORE,
            excluded_set if excluded_set else None,
            MAX_CANDIDATES,
        )
    except Exception:
        logger.exception(
            "Spatial query failed for path (%f,%f)->(%f,%f)",
            origin_lat,
            origin_lon,
            destination_lat,
            destination_lon,
        )
        return []

    candidates: list[SpatialCandidate] = []
    for row in rows:
        cat = row["category"]
        candidates.append(
            SpatialCandidate(
                activity_node_id=row["id"],
                name=row["name"],
                latitude=row["latitude"],
                longitude=row["longitude"],
                category=cat,
                price_level=row["priceLevel"],
                convergence_score=row["convergenceScore"],
                description_short=row["descriptionShort"],
                primary_image_url=row["primaryImageUrl"],
                neighborhood=row["neighborhood"],
                duration_minutes=_estimate_duration(cat),
            )
        )

    logger.info(
        "Spatial query: path (%f,%f)->(%f,%f) buffer=%dm found=%d",
        origin_lat,
        origin_lon,
        destination_lat,
        destination_lon,
        TRANSIT_BUFFER_METERS,
        len(candidates),
    )

    return candidates
