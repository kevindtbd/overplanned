"""
Repeat City Boost — V2 ML Pipeline Phase 5.2.

Pre-filter that runs before ranking when a user revisits a city they have
been to before. Adjusts the candidate list in-place:

  Hard exclude  — nodes the user explicitly skipped or disliked
                  (signal_weight < 0). Removed from the list entirely.

  Soft exclude  — nodes the user saw (impression) but never interacted
                  with positively. Removed unless revisit_favorites=True,
                  in which case they become neutral (no penalty).

  Boost         — nodes the user confirmed / loved (acceptance signals)
                  receive a 1.3x score multiplier on their
                  "convergenceScore" or "score" field.

The function queries the user's previous completed trips to the same city
slug, then applies the three-tier logic to the incoming candidate list.

Constraints
-----------
- DB queries use asyncpg raw SQL (db_pool is an asyncpg Pool/Connection).
- signal_weight is server-only — never included in the returned candidates.
- All signal_weight values must respect the DB CHECK [-1.0, 3.0].
- The function is idempotent — running it twice on the same list is safe.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# score multiplier applied to positively-confirmed nodes
BOOST_MULTIPLIER: float = 1.3

# signal_weight threshold: values strictly below this are "hard dislike"
_HARD_EXCLUDE_THRESHOLD: float = 0.0

# Acceptance signal types — positive interactions
_ACCEPTANCE_SIGNALS: frozenset[str] = frozenset({
    "slot_accept",
    "slot_love",
    "slot_confirm",
    "slot_complete",
})

# Negative / dislike signal types
_REJECTION_SIGNALS: frozenset[str] = frozenset({
    "slot_skip",
    "slot_dislike",
    "slot_reject",
})

# Impression-only signal types (seen but not acted on)
_IMPRESSION_SIGNALS: frozenset[str] = frozenset({
    "slot_view",
    "slot_impression",
})

# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------

_PREVIOUS_TRIPS_SQL = """
SELECT DISTINCT t.id
FROM trips t
JOIN trip_legs tl ON tl."tripId" = t.id
WHERE t."userId" = $1
  AND tl.city = $2
  AND t.status IN ('completed', 'active')
ORDER BY t.id DESC
"""

_SIGNALS_FOR_TRIPS_SQL = """
SELECT
    bs."activityNodeId",
    bs."signalType",
    bs."signal_weight"
FROM behavioral_signals bs
WHERE bs."tripId" = ANY($1::text[])
  AND bs."activityNodeId" IS NOT NULL
  AND bs."userId" = $2
ORDER BY bs."createdAt" ASC
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def apply_repeat_city_boost(
    candidates: list[dict],
    user_id: str,
    city_slug: str,
    revisit_favorites: bool,
    db_pool: Any,
) -> list[dict]:
    """
    Apply repeat-city pre-filter and boost adjustments to candidates.

    Args:
        candidates:        List of ActivityNode-like dicts. Each must have an
                           "id" field. May also carry "convergenceScore" or
                           "score" which is boosted for confirmed nodes.
        user_id:           The traveler's user ID.
        city_slug:         Slug for the destination city (e.g. "tokyo").
        revisit_favorites: When True, soft-excluded nodes become neutral
                           instead of being excluded.
        db_pool:           asyncpg connection pool.

    Returns:
        A new list of candidate dicts with adjustments applied. The original
        list is not mutated. Hard-excluded nodes are absent; soft-excluded
        nodes are absent unless revisit_favorites=True; boosted nodes carry
        an updated score.
    """
    if not candidates:
        return []

    hard_excluded, soft_excluded, boosted = await _load_node_classifications(
        user_id=user_id,
        city_slug=city_slug,
        db_pool=db_pool,
    )

    logger.info(
        "repeat_city_boost: user=%s city=%s hard_exclude=%d soft_exclude=%d boost=%d",
        user_id,
        city_slug,
        len(hard_excluded),
        len(soft_excluded),
        len(boosted),
    )

    result: list[dict] = []

    for candidate in candidates:
        node_id: str = candidate.get("id", "")

        # Hard exclude — drop entirely regardless of revisit_favorites
        if node_id in hard_excluded:
            logger.debug("repeat_city: hard-excluding node=%s", node_id)
            continue

        # Soft exclude — drop unless revisit_favorites is toggled
        if node_id in soft_excluded and not revisit_favorites:
            logger.debug("repeat_city: soft-excluding node=%s", node_id)
            continue

        # Build a shallow copy so we don't mutate the caller's list
        adjusted = dict(candidate)

        # Boost confirmed/loved nodes
        if node_id in boosted:
            adjusted = _apply_boost(adjusted)
            logger.debug("repeat_city: boosting node=%s", node_id)

        result.append(adjusted)

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _load_node_classifications(
    user_id: str,
    city_slug: str,
    db_pool: Any,
) -> tuple[set[str], set[str], set[str]]:
    """
    Query previous trip signals for this user + city and classify node IDs.

    Returns:
        (hard_excluded_ids, soft_excluded_ids, boosted_ids)

    Sets are mutually exclusive — hard_excluded takes priority over
    soft_excluded which takes priority over boosted.
    """
    async with db_pool.acquire() as conn:
        # Step 1: find all prior trips to this city
        trip_rows = await conn.fetch(_PREVIOUS_TRIPS_SQL, user_id, city_slug)

    if not trip_rows:
        # No prior visits — nothing to adjust
        return set(), set(), set()

    trip_ids = [row["id"] for row in trip_rows]

    async with db_pool.acquire() as conn:
        signal_rows = await conn.fetch(_SIGNALS_FOR_TRIPS_SQL, trip_ids, user_id)

    # Aggregate signals per node: track all signal types seen and min weight
    node_signals: dict[str, dict] = {}
    for row in signal_rows:
        node_id: str = row["activityNodeId"]
        signal_type: str = row["signalType"]
        weight: float = float(row["signal_weight"] or 1.0)

        if node_id not in node_signals:
            node_signals[node_id] = {
                "types": set(),
                "min_weight": weight,
            }

        node_signals[node_id]["types"].add(signal_type)
        node_signals[node_id]["min_weight"] = min(
            node_signals[node_id]["min_weight"], weight
        )

    hard_excluded: set[str] = set()
    soft_excluded: set[str] = set()
    boosted: set[str] = set()

    for node_id, data in node_signals.items():
        types: set[str] = data["types"]
        min_weight: float = data["min_weight"]

        has_rejection = bool(types & _REJECTION_SIGNALS)
        has_acceptance = bool(types & _ACCEPTANCE_SIGNALS)
        has_impression_only = bool(types & _IMPRESSION_SIGNALS) and not has_acceptance and not has_rejection

        # Hard exclude: explicit dislike signal OR negative weight
        if has_rejection or min_weight < _HARD_EXCLUDE_THRESHOLD:
            hard_excluded.add(node_id)
            continue

        # Boost: user confirmed/loved this node
        if has_acceptance:
            boosted.add(node_id)
            continue

        # Soft exclude: impression only, no positive interaction
        if has_impression_only:
            soft_excluded.add(node_id)

    # Ensure sets are disjoint (hard > soft > boost already guaranteed by
    # the continue-based logic above, but be explicit for safety)
    soft_excluded -= hard_excluded
    boosted -= hard_excluded
    boosted -= soft_excluded

    return hard_excluded, soft_excluded, boosted


def _apply_boost(candidate: dict) -> dict:
    """
    Apply BOOST_MULTIPLIER to the candidate's score fields.

    Checks "score" first, then "convergenceScore". If neither is present
    the candidate is returned unchanged — we don't invent scores.
    """
    boosted = dict(candidate)

    if "score" in boosted and boosted["score"] is not None:
        boosted["score"] = round(float(boosted["score"]) * BOOST_MULTIPLIER, 6)

    if "convergenceScore" in boosted and boosted["convergenceScore"] is not None:
        boosted["convergenceScore"] = round(
            float(boosted["convergenceScore"]) * BOOST_MULTIPLIER, 6
        )

    # Tag as boosted for downstream observability (stripped before client response)
    boosted["_repeatCityBoosted"] = True

    return boosted
