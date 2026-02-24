"""
Group Split Detector — V2 ML Pipeline Phase 5.5.

In group trips, detects when members have bimodal (strongly divergent)
preferences and suggests a temporary group split into subgroups.

Detection algorithm
-------------------
For each preference dimension present in the signal data, compute the
variance of preference scores across group members. If variance exceeds
VARIANCE_THRESHOLD on 2 or more dimensions, the group is considered bimodal.

Bimodal clustering is done via a simple two-centroid split: sort members
by their aggregate preference score for the conflicting dimensions and
split at the median. Ties are broken by user_id lexicographic order for
determinism.

Mutual exclusivity with Abilene
---------------------------------
A group cannot simultaneously be in Abilene territory (all-agreeing-
reluctantly) and bimodal (strongly divergent). The caller must ensure
AbileneDetector returns is_abilene=False before invoking this detector.
If abilene_active=True is passed, the function returns None immediately.

Rate limiting
-------------
MAX_SPLITS_PER_TRIP_PER_DAY = 1. The detector tracks suggestion timestamps
per trip in an in-memory dict. On process restart the rate limit resets.

Unanimous veto
--------------
Any member may veto the split suggestion. If any member_id appears in
vetoed_by, the function returns None.

Required sync-back
------------------
The returned split suggestion includes a "sync_back_slot" placeholder
indicating where the subgroups should reunite. Callers are responsible for
materialising this as an actual ItinerarySlot.

Output
------
On detection:
    {
        "split_suggested": True,
        "divergent_dimensions": list[str],
        "subgroups": list[list[str]],   # list of [user_id, ...] per subgroup
        "sync_back_slot": str,           # human-readable reunion point hint
    }

None if:
  - Variance below threshold on fewer than 2 dimensions
  - abilene_active=True
  - Any member has vetoed
  - Already suggested once today for this trip
"""

from __future__ import annotations

import logging
import statistics
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Variance threshold per dimension. Computed on preference scores [0, 1].
VARIANCE_THRESHOLD: float = 0.08

# Minimum number of divergent dimensions to suggest a split
MIN_DIVERGENT_DIMENSIONS: int = 2

# Maximum split suggestions per trip per calendar day
MAX_SPLITS_PER_TRIP_PER_DAY: int = 1

# ---------------------------------------------------------------------------
# In-memory rate-limit store: trip_id -> list of suggestion unix timestamps
# ---------------------------------------------------------------------------
_SUGGESTION_LOG: dict[str, list[float]] = defaultdict(list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def detect_group_split(
    trip_id: str,
    member_preferences: dict[str, list[dict]],
    db_pool: Any,
    abilene_active: bool = False,
    vetoed_by: list[str] | None = None,
) -> dict | None:
    """
    Detect bimodal group preferences and suggest a split if warranted.

    Args:
        trip_id:             The group trip being evaluated.
        member_preferences:  { user_id -> list of preference signal dicts }.
                             Each signal dict should carry:
                               "dimension" str  — preference axis name
                               "score"     float — preference score [0, 1]
                               "direction" str  — "positive" | "negative"
        db_pool:             asyncpg pool (reserved for future persistence;
                             not used in the current pure-logic implementation).
        abilene_active:      Set True if AbileneDetector already flagged this
                             group. Mutually exclusive with split detection.
        vetoed_by:           List of user_ids who have vetoed the split.
                             If non-empty, returns None.

    Returns:
        Split suggestion dict or None.
    """
    if abilene_active:
        logger.debug(
            "split_detector: skipping — Abilene paradox active for trip=%s", trip_id
        )
        return None

    if vetoed_by:
        logger.debug(
            "split_detector: vetoed by %s for trip=%s", vetoed_by, trip_id
        )
        return None

    if not member_preferences or len(member_preferences) < 2:
        return None

    if _rate_limited(trip_id):
        logger.debug(
            "split_detector: daily limit reached for trip=%s", trip_id
        )
        return None

    # Build per-dimension score vectors
    dimension_scores: dict[str, dict[str, float]] = defaultdict(dict)

    for user_id, signals in member_preferences.items():
        for signal in signals:
            dimension = signal.get("dimension", "")
            raw_score = signal.get("score")
            direction = signal.get("direction", "positive")

            if not dimension or raw_score is None:
                continue

            score = float(raw_score)

            # Invert score for negative direction signals
            if direction == "negative":
                score = 1.0 - score

            # Average multiple signals for the same dimension per user
            if user_id not in dimension_scores[dimension]:
                dimension_scores[dimension][user_id] = score
            else:
                # Running average (simple mean of two values for now)
                prev = dimension_scores[dimension][user_id]
                dimension_scores[dimension][user_id] = (prev + score) / 2.0

    if not dimension_scores:
        return None

    # Find divergent dimensions
    divergent_dimensions: list[str] = []

    for dimension, user_score_map in dimension_scores.items():
        scores = list(user_score_map.values())
        if len(scores) < 2:
            continue

        try:
            var = statistics.variance(scores)
        except statistics.StatisticsError:
            continue

        if var >= VARIANCE_THRESHOLD:
            divergent_dimensions.append(dimension)

    if len(divergent_dimensions) < MIN_DIVERGENT_DIMENSIONS:
        logger.debug(
            "split_detector: only %d divergent dimensions for trip=%s (need %d)",
            len(divergent_dimensions),
            trip_id,
            MIN_DIVERGENT_DIMENSIONS,
        )
        return None

    # Cluster members into 2 subgroups based on aggregate divergent-dimension scores
    subgroups = _cluster_members(
        member_preferences=member_preferences,
        divergent_dimensions=divergent_dimensions,
    )

    # Record suggestion for rate limiting
    _SUGGESTION_LOG[trip_id].append(time.time())

    sync_back_slot = _generate_sync_back_hint(divergent_dimensions)

    logger.info(
        "split_detector: split suggested for trip=%s divergent=%s subgroups=%s",
        trip_id,
        divergent_dimensions,
        [[uid for uid in sg] for sg in subgroups],
    )

    return {
        "split_suggested": True,
        "divergent_dimensions": divergent_dimensions,
        "subgroups": subgroups,
        "sync_back_slot": sync_back_slot,
    }


def reset_suggestion_log() -> None:
    """
    Clear the in-memory suggestion log.

    Exposed for testing only. Do NOT call in production code.
    """
    _SUGGESTION_LOG.clear()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _rate_limited(trip_id: str) -> bool:
    """
    Return True if a split was already suggested for this trip today.
    """
    today_start = _today_start_unix()
    recent = [t for t in _SUGGESTION_LOG.get(trip_id, []) if t >= today_start]
    return len(recent) >= MAX_SPLITS_PER_TRIP_PER_DAY


def _today_start_unix() -> float:
    """Return the unix timestamp for midnight UTC today."""
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.timestamp()


def _aggregate_score(
    signals: list[dict],
    dimensions: list[str],
) -> float:
    """
    Compute an aggregate preference score for a member across the given
    divergent dimensions. Higher = stronger preference in the positive
    direction for those dimensions.
    """
    total = 0.0
    count = 0

    for signal in signals:
        if signal.get("dimension") not in dimensions:
            continue
        raw = signal.get("score")
        if raw is None:
            continue
        score = float(raw)
        direction = signal.get("direction", "positive")
        if direction == "negative":
            score = 1.0 - score
        total += score
        count += 1

    return total / count if count > 0 else 0.5


def _cluster_members(
    member_preferences: dict[str, list[dict]],
    divergent_dimensions: list[str],
) -> list[list[str]]:
    """
    Split members into two subgroups by median aggregate score.

    Members are sorted by aggregate score ascending, then split at the
    midpoint. Ties broken by user_id lexicographic order for determinism.
    """
    scored: list[tuple[float, str]] = []

    for user_id, signals in member_preferences.items():
        score = _aggregate_score(signals, divergent_dimensions)
        scored.append((score, user_id))

    # Sort by score ascending, then user_id for determinism
    scored.sort(key=lambda x: (x[0], x[1]))

    midpoint = len(scored) // 2
    group_a = [uid for _, uid in scored[:midpoint]]
    group_b = [uid for _, uid in scored[midpoint:]]

    # Ensure both groups have at least one member
    if not group_a and group_b:
        group_a = [group_b.pop(0)]
    elif not group_b and group_a:
        group_b = [group_a.pop()]

    return [group_a, group_b]


def _generate_sync_back_hint(divergent_dimensions: list[str]) -> str:
    """
    Generate a human-readable sync-back slot hint based on the split context.

    This is a placeholder recommendation. Production would use ML to suggest
    a specific activity node that both subgroups rate highly.
    """
    # Common neutral reunion activities by dimension type
    dimension_reunions: dict[str, str] = {
        "food":         "group dinner at a communal table restaurant",
        "pace":         "relaxed meetup at a central cafe or park",
        "culture":      "shared exploration of a major landmark",
        "nightlife":    "early evening drinks before going separate ways",
        "budget":       "picnic or street food market where each member chooses their spend",
        "outdoor":      "scenic viewpoint or waterfront gathering spot",
        "shopping":     "browse a covered market where everyone can look at their own pace",
    }

    for dim in divergent_dimensions:
        hint = dimension_reunions.get(dim.lower())
        if hint:
            return hint

    return "reunite at a central location for a shared meal before continuing"
