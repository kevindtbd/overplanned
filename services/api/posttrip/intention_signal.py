"""
Capture explicit skip reasons as IntentionSignals for ML training.

When users say *why* they skipped a slot (post-trip reflection),
we write the highest-confidence training signals available:
  source="user_explicit", confidence=1.0

Valid skip reasons (intentionType values):
  not_interested | bad_timing | too_far | already_visited | weather | group_conflict
"""

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.db.models import BehavioralSignal, IntentionSignal


SkipReason = Literal[
    "not_interested",
    "bad_timing",
    "too_far",
    "already_visited",
    "weather",
    "group_conflict",
]

VALID_SKIP_REASONS: set[str] = {
    "not_interested",
    "bad_timing",
    "too_far",
    "already_visited",
    "weather",
    "group_conflict",
}


async def record_skip_intention(
    session: AsyncSession,
    *,
    user_id: str,
    behavioral_signal_id: str,
    skip_reason: SkipReason,
    raw_event_id: str | None = None,
) -> dict:
    """
    Write an IntentionSignal for an explicit user-provided skip reason.

    The corresponding BehavioralSignal (signalType=post_skipped) must already
    exist; its ID is passed as behavioral_signal_id.

    Args:
        session: SA async session
        user_id: The user providing the skip reason
        behavioral_signal_id: ID of the parent BehavioralSignal (post_skipped)
        skip_reason: One of the six predefined skip reasons
        raw_event_id: Optional RawEvent ID for full audit trail

    Returns:
        The created IntentionSignal record as a dict

    Raises:
        ValueError: If skip_reason is not in VALID_SKIP_REASONS
        ValueError: If behavioral_signal_id does not exist or doesn't
                    belong to user_id with signalType=post_skipped
    """
    if skip_reason not in VALID_SKIP_REASONS:
        raise ValueError(
            f"Invalid skip reason '{skip_reason}'. "
            f"Must be one of: {', '.join(sorted(VALID_SKIP_REASONS))}"
        )

    # Verify the parent BehavioralSignal exists and belongs to this user
    stmt = select(BehavioralSignal).where(BehavioralSignal.id == behavioral_signal_id)
    result = await session.execute(stmt)
    parent_signal = result.scalars().first()

    if parent_signal is None:
        raise ValueError(
            f"BehavioralSignal '{behavioral_signal_id}' not found"
        )
    if parent_signal.userId != user_id:
        raise ValueError(
            f"BehavioralSignal '{behavioral_signal_id}' does not belong "
            f"to user '{user_id}'"
        )
    if parent_signal.signalType != "post_skipped":
        raise ValueError(
            f"BehavioralSignal '{behavioral_signal_id}' has signalType "
            f"'{parent_signal.signalType}', expected 'post_skipped'"
        )

    intention_id = str(uuid4())
    now = datetime.now(timezone.utc)

    insert_stmt = insert(IntentionSignal).values(
        id=intention_id,
        userId=user_id,
        behavioralSignalId=behavioral_signal_id,
        rawEventId=raw_event_id,
        intentionType=skip_reason,
        confidence=1.0,
        source="user_explicit",
        userProvided=True,
        createdAt=now,
    )
    await session.execute(insert_stmt)
    await session.commit()

    return {
        "id": intention_id,
        "userId": user_id,
        "behavioralSignalId": behavioral_signal_id,
        "rawEventId": raw_event_id,
        "intentionType": skip_reason,
        "confidence": 1.0,
        "source": "user_explicit",
        "userProvided": True,
        "createdAt": now.isoformat(),
    }
