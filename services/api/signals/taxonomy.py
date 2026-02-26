"""
Signal taxonomy — defines training weights and polarity for all BehavioralSignal types.

Tier 1 (Explicit):       weight 1.0  — direct user intent
Tier 2 (Strong Implicit): weight 0.7 — strong behavioral cues
Tier 3 (Weak Implicit):   weight 0.3 — ambient interaction signals
Tier 4 (Passive):         weight 0.1 — system-observed events
"""

# ---------------------------------------------------------------------------
# Signal weights — maps signalType string to training weight
# ---------------------------------------------------------------------------

SIGNAL_WEIGHTS: dict[str, float] = {
    # Tier 1 — Explicit (1.0)
    "slot_confirmed": 1.0,
    "slot_rejected": 1.0,
    "pre_trip_slot_swap": 1.0,
    "pre_trip_slot_removed": 1.0,
    # Tier 2 — Strong Implicit (0.7)
    "slot_locked": 0.7,
    "pre_trip_slot_added": 0.7,
    "pre_trip_reorder": 0.7,
    "discover_shortlist": 0.7,
    # Tier 3 — Weak Implicit (0.3)
    "card_viewed": 0.3,
    "card_dismissed": 0.3,
    "slot_moved": 0.3,
    "discover_swipe_right": 0.3,
    "discover_swipe_left": 0.3,
    # Tier 4 — Passive (0.1)
    "card_impression": 0.1,
    "pivot_accepted": 0.1,
    "pivot_rejected": 0.1,
}

_DEFAULT_WEIGHT = 0.1

# Sets for O(1) polarity checks
_POSITIVE_SIGNALS: frozenset[str] = frozenset({
    "slot_confirmed",
    "slot_locked",
    "pre_trip_slot_added",
    "discover_shortlist",
    "discover_swipe_right",
    "pivot_accepted",
})

_NEGATIVE_SIGNALS: frozenset[str] = frozenset({
    "slot_rejected",
    "pre_trip_slot_removed",
    "discover_swipe_left",
    "pivot_rejected",
    "card_dismissed",
})


def get_training_weight(signal_type: str) -> float:
    """Return the training weight for a signal type. Unknown types default to 0.1."""
    return SIGNAL_WEIGHTS.get(signal_type, _DEFAULT_WEIGHT)


def is_positive_signal(signal_type: str) -> bool:
    """True when the signal indicates user preference / approval."""
    return signal_type in _POSITIVE_SIGNALS


def is_negative_signal(signal_type: str) -> bool:
    """True when the signal indicates user rejection / disinterest."""
    return signal_type in _NEGATIVE_SIGNALS
