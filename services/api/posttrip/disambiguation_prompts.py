"""
Post-trip disambiguation UX support.

Surfaces targeted questions to users for ItinerarySlots whose outcome is
genuinely ambiguous after the trip ends. Resolving these prompts creates
BehavioralSignals that feed into the nightly write-back and persona updates.

Public API:
    get_disambiguation_prompts(db, trip_id, max_prompts=3) -> list[dict]
    resolve_disambiguation(db, slot_id, user_id, response_value) -> dict

signal_weight values are SERVER-ONLY — they must never be included in any
client-facing response payload.

All weights stay within the DB CHECK constraint range [-1.0, 3.0].
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Response option definitions — server-side only
# ---------------------------------------------------------------------------

# signal_weight is intentionally NOT returned to the client.
_RESPONSE_OPTIONS: list[dict[str, Any]] = [
    {
        "label": "Yes, I went",
        "value": "confirmed_attended",
        "signal_weight": 0.7,
    },
    {
        "label": "No, not my thing",
        "value": "confirmed_skipped_preference",
        "signal_weight": -0.3,
    },
    {
        "label": "No, timing didn't work",
        "value": "confirmed_skipped_timing",
        "signal_weight": 0.0,
    },
]

# Mapping from response_value -> (completionSignal, signal_weight, update_persona)
_RESPONSE_MAP: dict[str, tuple[str, float, bool]] = {
    "confirmed_attended":          ("confirmed_attended",        0.7,  True),
    "confirmed_skipped_preference": ("confirmed_skipped",        -0.3, True),
    "confirmed_skipped_timing":     ("confirmed_skipped",         0.0, False),
}


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def _client_options() -> list[dict[str, str]]:
    """Return response options stripped of server-only signal_weight."""
    return [
        {"label": opt["label"], "value": opt["value"]}
        for opt in _RESPONSE_OPTIONS
    ]


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

async def get_disambiguation_prompts(
    db: Any,
    trip_id: str,
    max_prompts: int = 3,
) -> list[dict[str, Any]]:
    """
    Return up to max_prompts disambiguation prompts for a completed trip.

    Only ItinerarySlots with completionSignal = 'no_show_ambiguous' are
    considered. Slots are ordered by dayNumber ascending so prompts appear
    in chronological order.

    The returned dicts are safe to send to the client — signal_weight is
    not included.

    Args:
        db:          Prisma client (or compatible AsyncMock in tests).
        trip_id:     ID of the completed trip.
        max_prompts: Maximum number of prompts to return (default 3).

    Returns:
        List of prompt dicts::

            {
                "slotId": str,
                "activityName": str,
                "dayNumber": int,
                "question": str,
                "options": [{"label": str, "value": str}],
            }
    """
    # Fetch ambiguous slots with their linked ActivityNode for the name
    slots = await db.itineraryslot.find_many(
        where={
            "tripId": trip_id,
            "completionSignal": "no_show_ambiguous",
        },
        include={"activityNode": True},
        order_by={"dayNumber": "asc"},
        take=max_prompts,
    )

    prompts: list[dict[str, Any]] = []
    for slot in slots:
        activity_name = (
            slot.activityNode.name
            if slot.activityNode
            else "this activity"
        )
        prompts.append({
            "slotId": slot.id,
            "activityName": activity_name,
            "dayNumber": slot.dayNumber,
            "question": f"Did you end up going to {activity_name}?",
            "options": _client_options(),
        })

    logger.info(
        "disambiguation_prompts: trip=%s ambiguous_slots=%d returned=%d",
        trip_id,
        len(slots),
        len(prompts),
    )
    return prompts


async def resolve_disambiguation(
    db: Any,
    slot_id: str,
    user_id: str,
    response_value: str,
) -> dict[str, Any]:
    """
    Resolve a disambiguation prompt by recording the user's answer.

    Side effects:
    - Updates ItinerarySlot.completionSignal to the resolved value.
    - Creates a BehavioralSignal with appropriate signal_weight and subflow.

    For 'confirmed_skipped_preference', an additional negative-preference
    signal is created to inform future persona modeling.

    Args:
        db:             Prisma client.
        slot_id:        ItinerarySlot ID being resolved.
        user_id:        ID of the user submitting the response.
        response_value: One of 'confirmed_attended',
                        'confirmed_skipped_preference',
                        'confirmed_skipped_timing'.

    Returns:
        A result dict::

            {
                "slotId": str,
                "completionSignal": str,
                "signalCreated": bool,
            }

    Raises:
        ValueError if response_value is not a recognised option.
    """
    if response_value not in _RESPONSE_MAP:
        raise ValueError(
            f"Unknown response_value '{response_value}'. "
            f"Valid options: {list(_RESPONSE_MAP)}"
        )

    completion_signal, signal_weight, update_persona = _RESPONSE_MAP[response_value]

    # Fetch the slot so we can pull tripId and activityNodeId for the signal
    slot = await db.itineraryslot.find_unique(
        where={"id": slot_id},
        include={"activityNode": True},
    )

    trip_id = slot.tripId if slot else None
    activity_node_id = slot.activityNodeId if slot else None

    # Update slot completionSignal
    await db.itineraryslot.update(
        where={"id": slot_id},
        data={"completionSignal": completion_signal},
    )

    # Create primary BehavioralSignal
    await db.behavioralsignal.create(
        data={
            "userId": user_id,
            "tripId": trip_id,
            "slotId": slot_id,
            "activityNodeId": activity_node_id,
            "signalType": "post_disambiguation",
            "signalValue": signal_weight,
            "tripPhase": "post_trip",
            "rawAction": response_value,
            "subflow": "disambiguation_resolution",
            "signal_weight": signal_weight,
            "source": "explicit_feedback",
        }
    )

    # For preference skips, emit an additional negative-preference signal
    # so persona modeling sees this as a genuine anti-preference.
    if response_value == "confirmed_skipped_preference":
        await db.behavioralsignal.create(
            data={
                "userId": user_id,
                "tripId": trip_id,
                "slotId": slot_id,
                "activityNodeId": activity_node_id,
                "signalType": "negative_preference",
                "signalValue": signal_weight,
                "tripPhase": "post_trip",
                "rawAction": "explicit_negative_preference",
                "subflow": "disambiguation_resolution",
                "signal_weight": signal_weight,
                "source": "explicit_feedback",
            }
        )
        logger.info(
            "resolve_disambiguation: slot=%s preference skip recorded, "
            "negative preference signal created",
            slot_id,
        )

    logger.info(
        "resolve_disambiguation: slot=%s user=%s response=%s "
        "completion_signal=%s update_persona=%s",
        slot_id,
        user_id,
        response_value,
        completion_signal,
        update_persona,
    )

    return {
        "slotId": slot_id,
        "completionSignal": completion_signal,
        "signalCreated": True,
    }
