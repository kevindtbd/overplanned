"""
effective_persona() — the single entry point for all persona reads.

RankingOrchestrator and generation code NEVER read PersonaDimension directly.
This function resolves the priority stack and returns a unified PersonaSnapshot.

Priority stack (highest wins):
  1. TripPersonaCache (Redis) — if trip active and cache version matches DB
  2. persona_dimensions (DB) — base priors + nightly batch updates
  3. cf_persona_blend (DB) — blended at 0.5x (if >=5 neighbors, >=50 warm users)
     NOTE: cf_persona_blend table is not yet built. This layer is a no-op stub.
  4. destination_prior — blended at 0.15x (only dimensions with confidence < 0.3)

Negative tag affinities from persona_dimensions.negativeTagAffinities are
included in the snapshot for Qdrant query-time exclusion weighting.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from services.api.persona.types import DimensionValue, PersonaSnapshot
from services.api.priors.destination_prior import (
    CONFIDENCE_GATE,
    apply_destination_prior,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Redis key format for TripPersonaCache
_CACHE_KEY_TEMPLATE = "trip_persona_cache:{user_id}:{trip_id}"

# Default confidence assigned to dimensions when no DB data is found
_DEFAULT_CONFIDENCE = 0.5

# Default dimension values for a cold-start user
_DEFAULT_DIMENSIONS: dict[str, str] = {
    "energy_level": "medium_energy",
    "social_orientation": "small_group",
    "planning_style": "flexible",
    "budget_orientation": "moderate_spender",
    "food_priority": "food_balanced",
    "culture_engagement": "culture_moderate",
    "nature_preference": "nature_curious",
    "nightlife_interest": "balanced_schedule",
    "authenticity_preference": "locally_curious",
    "pace_preference": "moderate_pace",
}

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_GET_PERSONA_DIMENSIONS_SQL = """
SELECT dimension, value, confidence, source, "negativeTagAffinities", version
FROM persona_dimensions
WHERE "userId" = $1
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _cache_key(user_id: str, trip_id: str) -> str:
    return _CACHE_KEY_TEMPLATE.format(user_id=user_id, trip_id=trip_id)


async def _try_redis_cache(
    user_id: str,
    trip_id: str,
    redis_client: Any,
    db_version: int | None,
) -> PersonaSnapshot | None:
    """
    Attempt to read a PersonaSnapshot from TripPersonaCache.

    Returns a fully populated PersonaSnapshot on a valid cache hit,
    or None on miss, version mismatch, or any Redis error.

    Version check: the cached hash must contain a 'nightly_sync_version'
    field that equals the DB version. If db_version is None (DB not yet
    read), version check is skipped and the cache hit is accepted as-is.
    """
    if redis_client is None:
        return None

    key = _cache_key(user_id, trip_id)
    try:
        raw = await redis_client.hgetall(key)
        if not raw:
            logger.debug("effective_persona: cache miss key=%s", key)
            return None

        # Version guard
        cached_version_raw = raw.get("nightly_sync_version") or raw.get(b"nightly_sync_version")
        if cached_version_raw is not None and db_version is not None:
            try:
                cached_version = int(cached_version_raw)
            except (ValueError, TypeError):
                cached_version = -1

            if cached_version != db_version:
                logger.debug(
                    "effective_persona: cache stale key=%s cached_v=%s db_v=%s",
                    key,
                    cached_version_raw,
                    db_version,
                )
                return None

        # Deserialize the snapshot from the Redis hash
        dims_raw = raw.get("dimensions") or raw.get(b"dimensions")
        neg_tags_raw = raw.get("negative_tag_affinities") or raw.get(b"negative_tag_affinities")
        source_raw = raw.get("source_breakdown") or raw.get(b"source_breakdown")
        confidence_raw = raw.get("confidence") or raw.get(b"confidence")
        resolved_raw = raw.get("resolved_at") or raw.get(b"resolved_at")

        if dims_raw is None:
            logger.debug("effective_persona: cache entry missing 'dimensions' key=%s", key)
            return None

        if isinstance(dims_raw, bytes):
            dims_raw = dims_raw.decode()
        if isinstance(neg_tags_raw, bytes):
            neg_tags_raw = neg_tags_raw.decode() if neg_tags_raw else None
        if isinstance(source_raw, bytes):
            source_raw = source_raw.decode() if source_raw else None
        if isinstance(confidence_raw, bytes):
            confidence_raw = confidence_raw.decode() if confidence_raw else None
        if isinstance(resolved_raw, bytes):
            resolved_raw = resolved_raw.decode() if resolved_raw else None

        raw_dims: dict[str, dict] = json.loads(dims_raw)
        dimensions = {
            dim: DimensionValue(
                value=v["value"],
                confidence=float(v["confidence"]),
                source=v.get("source", "trip_cache"),
            )
            for dim, v in raw_dims.items()
        }

        negative_tag_affinities: dict[str, float] = (
            json.loads(neg_tags_raw) if neg_tags_raw else {}
        )
        source_breakdown: dict[str, str] = (
            json.loads(source_raw) if source_raw else {}
        )
        confidence = float(confidence_raw) if confidence_raw is not None else 0.5
        resolved_at = resolved_raw or _now_iso()

        logger.debug(
            "effective_persona: cache hit key=%s dims=%d",
            key,
            len(dimensions),
        )

        return PersonaSnapshot(
            user_id=user_id,
            trip_id=trip_id,
            dimensions=dimensions,
            negative_tag_affinities=negative_tag_affinities,
            source_breakdown=source_breakdown,
            confidence=confidence,
            cache_hit=True,
            resolved_at=resolved_at,
        )

    except Exception:
        logger.warning(
            "effective_persona: Redis read failed for key=%s, falling through to DB",
            key,
            exc_info=True,
        )
        return None


async def _read_persona_from_db(
    user_id: str,
    pool: Any,
) -> tuple[dict[str, DimensionValue], dict[str, float], dict[str, str], int]:
    """
    Read PersonaDimension rows from DB for the given user.

    Returns:
        (dimensions, negative_tag_affinities, source_breakdown, max_version)

    Raises:
        Exception: propagated from asyncpg — DB failure is fatal.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(_GET_PERSONA_DIMENSIONS_SQL, user_id)

    if not rows:
        # Cold-start: build default dimensions
        logger.debug(
            "effective_persona: no PersonaDimension rows for user=%s, using defaults",
            user_id,
        )
        dimensions: dict[str, DimensionValue] = {
            dim: DimensionValue(
                value=val,
                confidence=_DEFAULT_CONFIDENCE,
                source="onboarding",
            )
            for dim, val in _DEFAULT_DIMENSIONS.items()
        }
        return dimensions, {}, {dim: "onboarding" for dim in dimensions}, 0

    dimensions = {}
    source_breakdown: dict[str, str] = {}
    negative_tag_affinities: dict[str, float] = {}
    max_version = 0

    for row in rows:
        dim = row["dimension"]
        source = row["source"] or "onboarding"

        dimensions[dim] = DimensionValue(
            value=row["value"],
            confidence=float(row["confidence"]),
            source=source,
        )
        source_breakdown[dim] = source

        # Track max version across all rows (all rows share the same user version,
        # but we read max defensively in case of partial updates mid-batch)
        row_version = row["version"] if row["version"] is not None else 0
        if row_version > max_version:
            max_version = row_version

        # negativeTagAffinities is a user-level JSONB column on PersonaDimension.
        # It's duplicated across rows but conceptually user-scoped.
        # Grab it from the first non-null row.
        if not negative_tag_affinities and row["negativeTagAffinities"] is not None:
            raw_nta = row["negativeTagAffinities"]
            if isinstance(raw_nta, str):
                try:
                    raw_nta = json.loads(raw_nta)
                except (json.JSONDecodeError, ValueError):
                    raw_nta = {}
            if isinstance(raw_nta, dict):
                negative_tag_affinities = {
                    k: float(v) for k, v in raw_nta.items()
                }

    return dimensions, negative_tag_affinities, source_breakdown, max_version


def _try_cf_blend(
    dimensions: dict[str, DimensionValue],
) -> dict[str, DimensionValue]:
    """
    Collaborative filtering persona blend (stub — cf_persona_blend table not yet built).

    When cf_persona_blend is implemented in V2, this function will:
      - Query cf_persona_blend for users with >= 5 neighbors (>= 50 warm users)
      - Blend CF dimensions at 0.5x weight into low-confidence user dimensions

    For now, returns the input dimensions unchanged.
    """
    logger.debug("effective_persona: cf_persona_blend not yet available (stub)")
    return dimensions


def _apply_prior_to_dimensions(
    dimensions: dict[str, DimensionValue],
    source_breakdown: dict[str, str],
    city_slug: str,
) -> tuple[dict[str, DimensionValue], dict[str, str]]:
    """
    Apply destination prior to dimensions with confidence < CONFIDENCE_GATE.

    Converts PersonaSnapshot dimensions into the signal-list format that
    apply_destination_prior() expects, runs the blend, then converts back.
    """
    # Convert to signal list format
    user_signals = [
        {
            "dimension": dim,
            "direction": dv.value,
            "confidence": dv.confidence,
            "source": dv.source,
        }
        for dim, dv in dimensions.items()
    ]

    blended_signals = apply_destination_prior(user_signals, city_slug)

    updated_dimensions = dict(dimensions)
    updated_source = dict(source_breakdown)

    for sig in blended_signals:
        if sig.get("source") != "destination_prior":
            continue

        dim = sig["dimension"]
        # Only inject for dimensions that are new or below the confidence gate
        existing = dimensions.get(dim)
        if existing is not None and existing.confidence >= CONFIDENCE_GATE:
            continue

        updated_dimensions[dim] = DimensionValue(
            value=sig["direction"],  # destination_prior uses 'direction' as its value
            confidence=float(sig["confidence"]),
            source="destination_prior",
        )
        updated_source[dim] = "destination_prior"

    return updated_dimensions, updated_source


def _compute_overall_confidence(dimensions: dict[str, DimensionValue]) -> float:
    """Mean confidence across all dimensions. Returns 0.5 for empty sets."""
    if not dimensions:
        return 0.5
    total = sum(dv.confidence for dv in dimensions.values())
    return round(total / len(dimensions), 4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def effective_persona(
    user_id: str,
    trip_id: str | None = None,
    *,
    pool: Any = None,
    redis_client: Any = None,
    city_slug: str | None = None,
) -> PersonaSnapshot:
    """
    Resolve and return the effective persona for a user, optionally scoped to a trip.

    Priority stack (highest wins):
      1. TripPersonaCache (Redis) — only when trip_id is provided and version matches DB
      2. PersonaDimension (DB) — base priors and nightly EMA updates
      3. cf_persona_blend — collaborative filtering blend (stub, no-op until V2)
      4. destination_prior — fills low-confidence dimensions from city-level priors

    Args:
        user_id:      The user whose persona to resolve.
        trip_id:      Optional trip context. If provided, enables Redis cache lookup.
        pool:         asyncpg connection pool. Required for DB reads.
        redis_client: redis.asyncio client. If None, cache layer is skipped gracefully.
        city_slug:    City slug for destination prior injection (e.g. 'austin', 'bend').
                      If None, destination prior layer is skipped.

    Returns:
        PersonaSnapshot with all resolved dimensions.

    Raises:
        Exception: If the DB read fails. DB failure is fatal — we cannot serve
                   recommendations without persona data.
    """
    if pool is None:
        raise ValueError("effective_persona: 'pool' is required (asyncpg connection pool)")

    # ------------------------------------------------------------------
    # Step 1: Determine DB version for cache validation (lightweight fetch)
    # We need the version before reading the cache so we can validate freshness.
    # If Redis is not available, skip the version pre-fetch and go straight to DB.
    # ------------------------------------------------------------------
    db_version: int | None = None
    db_dimensions: dict[str, DimensionValue] | None = None
    db_neg_tags: dict[str, float] | None = None
    db_source_breakdown: dict[str, str] | None = None

    # ------------------------------------------------------------------
    # Step 2: Try TripPersonaCache (only if trip_id + redis available)
    # ------------------------------------------------------------------
    if trip_id is not None and redis_client is not None:
        # To validate cache version we first do a lightweight DB version read.
        # This is a small extra query but prevents serving stale persona data.
        # If this fails it's fatal (DB is required).
        try:
            async with pool.acquire() as _conn:
                version_rows = await _conn.fetch(
                    'SELECT version FROM persona_dimensions WHERE "userId" = $1 LIMIT 1',
                    user_id,
                )
            db_version = version_rows[0]["version"] if version_rows else 0
        except Exception:
            logger.warning(
                "effective_persona: version pre-fetch failed for user=%s, "
                "proceeding without version check",
                user_id,
                exc_info=True,
            )
            db_version = None

        cached = await _try_redis_cache(user_id, trip_id, redis_client, db_version)
        if cached is not None:
            logger.info(
                "effective_persona: served from cache user=%s trip=%s",
                user_id,
                trip_id,
            )
            return cached

    # ------------------------------------------------------------------
    # Step 3: Read PersonaDimension from DB
    # ------------------------------------------------------------------
    logger.debug("effective_persona: reading DB for user=%s", user_id)
    (
        db_dimensions,
        db_neg_tags,
        db_source_breakdown,
        resolved_db_version,
    ) = await _read_persona_from_db(user_id, pool)

    dimensions = db_dimensions
    negative_tag_affinities = db_neg_tags
    source_breakdown = db_source_breakdown

    # ------------------------------------------------------------------
    # Step 4: CF persona blend (stub — no-op until cf_persona_blend exists)
    # ------------------------------------------------------------------
    dimensions = _try_cf_blend(dimensions)

    # ------------------------------------------------------------------
    # Step 5: Apply destination prior for low-confidence dimensions
    # ------------------------------------------------------------------
    if city_slug is not None:
        dimensions, source_breakdown = _apply_prior_to_dimensions(
            dimensions, source_breakdown, city_slug
        )

    # ------------------------------------------------------------------
    # Step 6: Compute overall confidence and assemble snapshot
    # ------------------------------------------------------------------
    overall_confidence = _compute_overall_confidence(dimensions)

    snapshot = PersonaSnapshot(
        user_id=user_id,
        trip_id=trip_id,
        dimensions=dimensions,
        negative_tag_affinities=negative_tag_affinities,
        source_breakdown=source_breakdown,
        confidence=overall_confidence,
        cache_hit=False,
        resolved_at=_now_iso(),
    )

    logger.info(
        "effective_persona: resolved user=%s trip=%s dims=%d confidence=%.3f cache_hit=False",
        user_id,
        trip_id,
        len(dimensions),
        overall_confidence,
    )

    return snapshot


async def get_persona_for_ranking(
    user_id: str,
    trip_id: str,
    pool: Any,
    redis_client: Any = None,
    city_slug: str | None = None,
) -> dict[str, Any]:
    """
    Convenience wrapper for ranker.py integration.

    Calls effective_persona() and converts the result to the flat dict format
    that rank_candidates_with_llm() (and RankingOrchestrator) expect:

        {
            "vibes": ["food-driven", "culture-immersive"],
            "pace": "moderate",
            "budget": "mid",
            "dimensions": {
                "food_priority": {"value": "food_driven", "confidence": 0.85},
                ...
            },
            "negative_tags": {"party-central": -0.8},
        }

    The vibes list is derived from dimension values that represent lifestyle
    preferences (food_priority, culture_engagement, nature_preference, etc.).
    pace and budget are extracted from their specific dimensions.

    Args:
        user_id:      User to resolve persona for.
        trip_id:      Trip context (required for cache lookup).
        pool:         asyncpg connection pool.
        redis_client: Optional redis.asyncio client for cache reads.
        city_slug:    Optional city for destination prior injection.

    Returns:
        Flat dict matching the persona_seed format consumed by ranker.py.
    """
    snapshot = await effective_persona(
        user_id,
        trip_id=trip_id,
        pool=pool,
        redis_client=redis_client,
        city_slug=city_slug,
    )

    # Extract pace from persona dimensions
    pace_dim = snapshot.dimensions.get("pace_preference")
    if pace_dim is not None:
        pace_value = pace_dim.value
        # Map persona values to ranker-friendly labels
        if "slow" in pace_value:
            pace = "slow"
        elif "fast" in pace_value or "high" in pace_value:
            pace = "fast"
        else:
            pace = "moderate"
    else:
        pace = "moderate"

    # Extract budget orientation
    budget_dim = snapshot.dimensions.get("budget_orientation")
    if budget_dim is not None:
        budget_value = budget_dim.value
        if "budget" in budget_value or "low" in budget_value:
            budget = "budget"
        elif "luxury" in budget_value or "high" in budget_value:
            budget = "luxury"
        else:
            budget = "mid"
    else:
        budget = "mid"

    # Build vibes list from lifestyle-oriented dimensions
    _VIBE_DIMENSIONS = {
        "food_priority",
        "culture_engagement",
        "nature_preference",
        "nightlife_interest",
        "authenticity_preference",
        "social_orientation",
        "energy_level",
    }
    vibes: list[str] = []
    for dim_name in _VIBE_DIMENSIONS:
        dim_val = snapshot.dimensions.get(dim_name)
        if dim_val is not None and dim_val.confidence >= 0.4:
            # Convert underscored values to hyphenated labels for ranker
            vibe_label = dim_val.value.replace("_", "-")
            vibes.append(vibe_label)

    # Build flat dimensions dict
    flat_dimensions: dict[str, dict[str, Any]] = {
        dim_name: {
            "value": dv.value,
            "confidence": dv.confidence,
        }
        for dim_name, dv in snapshot.dimensions.items()
    }

    return {
        "vibes": vibes,
        "pace": pace,
        "budget": budget,
        "dimensions": flat_dimensions,
        "negative_tags": snapshot.negative_tag_affinities,
    }
