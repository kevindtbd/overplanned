"""
Alteration Signal Tagger — V2 ML Pipeline Phase 1.3.

Groups BehavioralSignals by session (userId + 30-minute rolling window) and
detects itinerary-alteration patterns. Returns enrichment dicts that callers
use to backfill ``subflow`` and ``signal_weight`` on the relevant signals.

Detected patterns
-----------------
date_shift          Two or more slot_swap signals where the dayNumber changed
                    within the session window.
                    subflow  → "itinerary_alteration_date"
                    weight   → 1.3

slot_swap           Any slot_swap signal (individual swap action).
                    subflow  → "itinerary_alteration_swap"
                    weight   → 1.3

category_shift      Two or more slot_skip or slot_swap signals involving the
                    same activity category within the session window.
                    subflow  → "itinerary_alteration_category"
                    weight   → 1.4   (strongest — reveals a clear preference gap)

Priority: category_shift > date_shift > slot_swap
When multiple patterns apply to the same signal, the highest-priority pattern
wins (the enrichment dict contains only one subflow per signal).

Session windowing
-----------------
Signals are bucketed by (userId, window_start) where window_start is the
signal's createdAt floored to the nearest ``window_minutes`` boundary.
This is a simple fixed-window approach — it does not slide.

Input shape
-----------
Each signal dict must contain at minimum:
    id          str       — signal identifier
    userId      str       — owner
    signalType  str       — e.g. "slot_swap", "slot_skip"
    createdAt   datetime  — used for windowing

Optional fields used for richer detection:
    payload     dict      — may contain "dayNumber", "category"
    metadata    dict      — alternative location for "dayNumber", "category"

Output shape
------------
List of enrichment dicts:
    {
        "signal_id": str,
        "subflow":   str,         # "itinerary_alteration_*"
        "signal_weight": float,   # 1.3 or 1.4
    }

Only signals that match at least one pattern are included in the output.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SWAP_TYPES: frozenset[str] = frozenset({"slot_swap"})
_SKIP_TYPES: frozenset[str] = frozenset({"slot_skip", "slot_swap"})

# Minimum number of category occurrences in one window to fire category_shift
_CATEGORY_SHIFT_THRESHOLD: int = 2

# Signal weights — stay within DB CHECK [-1.0, 3.0]
_WEIGHT_DATE_SHIFT: float = 1.3
_WEIGHT_SLOT_SWAP: float = 1.3
_WEIGHT_CATEGORY_SHIFT: float = 1.4

# Subflow labels
_SUBFLOW_DATE: str = "itinerary_alteration_date"
_SUBFLOW_SWAP: str = "itinerary_alteration_swap"
_SUBFLOW_CATEGORY: str = "itinerary_alteration_category"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _floor_to_window(dt: datetime, window_minutes: int) -> datetime:
    """Floor a datetime to the nearest window boundary (UTC)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    total_seconds = int(dt.timestamp())
    window_seconds = window_minutes * 60
    floored = (total_seconds // window_seconds) * window_seconds
    return datetime.fromtimestamp(floored, tz=timezone.utc)


def _get_day_number(signal: dict) -> int | None:
    """Extract dayNumber from signal payload or metadata."""
    for source in (signal.get("payload") or {}, signal.get("metadata") or {}):
        if isinstance(source, dict) and "dayNumber" in source:
            val = source["dayNumber"]
            if isinstance(val, int):
                return val
    return None


def _get_category(signal: dict) -> str | None:
    """Extract activity category from signal payload or metadata."""
    for source in (signal.get("payload") or {}, signal.get("metadata") or {}):
        if isinstance(source, dict) and "category" in source:
            val = source["category"]
            if val and isinstance(val, str):
                return val.lower().strip()
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_alterations(
    signals: list[dict],
    window_minutes: int = 30,
) -> list[dict]:
    """
    Detect itinerary-alteration patterns within session windows.

    Args:
        signals:        List of BehavioralSignal dicts. See module docstring
                        for required/optional keys.
        window_minutes: Size of the fixed session window in minutes.
                        Defaults to 30.

    Returns:
        List of enrichment dicts, one per signal that matched a pattern:
        ``{"signal_id": str, "subflow": str, "signal_weight": float}``

        Only signals matching at least one pattern are included.
        Higher-priority patterns take precedence when a signal matches
        multiple (category_shift > date_shift > slot_swap).
    """
    if not signals:
        return []

    # ---------------------------------------------------------------------------
    # Step 1: bucket signals by (userId, window_start)
    # ---------------------------------------------------------------------------
    # window_key -> list of signal dicts
    windows: dict[tuple[str, datetime], list[dict]] = defaultdict(list)

    for sig in signals:
        user_id = sig.get("userId") or ""
        created_at = sig.get("createdAt")
        if not user_id or not created_at:
            continue
        if not isinstance(created_at, datetime):
            logger.warning("Signal %s has non-datetime createdAt, skipping", sig.get("id"))
            continue
        window_start = _floor_to_window(created_at, window_minutes)
        windows[(user_id, window_start)].append(sig)

    # ---------------------------------------------------------------------------
    # Step 2: detect patterns per window
    # ---------------------------------------------------------------------------
    # signal_id -> (subflow, weight) — highest priority match wins
    enrichments: dict[str, tuple[str, float]] = {}

    for (user_id, window_start), window_signals in windows.items():
        _process_window(window_signals, enrichments)

    # ---------------------------------------------------------------------------
    # Step 3: build output list
    # ---------------------------------------------------------------------------
    results: list[dict] = []
    for signal_id, (subflow, weight) in enrichments.items():
        results.append({
            "signal_id": signal_id,
            "subflow": subflow,
            "signal_weight": weight,
        })

    return results


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _process_window(
    window_signals: list[dict],
    enrichments: dict[str, tuple[str, float]],
) -> None:
    """
    Detect patterns within a single session window and populate enrichments.

    Mutates ``enrichments`` in-place. Priority: category_shift > date_shift > slot_swap.
    """
    swap_signals = [s for s in window_signals if s.get("signalType") in _SWAP_TYPES]
    skip_or_swap = [s for s in window_signals if s.get("signalType") in _SKIP_TYPES]

    # --- Pattern: date_shift (slot_swap where dayNumber changed) ---
    # We detect a date shift when there are 2+ slot_swap signals in the
    # window that carry different dayNumber values.
    day_numbers_seen: set[int] = set()
    date_shift_signal_ids: list[str] = []
    for sig in swap_signals:
        day = _get_day_number(sig)
        if day is not None:
            day_numbers_seen.add(day)
            sig_id = sig.get("id")
            if sig_id:
                date_shift_signal_ids.append(sig_id)
    date_shift_detected = len(day_numbers_seen) >= 2

    # --- Pattern: category_shift (2+ skip/swap of same category) ---
    # Count per category, collect signal ids per category
    category_counts: dict[str, list[str]] = defaultdict(list)
    for sig in skip_or_swap:
        cat = _get_category(sig)
        sig_id = sig.get("id")
        if cat and sig_id:
            category_counts[cat].append(sig_id)
    # Categories that hit the threshold
    category_shift_ids: set[str] = set()
    for cat, ids in category_counts.items():
        if len(ids) >= _CATEGORY_SHIFT_THRESHOLD:
            category_shift_ids.update(ids)
    category_shift_detected = bool(category_shift_ids)

    # --- Assign enrichments (priority: category > date > swap) ---
    for sig in window_signals:
        sig_id = sig.get("id")
        if not sig_id:
            continue
        signal_type = sig.get("signalType", "")

        # category_shift (highest priority)
        if category_shift_detected and sig_id in category_shift_ids:
            _maybe_set(enrichments, sig_id, _SUBFLOW_CATEGORY, _WEIGHT_CATEGORY_SHIFT)
            continue

        # date_shift (second priority)
        if date_shift_detected and sig_id in date_shift_signal_ids:
            _maybe_set(enrichments, sig_id, _SUBFLOW_DATE, _WEIGHT_DATE_SHIFT)
            continue

        # slot_swap fallback (any swap that didn't qualify for higher tier)
        if signal_type in _SWAP_TYPES:
            _maybe_set(enrichments, sig_id, _SUBFLOW_SWAP, _WEIGHT_SLOT_SWAP)


def _maybe_set(
    enrichments: dict[str, tuple[str, float]],
    signal_id: str,
    subflow: str,
    weight: float,
) -> None:
    """
    Set enrichment only if not already present (first assignment wins).

    Because we process patterns in priority order and call _maybe_set once
    per signal per pattern, this guard prevents lower-priority patterns from
    overwriting a higher-priority assignment.
    """
    if signal_id not in enrichments:
        enrichments[signal_id] = (subflow, weight)
