"""
RankingEvent logger -- writes a row each time the ranking pipeline serves results.

Fire-and-forget safe: exceptions are caught and logged, never raised.
Caller should not await this in the critical path if latency matters --
wrap in asyncio.create_task() when appropriate.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from services.api.db.models import RankingEvent

logger = logging.getLogger(__name__)


async def log_ranking_event(
    session: AsyncSession,
    *,
    trip_id: str,
    user_id: str,
    day_number: int,
    model_name: str,
    model_version: str,
    candidate_ids: list[str],
    ranked_ids: list[str],
    selected_ids: list[str],
    surface: str,
    session_id: str | None = None,
    shadow_model_name: str | None = None,
    shadow_model_version: str | None = None,
    shadow_ranked_ids: list[str] | None = None,
    latency_ms: int | None = None,
) -> None:
    """Insert a RankingEvent row. Never raises -- logs errors instead.

    Parameters match the Prisma RankingEvent table columns:
      - trip_id, user_id, day_number: context for the ranking
      - model_name, model_version: which model produced the ranking
      - candidate_ids: full candidate set considered
      - ranked_ids: final model-ordered ranking
      - selected_ids: which candidates were actually served to the user
      - surface: where the ranking was shown (e.g. "itinerary", "discover")
      - shadow_*: optional shadow/challenger model results for A/B logging
      - latency_ms: end-to-end ranking latency
    """
    try:
        event = RankingEvent(
            id=str(uuid.uuid4()),
            userId=user_id,
            tripId=trip_id,
            sessionId=session_id,
            dayNumber=day_number,
            modelName=model_name,
            modelVersion=model_version,
            candidateIds=candidate_ids,
            rankedIds=ranked_ids,
            selectedIds=selected_ids,
            surface=surface,
            shadowModelName=shadow_model_name,
            shadowModelVersion=shadow_model_version,
            shadowRankedIds=shadow_ranked_ids or [],
            latencyMs=latency_ms,
            createdAt=datetime.now(timezone.utc),
        )
        session.add(event)
        await session.commit()
    except Exception:
        logger.exception("Failed to log RankingEvent for trip=%s user=%s", trip_id, user_id)
        try:
            await session.rollback()
        except Exception:
            logger.exception("Rollback also failed after RankingEvent error")
