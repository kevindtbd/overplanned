"""
Subflows package — V2 ML Pipeline Phase 5.

Public exports for all subflow feature modules.

  Phase 5.1 — rejection_recovery  : burst rejection detection + recovery
  Phase 5.2 — repeat_city         : repeat-city pre-filter and boost
  Phase 5.3 — slot_fitter         : mid-trip slot insertion with cascade
  Phase 5.4 — diversifier         : MMR post-processing for diversity
  Phase 5.5 — split_detector      : bimodal group split detection
"""

from services.api.subflows.rejection_recovery import (
    check_rejection_burst,
    reset_fired_trips,
    BURST_THRESHOLD,
    BURST_WINDOW_SECONDS,
    RECOVERY_WEIGHT_CAP,
)
from services.api.subflows.repeat_city import (
    apply_repeat_city_boost,
    BOOST_MULTIPLIER,
)
from services.api.subflows.slot_fitter import (
    fit_slot,
    CASCADE_LIMIT,
    MEAL_SLOT_TYPES,
)
from services.api.subflows.diversifier import (
    apply_mmr_diversification,
    generate_alternatives,
    DEFAULT_LAMBDA,
)
from services.api.subflows.split_detector import (
    detect_group_split,
    reset_suggestion_log,
    VARIANCE_THRESHOLD,
    MIN_DIVERGENT_DIMENSIONS,
    MAX_SPLITS_PER_TRIP_PER_DAY,
)

__all__ = [
    # rejection_recovery
    "check_rejection_burst",
    "reset_fired_trips",
    "BURST_THRESHOLD",
    "BURST_WINDOW_SECONDS",
    "RECOVERY_WEIGHT_CAP",
    # repeat_city
    "apply_repeat_city_boost",
    "BOOST_MULTIPLIER",
    # slot_fitter
    "fit_slot",
    "CASCADE_LIMIT",
    "MEAL_SLOT_TYPES",
    # diversifier
    "apply_mmr_diversification",
    "generate_alternatives",
    "DEFAULT_LAMBDA",
    # split_detector
    "detect_group_split",
    "reset_suggestion_log",
    "VARIANCE_THRESHOLD",
    "MIN_DIVERGENT_DIMENSIONS",
    "MAX_SPLITS_PER_TRIP_PER_DAY",
]
