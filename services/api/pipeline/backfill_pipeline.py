"""
Backfill ingestion pipeline — async processor.

Entry point: process_backfill(pool, backfill_trip_id)

Stages:
  1.   Source classification  — Haiku tier detection
  1.5  City extraction        — Haiku multi-city route detection + BackfillLeg creation
  2.   LLM extraction         — Sonnet tool-use venue extraction (multi-city aware)
  2.5  LLM validation         — Haiku plausibility gate
  3.   Entity resolution      — pg_trgm similarity against ActivityNode (per-venue city)
  3.5  Venue-to-leg assignment — deterministic city match
  4.   Anomaly checks         — geographic, temporal, density, duplicate flags
  5.   Signal generation      — BackfillSignal rows weighted by tier

Each stage writes BackfillTrip.status before doing work so crash recovery
knows where to resume (or at minimum, where the job died).

Status progression:
  processing → extracting → resolving → checking → complete | rejected
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import anthropic
import asyncpg

from services.api.pipeline.backfill_llm import (
    ExtractedCity,
    ExtractedVenue,
    classify_submission,
    extract_cities,
    extract_venues,
    validate_venues,
)
from services.api.pipeline.entity_resolution import normalize_name

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# pg_trgm similarity threshold for entity resolution
RESOLUTION_THRESHOLD = 0.75

# Anomaly thresholds
GEO_IMPOSSIBLE_MILES = 500.0
TEMPORAL_MAX_VENUES_PER_DAY = 8
DENSITY_OUTLIER_PRICE_LEVEL = 4
DENSITY_OUTLIER_RATIO = 0.70

# Signal weights by tier
TIER_WEIGHTS = {
    "tier_2": 0.65,
    "tier_3": 0.40,
    "tier_4": 0.20,
}

# Quality gate: minimum extractable venues to proceed
MIN_VENUES_FOR_PROCEED = 3


# ---------------------------------------------------------------------------
# Haversine
# ---------------------------------------------------------------------------

def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Return great-circle distance in miles between two lat/lng points.
    Uses Python math library only — no external dependencies.
    """
    R = 3_958.8  # Earth radius in miles

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------

@dataclass
class ResolvedVenue:
    """Extraction result after entity resolution."""
    extracted: ExtractedVenue
    activity_node_id: Optional[str]
    resolution_score: Optional[float]
    is_resolved: bool
    latitude: Optional[float]
    longitude: Optional[float]
    price_level: Optional[int]
    backfill_leg_id: Optional[str] = None  # set during venue-to-leg assignment


@dataclass
class CheckedVenue:
    """Post-anomaly-check venue state."""
    resolved: ResolvedVenue
    is_quarantined: bool
    quarantine_reason: Optional[str]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _update_status(conn: asyncpg.Connection, backfill_trip_id: str, status: str) -> None:
    """Write BackfillTrip.status before each stage (crash recovery anchor)."""
    await conn.execute(
        """
        UPDATE backfill_trips
        SET status = $1, "updatedAt" = NOW()
        WHERE id = $2
        """,
        status,
        backfill_trip_id,
    )


async def _update_confidence_tier(
    conn: asyncpg.Connection, backfill_trip_id: str, tier: str
) -> None:
    await conn.execute(
        """
        UPDATE backfill_trips
        SET "confidenceTier" = $1, "updatedAt" = NOW()
        WHERE id = $2
        """,
        tier,
        backfill_trip_id,
    )


async def _fetch_backfill_trip(
    conn: asyncpg.Connection, backfill_trip_id: str
) -> Optional[dict]:
    row = await conn.fetchrow(
        """
        SELECT bt.id, bt."userId", bt."rawSubmission",
               bt."confidenceTier", bt.status,
               bl.city, bl.country
        FROM backfill_trips bt
        LEFT JOIN backfill_legs bl
          ON bl."backfillTripId" = bt.id
          AND bl.position = 0
        WHERE bt.id = $1
        """,
        backfill_trip_id,
    )
    return dict(row) if row else None


async def _reject_trip(
    conn: asyncpg.Connection, backfill_trip_id: str, reason: str
) -> None:
    await conn.execute(
        """
        UPDATE backfill_trips
        SET status = 'rejected',
            "rejectionReason" = $1,
            "updatedAt" = NOW()
        WHERE id = $2
        """,
        reason,
        backfill_trip_id,
    )


# ---------------------------------------------------------------------------
# Stage 1.5 helpers: city extraction + leg creation
# ---------------------------------------------------------------------------

async def _create_or_update_legs(
    conn: asyncpg.Connection,
    backfill_trip_id: str,
    extracted_cities: list[ExtractedCity],
) -> list[dict]:
    """
    Synchronize BackfillLeg rows for this trip against the extracted city list.

    The router already created a leg at position=0 with a provisional city_hint.
    Strategy:
    - If extraction returned 1 city: UPDATE leg[0] with the extracted city/country.
    - If extraction returned N cities: UPDATE leg[0] with the first city, then
      INSERT legs at positions 1..N-1.
    - If extraction returned 0 cities: do nothing — leg[0] stays as created by
      the router (city = cityHint or "unknown").

    Returns the final list of leg dicts: [{ id, position, city, country }, ...]
    sorted by position ascending.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if extracted_cities:
        # Update leg[0] with the first extracted city
        first = extracted_cities[0]
        await conn.execute(
            """
            UPDATE backfill_legs
            SET city = $1, country = $2
            WHERE "backfillTripId" = $3 AND position = 0
            """,
            first.city,
            first.country,
            backfill_trip_id,
        )
        logger.info(
            "_create_or_update_legs: updated leg[0] to city=%r country=%r trip=%s",
            first.city, first.country, backfill_trip_id,
        )

        # Insert additional legs for positions 1..N-1
        for ec in extracted_cities[1:]:
            leg_id = str(uuid4())
            await conn.execute(
                """
                INSERT INTO backfill_legs (
                    id, "backfillTripId", position, city, country, "createdAt"
                ) VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT ("backfillTripId", position) DO UPDATE
                  SET city = EXCLUDED.city, country = EXCLUDED.country
                """,
                leg_id,
                backfill_trip_id,
                ec.position,
                ec.city,
                ec.country,
                now,
            )
            logger.info(
                "_create_or_update_legs: upserted leg position=%d city=%r trip=%s",
                ec.position, ec.city, backfill_trip_id,
            )

    # Fetch and return current legs for this trip
    rows = await conn.fetch(
        """
        SELECT id, position, city, country
        FROM backfill_legs
        WHERE "backfillTripId" = $1
        ORDER BY position ASC
        """,
        backfill_trip_id,
    )
    legs = [dict(r) for r in rows]
    logger.info(
        "_create_or_update_legs: trip=%s final legs=%s",
        backfill_trip_id,
        [(l["position"], l["city"]) for l in legs],
    )
    return legs


def _assign_venues_to_legs(
    resolved_venues: list[ResolvedVenue],
    legs: list[dict],
) -> list[ResolvedVenue]:
    """
    Assign each ResolvedVenue to a BackfillLeg by matching venue.extracted.city
    to leg.city (case-insensitive). First matching leg wins.

    If no leg matches, backfill_leg_id stays None — the venue remains assigned
    to the trip but not to a specific leg.

    Returns the same list with backfill_leg_id populated in-place.
    """
    if not legs:
        return resolved_venues

    # Build a lookup: city_lower -> leg_id (first match by position)
    city_to_leg: dict[str, str] = {}
    for leg in sorted(legs, key=lambda l: l["position"]):
        key = leg["city"].strip().lower()
        if key not in city_to_leg:
            city_to_leg[key] = leg["id"]

    for rv in resolved_venues:
        venue_city = rv.extracted.city
        if not venue_city:
            continue
        key = venue_city.strip().lower()
        leg_id = city_to_leg.get(key)
        if leg_id:
            rv.backfill_leg_id = leg_id

    assigned = sum(1 for rv in resolved_venues if rv.backfill_leg_id is not None)
    logger.info(
        "_assign_venues_to_legs: assigned %d/%d venues to legs",
        assigned, len(resolved_venues),
    )
    return resolved_venues


# ---------------------------------------------------------------------------
# Stage 3: Entity resolution
# ---------------------------------------------------------------------------

async def _resolve_single_venue(
    conn: asyncpg.Connection,
    venue: ExtractedVenue,
    city: str,
) -> ResolvedVenue:
    """
    Resolve one venue against ActivityNode using pg_trgm similarity.

    Strategy:
      1. Try with category filter (more precise)
      2. Retry without category if no match above threshold
    Threshold: 0.75 similarity.
    """
    normalized = normalize_name(venue.name)
    if not normalized:
        return ResolvedVenue(
            extracted=venue,
            activity_node_id=None,
            resolution_score=None,
            is_resolved=False,
            latitude=None,
            longitude=None,
            price_level=None,
        )

    # Attempt 1: city + category scoped
    row = None
    if venue.category:
        row = await conn.fetchrow(
            """
            SELECT id, latitude, longitude, "priceLevel",
                   similarity("canonicalName", $1) AS sim
            FROM activity_nodes
            WHERE "isCanonical" = true
              AND lower(city) = lower($2)
              AND category = $3
              AND similarity("canonicalName", $1) > $4
            ORDER BY sim DESC
            LIMIT 1
            """,
            normalized,
            city,
            venue.category,
            RESOLUTION_THRESHOLD,
        )

    # Attempt 2: city only (drop category filter)
    if row is None:
        row = await conn.fetchrow(
            """
            SELECT id, latitude, longitude, "priceLevel",
                   similarity("canonicalName", $1) AS sim
            FROM activity_nodes
            WHERE "isCanonical" = true
              AND lower(city) = lower($2)
              AND similarity("canonicalName", $1) > $3
            ORDER BY sim DESC
            LIMIT 1
            """,
            normalized,
            city,
            RESOLUTION_THRESHOLD,
        )

    if row is None:
        return ResolvedVenue(
            extracted=venue,
            activity_node_id=None,
            resolution_score=None,
            is_resolved=False,
            latitude=None,
            longitude=None,
            price_level=None,
        )

    return ResolvedVenue(
        extracted=venue,
        activity_node_id=str(row["id"]),
        resolution_score=float(row["sim"]),
        is_resolved=True,
        latitude=row["latitude"],
        longitude=row["longitude"],
        price_level=row["priceLevel"],
    )


# ---------------------------------------------------------------------------
# Stage 4: Anomaly checks
# ---------------------------------------------------------------------------

def _check_geographic_impossibility(resolved_venues: list[ResolvedVenue]) -> dict[str, str]:
    """
    Flag venue pairs that are >500 miles apart on the same date AND in the same city.

    Cross-city venue pairs on the same date are exempt — this is expected behavior
    for transit days in multi-city trips (e.g. morning in Tokyo, evening in Kyoto).
    Grouping uses venue.extracted.city (from Sonnet extraction) as the city key.

    Returns a dict of venue index -> quarantine reason for flagged venues.
    """
    quarantine: dict[str, str] = {}

    # Group resolved venues by (date_or_range, city) — cross-city pairs are exempt
    by_date_city: dict[tuple[str, str], list[tuple[int, ResolvedVenue]]] = {}
    for i, rv in enumerate(resolved_venues):
        date_key = rv.extracted.date_or_range or "_no_date"
        city_key = (rv.extracted.city or "_no_city").strip().lower()
        bucket = (date_key, city_key)
        if bucket not in by_date_city:
            by_date_city[bucket] = []
        by_date_city[bucket].append((i, rv))

    for (date_key, city_key), group in by_date_city.items():
        if date_key == "_no_date" or len(group) < 2:
            continue

        # Only check resolved venues (need lat/lng)
        geo_group = [
            (i, rv) for i, rv in group
            if rv.is_resolved and rv.latitude is not None and rv.longitude is not None
        ]

        for a_idx in range(len(geo_group)):
            for b_idx in range(a_idx + 1, len(geo_group)):
                i, rv_a = geo_group[a_idx]
                j, rv_b = geo_group[b_idx]
                dist = haversine_miles(
                    rv_a.latitude, rv_a.longitude,  # type: ignore[arg-type]
                    rv_b.latitude, rv_b.longitude,  # type: ignore[arg-type]
                )
                if dist > GEO_IMPOSSIBLE_MILES:
                    reason = (
                        f"geographic_impossibility: {rv_a.extracted.name!r} and "
                        f"{rv_b.extracted.name!r} are {dist:.0f} miles apart "
                        f"on same date {date_key!r} in city {city_key!r}"
                    )
                    quarantine[str(i)] = reason
                    quarantine[str(j)] = reason

    return quarantine


def _check_temporal_impossibility(resolved_venues: list[ResolvedVenue]) -> dict[str, str]:
    """Flag venues when >8 venues appear on a single date."""
    quarantine: dict[str, str] = {}

    by_date: dict[str, list[int]] = {}
    for i, rv in enumerate(resolved_venues):
        date_key = rv.extracted.date_or_range or "_no_date"
        if date_key == "_no_date":
            continue
        if date_key not in by_date:
            by_date[date_key] = []
        by_date[date_key].append(i)

    for date_key, indices in by_date.items():
        if len(indices) > TEMPORAL_MAX_VENUES_PER_DAY:
            reason = (
                f"temporal_impossibility: {len(indices)} venues on date {date_key!r} "
                f"(max {TEMPORAL_MAX_VENUES_PER_DAY})"
            )
            for i in indices:
                quarantine[str(i)] = reason

    return quarantine


def _check_density_outlier(resolved_venues: list[ResolvedVenue]) -> dict[str, str]:
    """Flag the whole submission if >70% of resolved venues are priceLevel 4+."""
    quarantine: dict[str, str] = {}

    resolved_with_price = [
        (i, rv) for i, rv in enumerate(resolved_venues)
        if rv.is_resolved and rv.price_level is not None
    ]

    if not resolved_with_price:
        return quarantine

    high_price = sum(
        1 for _, rv in resolved_with_price
        if rv.price_level >= DENSITY_OUTLIER_PRICE_LEVEL
    )
    ratio = high_price / len(resolved_with_price)

    if ratio > DENSITY_OUTLIER_RATIO:
        reason = (
            f"density_outlier: {high_price}/{len(resolved_with_price)} "
            f"({ratio:.0%}) venues are priceLevel {DENSITY_OUTLIER_PRICE_LEVEL}+"
        )
        for i, _ in resolved_with_price:
            quarantine[str(i)] = reason

    return quarantine


async def _check_duplicate_submission(
    conn: asyncpg.Connection,
    user_id: str,
    city: str,
    start_date: Optional[datetime],
    end_date: Optional[datetime],
    current_backfill_id: str,
) -> Optional[str]:
    """
    Return a quarantine reason string if a near-duplicate BackfillTrip exists
    for this user+city with overlapping dates. Returns None if clean.
    """
    row = await conn.fetchrow(
        """
        SELECT bt.id FROM backfill_trips bt
        JOIN backfill_legs bl
          ON bl."backfillTripId" = bt.id
          AND bl.position = 0
        WHERE bt."userId" = $1
          AND lower(bl.city) = lower($2)
          AND bt.id != $3
          AND bt.status NOT IN ('rejected', 'archived')
        LIMIT 1
        """,
        user_id,
        city,
        current_backfill_id,
    )
    if row is None:
        return None

    return (
        f"duplicate: existing backfill {row['id']!r} covers same user+city "
        f"({city!r})"
    )


# ---------------------------------------------------------------------------
# DB writes for venues and signals
# ---------------------------------------------------------------------------

async def _write_venues(
    conn: asyncpg.Connection,
    backfill_trip_id: str,
    checked_venues: list[CheckedVenue],
) -> list[str]:
    """
    Insert BackfillVenue rows. Returns list of inserted venue IDs
    in the same order as checked_venues.
    """
    venue_ids: list[str] = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for cv in checked_venues:
        rv = cv.resolved
        ev = rv.extracted
        venue_id = str(uuid4())

        await conn.execute(
            """
            INSERT INTO backfill_venues (
                id, "backfillTripId", "backfillLegId", "activityNodeId",
                "extractedName", "extractedCategory", "extractedDate",
                "extractedSentiment", latitude, longitude,
                "resolutionScore", "isResolved",
                "isQuarantined", "quarantineReason",
                "createdAt", "updatedAt"
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9,
                $10, $11, $12, $13, $14, $15, $15
            )
            """,
            venue_id,
            backfill_trip_id,
            rv.backfill_leg_id,  # populated by _assign_venues_to_legs, or None
            rv.activity_node_id,
            ev.name,
            ev.category,
            ev.date_or_range,
            ev.sentiment,
            rv.latitude,
            rv.longitude,
            rv.resolution_score,
            rv.is_resolved,
            cv.is_quarantined,
            cv.quarantine_reason,
            now,
        )
        venue_ids.append(venue_id)

    return venue_ids


async def _write_signals(
    conn: asyncpg.Connection,
    user_id: str,
    backfill_trip_id: str,
    confidence_tier: str,
    checked_venues: list[CheckedVenue],
    venue_ids: list[str],
) -> int:
    """
    Insert BackfillSignal rows for clean, resolved, non-quarantined venues.
    Returns number of signals written.
    """
    weight = TIER_WEIGHTS.get(confidence_tier, TIER_WEIGHTS["tier_4"])
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    count = 0

    for cv, venue_id in zip(checked_venues, venue_ids):
        rv = cv.resolved
        ev = rv.extracted

        # Only clean, resolved, non-quarantined venues generate signals
        if cv.is_quarantined or not rv.is_resolved:
            continue

        # signalType comes from extracted category, or falls back to "experience"
        signal_type = ev.category or "experience"

        # signalValue: encode sentiment as 0-1 float
        sentiment_map = {"positive": 1.0, "neutral": 0.5, "negative": 0.0}
        signal_value = sentiment_map.get(ev.sentiment or "", 0.5)

        signal_id = str(uuid4())
        await conn.execute(
            """
            INSERT INTO backfill_signals (
                id, "userId", "backfillTripId", "backfillVenueId",
                "signalType", "signalValue", "confidenceTier",
                weight, "earnedOut", "createdAt", "updatedAt"
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, false, $9, $9
            )
            """,
            signal_id,
            user_id,
            backfill_trip_id,
            venue_id,
            signal_type,
            signal_value,
            confidence_tier,
            weight,
            now,
        )
        count += 1

    return count


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

async def process_backfill(pool: asyncpg.Pool, backfill_trip_id: str) -> None:
    """
    Run the 5-stage backfill pipeline for a single BackfillTrip.

    Stages update BackfillTrip.status before doing work so any crash leaves
    a recoverable breadcrumb. On rejection, status is set to 'rejected' with
    a reason. On success, status is set to 'complete'.
    """
    anthropic_client = anthropic.AsyncAnthropic()  # reads ANTHROPIC_API_KEY from env

    async with pool.acquire() as conn:
        # ------------------------------------------------------------------
        # Load the BackfillTrip
        # ------------------------------------------------------------------
        trip = await _fetch_backfill_trip(conn, backfill_trip_id)
        if trip is None:
            logger.error(
                "process_backfill: BackfillTrip %s not found — aborting",
                backfill_trip_id,
            )
            return

        user_id: str = trip["userId"]
        # city comes from leg[0] via the LEFT JOIN in _fetch_backfill_trip.
        # May be None if no leg exists yet (defensive fallback).
        city_hint: Optional[str] = trip.get("city") or None
        raw_text: str = trip["rawSubmission"]

        logger.info(
            "process_backfill: starting pipeline for trip=%s user=%s city_hint=%s",
            backfill_trip_id,
            user_id,
            city_hint,
        )

        # ------------------------------------------------------------------
        # Stage 1: Source classification
        # ------------------------------------------------------------------
        await _update_status(conn, backfill_trip_id, "processing")

        try:
            tier = await classify_submission(anthropic_client, raw_text)
        except Exception as exc:
            logger.exception(
                "process_backfill: stage 1 classify failed for %s: %s",
                backfill_trip_id, exc,
            )
            tier = "tier_4"  # degrade gracefully

        await _update_confidence_tier(conn, backfill_trip_id, tier)
        logger.info(
            "process_backfill: stage 1 complete tier=%s trip=%s",
            tier, backfill_trip_id,
        )

        # ------------------------------------------------------------------
        # Stage 1.5: City extraction + BackfillLeg creation
        # ------------------------------------------------------------------
        extracted_cities: list[ExtractedCity] = []
        try:
            extracted_cities = await extract_cities(
                anthropic_client, raw_text, city_hint
            )
        except Exception as exc:
            logger.exception(
                "process_backfill: stage 1.5 city extraction failed for %s: %s",
                backfill_trip_id, exc,
            )
            # Fall through with empty list — legs stay as router created them

        # Create or update BackfillLeg rows based on extracted cities.
        # Falls back gracefully if extraction returned nothing.
        try:
            legs = await _create_or_update_legs(
                conn, backfill_trip_id, extracted_cities
            )
        except Exception as exc:
            logger.exception(
                "process_backfill: stage 1.5 leg creation failed for %s: %s",
                backfill_trip_id, exc,
            )
            # Fetch existing legs without modification
            rows = await conn.fetch(
                """
                SELECT id, position, city, country
                FROM backfill_legs
                WHERE "backfillTripId" = $1
                ORDER BY position ASC
                """,
                backfill_trip_id,
            )
            legs = [dict(r) for r in rows]

        # Derive the primary city context for venue extraction (first leg's city,
        # or fall back to city_hint, then "unknown")
        primary_city: str = (
            legs[0]["city"] if legs else (city_hint or "unknown")
        )

        logger.info(
            "process_backfill: stage 1.5 complete legs=%d primary_city=%r trip=%s",
            len(legs), primary_city, backfill_trip_id,
        )

        # ------------------------------------------------------------------
        # Stage 2: LLM extraction
        # ------------------------------------------------------------------
        await _update_status(conn, backfill_trip_id, "extracting")

        # Build cities context string for Sonnet (all extracted cities, or just
        # primary_city if extraction returned nothing)
        if legs:
            cities_context = ", ".join(l["city"] for l in legs)
        else:
            cities_context = primary_city

        try:
            venues = await extract_venues(anthropic_client, raw_text, cities_context)
        except Exception as exc:
            logger.exception(
                "process_backfill: stage 2 extraction failed for %s: %s",
                backfill_trip_id, exc,
            )
            await _reject_trip(conn, backfill_trip_id, "extraction_failed: LLM call error")
            return

        # Quality gate: need at least MIN_VENUES_FOR_PROCEED extractable venues
        # OR some temporal context present
        has_temporal = any(v.date_or_range for v in venues)
        if len(venues) < MIN_VENUES_FOR_PROCEED and not has_temporal:
            reason = (
                f"quality_gate: only {len(venues)} venues extracted "
                f"(min {MIN_VENUES_FOR_PROCEED}) and no temporal context"
            )
            logger.info(
                "process_backfill: quality gate reject trip=%s reason=%s",
                backfill_trip_id, reason,
            )
            await _reject_trip(conn, backfill_trip_id, reason)
            return

        logger.info(
            "process_backfill: stage 2 complete venues=%d trip=%s",
            len(venues), backfill_trip_id,
        )

        # ------------------------------------------------------------------
        # Stage 2.5: LLM validation
        # ------------------------------------------------------------------
        try:
            validated = await validate_venues(anthropic_client, venues, primary_city)
        except Exception as exc:
            logger.exception(
                "process_backfill: stage 2.5 validation failed for %s: %s",
                backfill_trip_id, exc,
            )
            # Fail open: treat all venues as validated
            validated = list(venues)

        # Filter out None (failed plausibility)
        valid_venues: list[ExtractedVenue] = [v for v in validated if v is not None]
        logger.info(
            "process_backfill: stage 2.5 complete valid=%d/%d trip=%s",
            len(valid_venues), len(venues), backfill_trip_id,
        )

        if not valid_venues:
            await _reject_trip(
                conn, backfill_trip_id,
                "quality_gate: all extracted venues failed plausibility validation"
            )
            return

        # ------------------------------------------------------------------
        # Stage 3: Entity resolution (per-venue city)
        # ------------------------------------------------------------------
        await _update_status(conn, backfill_trip_id, "resolving")

        resolved_venues: list[ResolvedVenue] = []
        for venue in valid_venues:
            # Resolve against the venue's own extracted city first;
            # fall back to primary_city if the venue has no city field.
            resolve_city = venue.city or primary_city
            try:
                rv = await _resolve_single_venue(conn, venue, resolve_city)
            except Exception as exc:
                logger.error(
                    "process_backfill: resolution failed for %r: %s",
                    venue.name, exc,
                )
                rv = ResolvedVenue(
                    extracted=venue,
                    activity_node_id=None,
                    resolution_score=None,
                    is_resolved=False,
                    latitude=None,
                    longitude=None,
                    price_level=None,
                )
            resolved_venues.append(rv)

        resolved_count = sum(1 for rv in resolved_venues if rv.is_resolved)
        logger.info(
            "process_backfill: stage 3 complete resolved=%d/%d trip=%s",
            resolved_count, len(resolved_venues), backfill_trip_id,
        )

        # ------------------------------------------------------------------
        # Stage 3.5: Venue-to-leg assignment
        # ------------------------------------------------------------------
        resolved_venues = _assign_venues_to_legs(resolved_venues, legs)

        # ------------------------------------------------------------------
        # Stage 4: Anomaly checks
        # ------------------------------------------------------------------
        await _update_status(conn, backfill_trip_id, "checking")

        geo_flags = _check_geographic_impossibility(resolved_venues)
        temporal_flags = _check_temporal_impossibility(resolved_venues)
        density_flags = _check_density_outlier(resolved_venues)

        # Duplicate submission check uses primary city (first leg)
        dup_reason = await _check_duplicate_submission(
            conn,
            user_id=user_id,
            city=primary_city,
            start_date=trip.get("startDate"),
            end_date=trip.get("endDate"),
            current_backfill_id=backfill_trip_id,
        )

        # Assemble checked venues
        checked_venues: list[CheckedVenue] = []
        for i, rv in enumerate(resolved_venues):
            idx = str(i)
            reasons: list[str] = []

            if idx in geo_flags:
                reasons.append(geo_flags[idx])
            if idx in temporal_flags:
                reasons.append(temporal_flags[idx])
            if idx in density_flags:
                reasons.append(density_flags[idx])
            if dup_reason:
                reasons.append(dup_reason)

            if reasons:
                cv = CheckedVenue(
                    resolved=rv,
                    is_quarantined=True,
                    quarantine_reason="; ".join(reasons),
                )
            else:
                cv = CheckedVenue(
                    resolved=rv,
                    is_quarantined=False,
                    quarantine_reason=None,
                )
            checked_venues.append(cv)

        quarantined_count = sum(1 for cv in checked_venues if cv.is_quarantined)
        logger.info(
            "process_backfill: stage 4 complete quarantined=%d/%d trip=%s",
            quarantined_count, len(checked_venues), backfill_trip_id,
        )

        # ------------------------------------------------------------------
        # Stage 5: Signal generation + persist everything in one transaction
        # ------------------------------------------------------------------
        async with conn.transaction():
            # Write venues
            venue_ids = await _write_venues(conn, backfill_trip_id, checked_venues)

            # Write signals for clean resolved venues
            signal_count = await _write_signals(
                conn,
                user_id=user_id,
                backfill_trip_id=backfill_trip_id,
                confidence_tier=tier,
                checked_venues=checked_venues,
                venue_ids=venue_ids,
            )

            # Mark complete
            await conn.execute(
                """
                UPDATE backfill_trips
                SET status = 'complete', "updatedAt" = NOW()
                WHERE id = $1
                """,
                backfill_trip_id,
            )

        logger.info(
            "process_backfill: pipeline complete trip=%s venues=%d signals=%d tier=%s",
            backfill_trip_id,
            len(checked_venues),
            signal_count,
            tier,
        )
