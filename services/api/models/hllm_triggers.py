"""
Phase 6.6 -- HLLM Triggers (Subflow Routing)

HLLM triggers decide when to invoke the LLM for edge cases that ML models
can't handle well. These are NOT a model -- they're routing rules that detect
when to fall back to LLM.

No ML, no heavy frameworks. Pure Python routing logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Trigger Enum
# ---------------------------------------------------------------------------

class HLLMTrigger(Enum):
    COLD_USER = "cold_user"
    NOVELTY_REQUEST = "novelty_request"
    LOW_ML_CONFIDENCE = "low_ml_confidence"
    HIGH_DISAGREEMENT = "high_disagreement"
    CUISINE_SHIFT = "cuisine_shift"
    GROUP_CONTEXT = "group_context"
    PIVOT_EVENT = "pivot_event"


# ---------------------------------------------------------------------------
# Trigger Context
# ---------------------------------------------------------------------------

@dataclass
class TriggerContext:
    """All signals needed for trigger detection."""

    user_signal_count: int
    trip_count: int
    trip_member_count: int
    ml_confidence: float
    agreement_score: float
    recent_signal_categories: list[str] = field(default_factory=list)
    has_active_pivot: bool = False
    user_message: str | None = None


# ---------------------------------------------------------------------------
# Novelty keywords
# ---------------------------------------------------------------------------

NOVELTY_PHRASES = [
    "something different",
    "something new",
    "surprise me",
    "off the beaten path",
    "hidden gem",
    "hidden gems",
    "unusual",
    "unique",
    "undiscovered",
    "local secret",
    "non-touristy",
    "not touristy",
    "authentic",
    "unconventional",
]


# ---------------------------------------------------------------------------
# Subflow mapping
# ---------------------------------------------------------------------------

_TRIGGER_SUBFLOW_MAP: dict[HLLMTrigger, str] = {
    HLLMTrigger.COLD_USER: "llm_cold_start",
    HLLMTrigger.NOVELTY_REQUEST: "llm_novelty_generation",
    HLLMTrigger.LOW_ML_CONFIDENCE: "llm_low_confidence_fallback",
    HLLMTrigger.HIGH_DISAGREEMENT: "llm_disagreement_resolution",
    HLLMTrigger.CUISINE_SHIFT: "llm_category_exploration",
    HLLMTrigger.GROUP_CONTEXT: "llm_group_consensus",
    HLLMTrigger.PIVOT_EVENT: "llm_pivot_handling",
}


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class HLLMTriggerDetector:
    """
    Detects when to route to LLM instead of (or alongside) ML ranking.

    Each trigger has an independent check function. Multiple triggers can
    fire simultaneously.
    """

    def __init__(
        self,
        cold_user_threshold: int = 3,
        low_confidence_threshold: float = 0.3,
        high_disagreement_threshold: float = 0.2,
        group_size_threshold: int = 3,
        cuisine_shift_ratio: float = 0.6,
    ) -> None:
        self.cold_user_threshold = cold_user_threshold
        self.low_confidence_threshold = low_confidence_threshold
        self.high_disagreement_threshold = high_disagreement_threshold
        self.group_size_threshold = group_size_threshold
        self.cuisine_shift_ratio = cuisine_shift_ratio

    def _check_cold_user(self, ctx: TriggerContext) -> bool:
        """User has fewer than threshold completed trips."""
        return ctx.trip_count < self.cold_user_threshold

    def _check_novelty_request(self, ctx: TriggerContext) -> bool:
        """User explicitly asks for something new/different."""
        if not ctx.user_message:
            return False
        msg_lower = ctx.user_message.lower()
        return any(phrase in msg_lower for phrase in NOVELTY_PHRASES)

    def _check_low_ml_confidence(self, ctx: TriggerContext) -> bool:
        """ML ranker confidence below threshold."""
        return ctx.ml_confidence < self.low_confidence_threshold

    def _check_high_disagreement(self, ctx: TriggerContext) -> bool:
        """ML and LLM rankings have overlap@5 below threshold."""
        return ctx.agreement_score < self.high_disagreement_threshold

    def _check_cuisine_shift(self, ctx: TriggerContext) -> bool:
        """Recent signals show a category shift (majority differs from minority)."""
        cats = ctx.recent_signal_categories
        if len(cats) < 3:
            return False
        # If the most recent category differs from the majority of older ones
        recent = cats[-1]
        older = cats[:-1]
        older_different = sum(1 for c in older if c != recent)
        return older_different / len(older) >= self.cuisine_shift_ratio

    def _check_group_context(self, ctx: TriggerContext) -> bool:
        """Trip has 3+ members."""
        return ctx.trip_member_count >= self.group_size_threshold

    def _check_pivot_event(self, ctx: TriggerContext) -> bool:
        """Active pivot event on the trip."""
        return ctx.has_active_pivot

    def detect_triggers(self, context: TriggerContext) -> list[HLLMTrigger]:
        """
        Run all trigger checks and return list of fired triggers.

        Multiple triggers can fire simultaneously.
        """
        fired: list[HLLMTrigger] = []

        checks: list[tuple[HLLMTrigger, Any]] = [
            (HLLMTrigger.COLD_USER, self._check_cold_user),
            (HLLMTrigger.NOVELTY_REQUEST, self._check_novelty_request),
            (HLLMTrigger.LOW_ML_CONFIDENCE, self._check_low_ml_confidence),
            (HLLMTrigger.HIGH_DISAGREEMENT, self._check_high_disagreement),
            (HLLMTrigger.CUISINE_SHIFT, self._check_cuisine_shift),
            (HLLMTrigger.GROUP_CONTEXT, self._check_group_context),
            (HLLMTrigger.PIVOT_EVENT, self._check_pivot_event),
        ]

        for trigger, check_fn in checks:
            if check_fn(context):
                fired.append(trigger)

        return fired

    @staticmethod
    def should_use_llm(triggers: list[HLLMTrigger]) -> bool:
        """Any trigger fires = use LLM."""
        return len(triggers) > 0

    @staticmethod
    def get_subflow_for_triggers(triggers: list[HLLMTrigger]) -> str:
        """
        Map fired triggers to a subflow name for BehavioralSignal logging.

        If multiple triggers fire, returns the highest-priority subflow
        (first in the trigger list, which follows detection order).
        """
        if not triggers:
            return "ml_default"

        # Return subflow for the first (highest-priority) trigger
        return _TRIGGER_SUBFLOW_MAP.get(triggers[0], "llm_generic_fallback")
