"""
Slot Outcome Classifier — V2 ML Pipeline Phase 1.1.

Classifies each ItinerarySlot into a SlotCompletionSignal state after a trip
completes. The result is written back to the ``completionSignal`` column so
downstream training-data pipelines have a clean, normalized label.

Classification is purely deterministic (no LLM, no model inference). The
mapping from slot fields to outcome state is stable and auditable.

States
------
confirmed_attended  — slot.status == "completed" (explicit app signal)
likely_attended     — slot.status in {"confirmed", "active"} (confirmed but
                      no completion tap recorded; most likely attended)
confirmed_skipped   — slot.status == "skipped" (explicit skip signal)
pivot_replaced      — slot had a pivot event AND wasSwapped=True (neutral
                      for preference; the *new* slot carries the preference)
no_show_ambiguous   — everything else; held out from training until
                      disambiguation resolves it

Signal weights (SERVER-ONLY — never exposed to client)
-------------------------------------------------------
These weights are applied when the signal is used as a training example.
The CHECK constraint on the DB column enforces [-1.0, 3.0].
"""

from __future__ import annotations

from typing import Literal

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

SlotCompletionSignal = Literal[
    "confirmed_attended",
    "likely_attended",
    "confirmed_skipped",
    "pivot_replaced",
    "no_show_ambiguous",
]

# ---------------------------------------------------------------------------
# Training weights (server-side only)
# ---------------------------------------------------------------------------

COMPLETION_WEIGHTS: dict[str, float] = {
    "confirmed_attended": 1.0,
    "likely_attended": 0.7,
    "confirmed_skipped": -0.3,
    "pivot_replaced": 0.0,   # neutral — the pivot path itself is informative
    "no_show_ambiguous": 0.0,  # no signal until disambiguation resolves it
}

# Ordered set of statuses that indicate a slot was likely attended
_LIKELY_ATTENDED_STATUSES: frozenset[str] = frozenset({"confirmed", "active"})


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

def classify_slot_outcome(slot: dict) -> SlotCompletionSignal:
    """
    Classify an ItinerarySlot dict into a SlotCompletionSignal state.

    Priority order (first match wins):
      1. pivot_replaced  — pivotEventId is set AND wasSwapped is True
      2. confirmed_attended — status == "completed"
      3. confirmed_skipped  — status == "skipped"
      4. likely_attended    — status in {"confirmed", "active"}
      5. no_show_ambiguous  — fallback for everything else

    Args:
        slot: ItinerarySlot dict. The following keys are inspected:
              ``pivotEventId``, ``wasSwapped``, ``status``.
              Missing or None values are treated as falsy.

    Returns:
        A SlotCompletionSignal literal string.
    """
    pivot_event_id = slot.get("pivotEventId")
    was_swapped = slot.get("wasSwapped") or False
    status = slot.get("status") or ""

    # Rule 1: pivot replaced — pivot event exists AND slot was actually swapped out
    if pivot_event_id and was_swapped:
        return "pivot_replaced"

    # Rule 2: explicit completion tap in the app
    if status == "completed":
        return "confirmed_attended"

    # Rule 3: explicit skip action
    if status == "skipped":
        return "confirmed_skipped"

    # Rule 4: was confirmed/active — very likely attended, no completion tap
    if status in _LIKELY_ATTENDED_STATUSES:
        return "likely_attended"

    # Rule 5: fallback — proposed, archived, or any unknown status
    return "no_show_ambiguous"


def get_completion_weight(signal: SlotCompletionSignal) -> float:
    """
    Return the training weight for a given SlotCompletionSignal.

    This is a convenience accessor used by the training-data pipeline.
    Weights are clamped to the DB CHECK constraint range [-1.0, 3.0].

    Args:
        signal: A SlotCompletionSignal literal.

    Returns:
        float in [-1.0, 3.0]
    """
    return COMPLETION_WEIGHTS[signal]
