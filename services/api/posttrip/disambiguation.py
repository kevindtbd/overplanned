"""
Rule-based batch job for inferring IntentionSignals from BehavioralSignals.

Applies heuristic rules to detect skip reasons when explicit user feedback is unavailable.
Explicit feedback (source='explicit_feedback') always takes precedence over rule-based inferences.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import and_, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.db.models import BehavioralSignal, IntentionSignal, RawEvent, Trip

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
    session: AsyncSession, signal
) -> dict[str, Any]:
    """
    Build context dictionary from BehavioralSignal and related data.

    This extracts relevant fields from the signal and enriches with:
    - Activity metadata (category, location)
    - Weather data from raw event
    - Trip context (is_group, timing)
    - User history (previously_visited)

    NOTE: signal attributes use camelCase (SA model mirrors DB column names).
    """
    context: dict[str, Any] = {
        "signal_type": signal.signalType,
        "user_id": signal.userId,
    }

    # Extract metadata from signal
    meta = signal.signal_metadata or {}

    # Activity category (from slot or activity node)
    if "activity_category" in meta:
        context["activity_category"] = meta["activity_category"]

    # Weather condition (from raw event if available)
    if signal.slotId:
        # rawEventId not on BehavioralSignal in current schema;
        # weather comes from weatherContext or metadata
        pass

    # Check weatherContext field
    if signal.weatherContext:
        try:
            weather_data = json.loads(signal.weatherContext) if isinstance(signal.weatherContext, str) else signal.weatherContext
            if isinstance(weather_data, dict) and "condition" in weather_data:
                context["weather_condition"] = weather_data["condition"]
        except (json.JSONDecodeError, TypeError):
            pass

    # Time overrun (if previous slot ran late)
    if "time_overrun" in meta:
        context["time_overrun"] = meta["time_overrun"]

    # Distance (from slot to previous/next activity)
    if "distance_km" in meta:
        context["distance_km"] = meta["distance_km"]

    # Group trip context
    if signal.tripId:
        stmt = select(Trip).where(Trip.id == signal.tripId)
        result = await session.execute(stmt)
        trip = result.scalars().first()
        if trip:
            context["is_group_trip"] = (trip.memberCount or 1) > 1
            if "has_preference_conflict" in meta:
                context["has_preference_conflict"] = meta["has_preference_conflict"]

    # Previously visited check (simplified - would need location history)
    if "previously_visited" in meta:
        context["previously_visited"] = meta["previously_visited"]

    return context


async def infer_intention(
    session: AsyncSession, signal
) -> tuple[SkipReason, float] | None:
    """
    Apply rules to infer skip intention from behavioral signal.

    Returns (skip_reason, confidence) or None if no rule matches.
    """
    rules = load_rules()
    context = await get_signal_context(session, signal)

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


async def process_signal(session: AsyncSession, signal) -> bool:
    """
    Process a single behavioral signal, creating IntentionSignal if rule matches.

    Returns True if IntentionSignal was created, False otherwise.
    """
    # Skip if already has explicit feedback (higher confidence source)
    existing_stmt = select(IntentionSignal).where(
        and_(
            IntentionSignal.userId == signal.userId,
            IntentionSignal.behavioralSignalId == signal.id,
            IntentionSignal.source == "explicit_feedback",
        )
    )
    existing_result = await session.execute(existing_stmt)
    existing = existing_result.scalars().first()
    if existing:
        logger.debug(f"Signal {signal.id} has explicit feedback, skipping inference")
        return False

    # Skip if already has rule-based inference (idempotency)
    existing_rule_stmt = select(IntentionSignal).where(
        and_(
            IntentionSignal.userId == signal.userId,
            IntentionSignal.behavioralSignalId == signal.id,
            IntentionSignal.source == "rule_heuristic",
        )
    )
    existing_rule_result = await session.execute(existing_rule_stmt)
    existing_rule = existing_rule_result.scalars().first()
    if existing_rule:
        logger.debug(f"Signal {signal.id} already has rule inference")
        return False

    # Apply rules
    result = await infer_intention(session, signal)
    if not result:
        logger.debug(f"No rule matched for signal {signal.id}")
        return False

    skip_reason, confidence = result

    # Create IntentionSignal
    stmt = insert(IntentionSignal).values(
        id=str(uuid4()),
        userId=signal.userId,
        behavioralSignalId=signal.id,
        rawEventId=None,
        intentionType="skip_reason",
        confidence=confidence,
        source="rule_heuristic",
        userProvided=False,
        createdAt=datetime.now(timezone.utc),
    )
    await session.execute(stmt)
    await session.commit()

    logger.info(
        f"Created IntentionSignal for {signal.id}: {skip_reason} ({confidence})"
    )
    return True


async def run_disambiguation_batch(
    session: AsyncSession,
    limit: int | None = None,
    backlog: bool = False,
) -> dict[str, int]:
    """
    Run batch job to infer intentions from behavioral signals.

    Args:
        session: SA async session
        limit: Max number of signals to process (None = all)
        backlog: If True, process all historical signals without IntentionSignals

    Returns:
        Stats dict with processed/created/skipped counts
    """
    logger.info("Starting disambiguation batch job")

    # Query signals that need processing
    stmt = (
        select(BehavioralSignal)
        .where(BehavioralSignal.signalType == "post_skipped")
        .order_by(BehavioralSignal.createdAt.desc())
    )

    if limit is not None:
        stmt = stmt.limit(limit)

    result = await session.execute(stmt)
    signals = result.scalars().all()

    logger.info(f"Found {len(signals)} signals to process")

    processed = 0
    created = 0
    skipped = 0

    for signal in signals:
        processed += 1
        if await process_signal(session, signal):
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

    from services.api.db.engine import standalone_session

    async with standalone_session() as session:
        # Process full backlog on first run
        stats = await run_disambiguation_batch(session, backlog=True)
        print(f"Disambiguation batch complete: {stats}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
