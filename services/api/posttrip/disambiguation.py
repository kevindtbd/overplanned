"""
Rule-based batch job for inferring IntentionSignals from BehavioralSignals.

Applies heuristic rules to detect skip reasons when explicit user feedback is unavailable.
Explicit feedback (source='explicit_feedback') always takes precedence over rule-based inferences.
"""
import json
import logging
from pathlib import Path
from typing import Any, Literal

from prisma import Prisma
from prisma.models import BehavioralSignal, IntentionSignal

logger = logging.getLogger(__name__)

SkipReason = Literal[
    "not_interested",
    "bad_timing",
    "too_far",
    "already_visited",
    "weather",
    "group_conflict",
]

RULES_PATH = Path(__file__).parent / "disambiguation_rules.json"


def load_rules() -> list[dict[str, Any]]:
    """Load disambiguation rules from JSON config."""
    with open(RULES_PATH) as f:
        config = json.load(f)
    return config["rules"]


def matches_condition(value: Any, condition: Any) -> bool:
    """
    Check if a value matches a condition.

    Condition can be:
    - Direct value: matches if equal
    - Dict with operators: {"gt": 10}, {"lt": 5}, {"in": ["a", "b"]}
    """
    if isinstance(condition, dict):
        if "gt" in condition:
            return value > condition["gt"]
        if "lt" in condition:
            return value < condition["lt"]
        if "gte" in condition:
            return value >= condition["gte"]
        if "lte" in condition:
            return value <= condition["lte"]
        if "in" in condition:
            return value in condition["in"]
        return False
    return value == condition


def evaluate_rule(rule: dict[str, Any], context: dict[str, Any]) -> bool:
    """
    Evaluate if a rule matches the given context.

    All conditions in the rule must be satisfied.
    """
    conditions = rule["conditions"]
    for key, expected in conditions.items():
        if key not in context:
            return False
        if not matches_condition(context[key], expected):
            return False
    return True


async def get_signal_context(
    db: Prisma, signal: BehavioralSignal
) -> dict[str, Any]:
    """
    Build context dictionary from BehavioralSignal and related data.

    This extracts relevant fields from the signal and enriches with:
    - Activity metadata (category, location)
    - Weather data from raw event
    - Trip context (is_group, timing)
    - User history (previously_visited)
    """
    context: dict[str, Any] = {
        "signal_type": signal.signal_type,
        "user_id": signal.user_id,
    }

    # Extract metadata from signal
    meta = signal.metadata or {}

    # Activity category (from slot or activity node)
    if "activity_category" in meta:
        context["activity_category"] = meta["activity_category"]

    # Weather condition (from raw event if available)
    if signal.raw_event_id:
        raw_event = await db.rawevent.find_unique(where={"id": signal.raw_event_id})
        if raw_event and raw_event.payload:
            if "weather" in raw_event.payload:
                context["weather_condition"] = raw_event.payload["weather"]

    # Time overrun (if previous slot ran late)
    if "time_overrun" in meta:
        context["time_overrun"] = meta["time_overrun"]

    # Distance (from slot to previous/next activity)
    if "distance_km" in meta:
        context["distance_km"] = meta["distance_km"]

    # Group trip context
    if signal.trip_id:
        trip = await db.trip.find_unique(
            where={"id": signal.trip_id},
            include={"travelers": True}
        )
        if trip:
            context["is_group_trip"] = len(trip.travelers) > 1
            if "has_preference_conflict" in meta:
                context["has_preference_conflict"] = meta["has_preference_conflict"]

    # Previously visited check (simplified - would need location history)
    if "previously_visited" in meta:
        context["previously_visited"] = meta["previously_visited"]

    return context


async def infer_intention(
    db: Prisma, signal: BehavioralSignal
) -> tuple[SkipReason, float] | None:
    """
    Apply rules to infer skip intention from behavioral signal.

    Returns (skip_reason, confidence) or None if no rule matches.
    """
    rules = load_rules()
    context = await get_signal_context(db, signal)

    # Evaluate rules in order (first match wins)
    for rule in rules:
        if evaluate_rule(rule, context):
            intention = rule["intention"]
            confidence = rule["confidence"]
            logger.info(
                f"Rule {rule['id']} matched for signal {signal.id}: "
                f"{intention} ({confidence})"
            )
            return intention, confidence

    return None


async def process_signal(db: Prisma, signal: BehavioralSignal) -> bool:
    """
    Process a single behavioral signal, creating IntentionSignal if rule matches.

    Returns True if IntentionSignal was created, False otherwise.
    """
    # Skip if already has explicit feedback (higher confidence source)
    existing = await db.intentionsignal.find_first(
        where={
            "user_id": signal.user_id,
            "behavioral_signal_id": signal.id,
            "source": "explicit_feedback",
        }
    )
    if existing:
        logger.debug(f"Signal {signal.id} has explicit feedback, skipping inference")
        return False

    # Skip if already has rule-based inference (idempotency)
    existing_rule = await db.intentionsignal.find_first(
        where={
            "user_id": signal.user_id,
            "behavioral_signal_id": signal.id,
            "source": "rule_heuristic",
        }
    )
    if existing_rule:
        logger.debug(f"Signal {signal.id} already has rule inference")
        return False

    # Apply rules
    result = await infer_intention(db, signal)
    if not result:
        logger.debug(f"No rule matched for signal {signal.id}")
        return False

    skip_reason, confidence = result

    # Create IntentionSignal
    await db.intentionsignal.create(
        data={
            "user_id": signal.user_id,
            "behavioral_signal_id": signal.id,
            "raw_event_id": signal.raw_event_id,
            "trip_id": signal.trip_id,
            "itinerary_slot_id": signal.itinerary_slot_id,
            "activity_node_id": signal.activity_node_id,
            "intention_type": "skip_reason",
            "intention_value": skip_reason,
            "confidence": confidence,
            "source": "rule_heuristic",
            "metadata": {
                "rule_version": "1.0",
                "inferred_at": signal.created_at.isoformat(),
            },
        }
    )

    logger.info(
        f"Created IntentionSignal for {signal.id}: {skip_reason} ({confidence})"
    )
    return True


async def run_disambiguation_batch(
    db: Prisma,
    limit: int | None = None,
    backlog: bool = False,
) -> dict[str, int]:
    """
    Run batch job to infer intentions from behavioral signals.

    Args:
        db: Prisma client
        limit: Max number of signals to process (None = all)
        backlog: If True, process all historical signals without IntentionSignals

    Returns:
        Stats dict with processed/created/skipped counts
    """
    logger.info("Starting disambiguation batch job")

    # Query signals that need processing
    # Focus on post_skipped signals (main use case for skip reason inference)
    where_clause: dict[str, Any] = {
        "signal_type": "post_skipped",
    }

    if not backlog:
        # Only process recent signals (last 24h)
        # In production, this would use a timestamp filter
        pass

    signals = await db.behavioralsignal.find_many(
        where=where_clause,
        take=limit,
        order_by={"created_at": "desc"},
    )

    logger.info(f"Found {len(signals)} signals to process")

    processed = 0
    created = 0
    skipped = 0

    for signal in signals:
        processed += 1
        if await process_signal(db, signal):
            created += 1
        else:
            skipped += 1

    stats = {
        "processed": processed,
        "created": created,
        "skipped": skipped,
    }

    logger.info(f"Batch complete: {stats}")
    return stats


async def main():
    """Entry point for running as standalone script."""
    logging.basicConfig(level=logging.INFO)

    db = Prisma()
    await db.connect()

    try:
        # Process full backlog on first run
        stats = await run_disambiguation_batch(db, backlog=True)
        print(f"Disambiguation batch complete: {stats}")
    finally:
        await db.disconnect()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
