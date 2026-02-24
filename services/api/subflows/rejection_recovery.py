"""
Rejection Recovery — V2 ML Pipeline Phase 5.1.

Detects when a user rejects multiple slots in quick succession and triggers
recovery logic that surfaces alternative recommendations based on the
rejection pattern.

Burst detection
---------------
3 or more rejections within BURST_WINDOW_SECONDS triggers recovery. The
timestamps are supplied by the caller (unix floats) — no wall-clock state is
kept inside this module. A simple in-memory set (not Redis) tracks which
trips have already fired recovery to prevent repeated triggering.

Vibe analysis
-------------
Rejected slots' vibe tags are aggregated. The most-common vibe slugs in
rejected slots form the "anti-pattern". The recovery suggestion inverts
this: it recommends vibes that are dissimilar to the anti-pattern.

Output
------
On burst detection (first time for this trip):
    {
        "trigger": True,
        "anti_vibes": list[str],       # vibe slugs to avoid
        "suggested_vibes": list[str],  # recommended alternatives
        "signal_weight": float,        # <= -0.4
    }

None if no burst detected, or if recovery already fired for this trip.

Constraints
-----------
- signal_weight is server-only — callers must NOT return it to clients.
- signal_weight values must respect DB CHECK [-1.0, 3.0].
- Weight cap for recovery signals: RECOVERY_WEIGHT_CAP = -0.4.
- The function logs a BehavioralSignal with subflow="rejection_recovery".
- One recovery trigger per trip (tracked in _FIRED_TRIPS module-level set).
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Burst window in seconds: rejections within this window trigger recovery
BURST_WINDOW_SECONDS: float = 120.0

# Minimum rejections within the window to trigger recovery
BURST_THRESHOLD: int = 3

# Maximum (most negative) signal_weight for recovery signals
# DB CHECK constraint: [-1.0, 3.0] — this is well within range
RECOVERY_WEIGHT_CAP: float = -0.4

# ---------------------------------------------------------------------------
# In-memory guard: track which trips have already fired recovery
# This prevents repeated triggering within the same process lifetime.
# On process restart the guard resets — acceptable for a per-trip,
# per-session feature.
# ---------------------------------------------------------------------------
_FIRED_TRIPS: set[str] = set()

# ---------------------------------------------------------------------------
# Vibe inversion map: common anti-vibes -> recommended alternative vibes
# This is a static heuristic table. As the ML layer matures this can be
# replaced by a learned inversion from behavioral_signal data.
# ---------------------------------------------------------------------------
_VIBE_ALTERNATIVES: dict[str, list[str]] = {
    "touristy":       ["local-hidden-gem", "neighborhood-spot", "off-the-beaten-path"],
    "crowded":        ["peaceful", "quiet", "low-key"],
    "expensive":      ["budget-friendly", "affordable", "street-food"],
    "fine-dining":    ["casual-dining", "street-food", "izakaya"],
    "chain":          ["independent", "local-only", "family-run"],
    "museum":         ["outdoor", "street-art", "market"],
    "temple":         ["urban-exploration", "market", "cafe-culture"],
    "nightlife":      ["daytime", "family-friendly", "morning-ritual"],
    "fast-food":      ["sit-down", "local-spot", "chef-driven"],
    "popular":        ["under-the-radar", "locals-only", "hidden"],
    "mainstream":     ["niche", "subculture", "indie"],
    "tourist-trap":   ["authentic", "local-favorite", "no-english-menu"],
}

_DEFAULT_ALTERNATIVES: list[str] = ["local-hidden-gem", "neighborhood-spot", "casual"]

# ---------------------------------------------------------------------------
# SQL for logging the recovery signal
# ---------------------------------------------------------------------------

_INSERT_SIGNAL_SQL = """
INSERT INTO "BehavioralSignal" (
    id,
    "userId",
    "tripId",
    "signalType",
    "signalValue",
    "tripPhase",
    "rawAction",
    "subflow",
    "signal_weight",
    "source",
    "createdAt"
) VALUES (
    gen_random_uuid(),
    $1, $2,
    'rejection_recovery_trigger',
    $3,
    'active',
    'auto_recovery',
    'rejection_recovery',
    $4,
    'user_behavioral',
    NOW()
)
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def check_rejection_burst(
    user_id: str,
    trip_id: str,
    rejection_timestamps: list[float],
    rejected_slots: list[dict],
    db_pool: Any,
) -> dict | None:
    """
    Evaluate whether a rejection burst has occurred and return recovery data.

    Args:
        user_id:               The user whose rejections are being evaluated.
        trip_id:               The trip being evaluated. Recovery fires at most
                               once per trip_id.
        rejection_timestamps:  Unix timestamps (float) of recent rejections.
                               Caller should supply at least the last few
                               minutes worth.
        rejected_slots:        Dicts representing the rejected ItinerarySlots.
                               Each may carry "vibeTags" (list of dicts or
                               strings), "slotType", and "activityNodeId".
        db_pool:               asyncpg connection pool for signal logging.

    Returns:
        Recovery suggestion dict if burst detected, None otherwise.
        {
            "trigger": True,
            "anti_vibes": list[str],
            "suggested_vibes": list[str],
            "signal_weight": float,       # <= RECOVERY_WEIGHT_CAP
        }
    """
    if trip_id in _FIRED_TRIPS:
        logger.debug("rejection_recovery: already fired for trip=%s, skipping", trip_id)
        return None

    if not _is_burst(rejection_timestamps):
        return None

    # Mark as fired before any await to prevent double-fire under concurrency
    _FIRED_TRIPS.add(trip_id)

    anti_vibes = _extract_anti_vibes(rejected_slots)
    suggested_vibes = _invert_vibes(anti_vibes)

    # Log the recovery trigger as a BehavioralSignal
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                _INSERT_SIGNAL_SQL,
                user_id,
                trip_id,
                float(len(rejection_timestamps)),  # signalValue = rejection count
                RECOVERY_WEIGHT_CAP,
            )
    except Exception:
        logger.exception(
            "rejection_recovery: failed to log signal for trip=%s user=%s",
            trip_id,
            user_id,
        )
        # Non-fatal — still return the recovery suggestion

    logger.info(
        "rejection_recovery: burst detected for trip=%s user=%s "
        "rejections=%d anti_vibes=%s",
        trip_id,
        user_id,
        len(rejection_timestamps),
        anti_vibes,
    )

    return {
        "trigger": True,
        "anti_vibes": anti_vibes,
        "suggested_vibes": suggested_vibes,
        "signal_weight": RECOVERY_WEIGHT_CAP,
    }


def reset_fired_trips() -> None:
    """
    Clear the in-memory fired-trips guard.

    Exposed for testing only. Do NOT call in production code.
    """
    _FIRED_TRIPS.clear()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_burst(timestamps: list[float]) -> bool:
    """
    Return True if BURST_THRESHOLD or more timestamps fall within
    BURST_WINDOW_SECONDS of the most recent timestamp.
    """
    if len(timestamps) < BURST_THRESHOLD:
        return False

    now = max(timestamps)  # use the most recent rejection as the anchor
    window_start = now - BURST_WINDOW_SECONDS
    recent = [t for t in timestamps if t >= window_start]
    return len(recent) >= BURST_THRESHOLD


def _extract_anti_vibes(rejected_slots: list[dict]) -> list[str]:
    """
    Aggregate vibe tag slugs from rejected slots, return the most common ones.

    Returns up to 3 most common slugs. If a slot has no vibe tags its
    slotType is used as a fallback heuristic.
    """
    counter: Counter[str] = Counter()

    for slot in rejected_slots:
        vibes = _get_vibe_slugs(slot)
        if vibes:
            counter.update(vibes)
        else:
            # Fallback: use slotType as a proxy vibe
            slot_type = (slot.get("slotType") or "").lower().strip()
            if slot_type:
                counter[slot_type] += 1

    # Return up to 3 most common anti-vibes
    return [slug for slug, _ in counter.most_common(3)]


def _invert_vibes(anti_vibes: list[str]) -> list[str]:
    """
    Return a list of recommended vibes that are the inverse of anti_vibes.

    Walks the anti_vibes list, collecting alternatives from the lookup table.
    Deduplicates and returns up to 5 suggestions.
    """
    seen: set[str] = set()
    suggestions: list[str] = []

    for vibe in anti_vibes:
        alts = _VIBE_ALTERNATIVES.get(vibe, [])
        for alt in alts:
            if alt not in seen:
                seen.add(alt)
                suggestions.append(alt)
            if len(suggestions) >= 5:
                return suggestions

    # If we couldn't build a suggestion list, return safe defaults
    if not suggestions:
        for alt in _DEFAULT_ALTERNATIVES:
            if alt not in seen:
                seen.add(alt)
                suggestions.append(alt)

    return suggestions[:5]


def _get_vibe_slugs(slot: dict) -> list[str]:
    """
    Extract vibe tag slugs from a slot dict.

    Handles both:
      - list of dicts: [{"slug": "coffee-crawl"}, ...]
      - list of strings: ["coffee-crawl", ...]
    """
    raw = slot.get("vibeTags") or []
    slugs: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            slug = (item.get("slug") or item.get("name") or "").lower().strip()
        else:
            slug = str(item).lower().strip()
        if slug:
            slugs.append(slug)
    return slugs
