"""Admin routes for Pipeline D research jobs + conflict resolution."""
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def list_research_jobs(session: AsyncSession, city_slug: Optional[str] = None, limit: int = 50) -> list[dict]:
    sql = 'SELECT id, "cityId", status, "triggeredBy", "modelVersion", "totalCostUsd", "venuesResearched", "venuesResolved", "venuesUnresolved", "createdAt", "completedAt" FROM research_jobs'
    params: dict = {}
    if city_slug:
        sql += ' WHERE "cityId" = :city'
        params["city"] = city_slug
    sql += ' ORDER BY "createdAt" DESC LIMIT :limit'
    params["limit"] = limit
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings().all()]


async def list_conflicts(session: AsyncSession, city_slug: str) -> list[dict]:
    result = await session.execute(text("""
        SELECT cr.id, cr."activityNodeId", cr."tagAgreementScore",
               cr."touristScoreDelta", cr."signalConflict",
               cr."mergedConfidence", cr."resolutionAction",
               an."canonicalName", an."convergenceScore", an.tourist_score
        FROM cross_reference_results cr
        JOIN activity_nodes an ON an.id = cr."activityNodeId"
        WHERE cr."cityId" = :city AND cr."signalConflict" = true AND cr."resolvedAt" IS NULL
        ORDER BY cr."touristScoreDelta" DESC NULLS LAST
    """), {"city": city_slug})
    return [dict(r) for r in result.mappings().all()]


async def resolve_conflict(session: AsyncSession, cross_ref_id: str, action: str, resolved_by: str) -> bool:
    result = await session.execute(text("""
        UPDATE cross_reference_results
        SET "resolvedBy" = :resolved_by, "resolvedAt" = :now, "resolutionAction" = :action
        WHERE id = :id AND "resolvedAt" IS NULL
    """), {"id": cross_ref_id, "resolved_by": resolved_by, "now": _now(), "action": action})
    await session.commit()
    return result.rowcount > 0
