"""
Admin Source Freshness: Monitor scraper health, source staleness, and authority scores.

Endpoints:
  GET  /admin/sources           — List all sources with freshness + stats
  GET  /admin/sources/alerts    — Stale sources exceeding configured thresholds
  PATCH /admin/sources/:name    — Update authority score (audit logged)
  GET  /admin/sources/config    — Current staleness thresholds
  PUT  /admin/sources/config    — Update staleness thresholds (audit logged)

Source data derived from QualitySignal aggregate by sourceName.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field

from services.api.middleware.audit import audit_action
from services.api.routers._admin_deps import require_admin_user, get_db

router = APIRouter(prefix="/admin/sources", tags=["admin-sources"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class SourceSummary(BaseModel):
    source_name: str
    signal_count: int
    node_count: int
    avg_authority: float
    min_authority: float
    max_authority: float
    last_scraped_at: Optional[str]
    oldest_signal_at: Optional[str]
    is_stale: bool
    staleness_hours: Optional[float]


class SourceListResponse(BaseModel):
    sources: list[SourceSummary]
    total: int
    stale_count: int


class StaleAlert(BaseModel):
    source_name: str
    last_scraped_at: Optional[str]
    threshold_hours: int
    hours_since_scrape: Optional[float]
    signal_count: int


class AlertsResponse(BaseModel):
    alerts: list[StaleAlert]
    total: int


class AuthorityUpdate(BaseModel):
    authority_score: float = Field(..., ge=0.0, le=1.0)


class StalenessConfig(BaseModel):
    default_threshold_hours: int = Field(default=72, ge=1, le=8760)
    per_source: dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Staleness config (Redis-backed for persistence)
# ---------------------------------------------------------------------------

STALENESS_CONFIG_KEY = "admin:sources:staleness_config"
DEFAULT_THRESHOLD_HOURS = 72


async def _get_staleness_config(redis) -> StalenessConfig:
    """Load staleness config from Redis, or return defaults."""
    import json
    raw = await redis.get(STALENESS_CONFIG_KEY)
    if raw:
        data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
        return StalenessConfig(**data)
    return StalenessConfig()


async def _set_staleness_config(redis, config: StalenessConfig) -> None:
    """Persist staleness config to Redis."""
    import json
    await redis.set(STALENESS_CONFIG_KEY, json.dumps(config.model_dump()))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hours_since(dt: Optional[datetime]) -> Optional[float]:
    """Compute hours since a datetime, or None if dt is None."""
    if dt is None:
        return None
    delta = datetime.now(timezone.utc) - dt.replace(tzinfo=timezone.utc)
    return round(delta.total_seconds() / 3600, 1)


def _threshold_for_source(config: StalenessConfig, source_name: str) -> int:
    """Get staleness threshold for a specific source."""
    return config.per_source.get(source_name, config.default_threshold_hours)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=SourceListResponse)
async def list_sources(
    request: Request,
    db=Depends(get_db),
    actor_id: str = Depends(require_admin_user),
):
    """
    List all known scraper sources with freshness metrics.
    Aggregated from QualitySignal grouped by sourceName.
    """
    redis = request.app.state.redis
    config = await _get_staleness_config(redis)

    # Aggregate source stats from QualitySignal
    # Raw SQL for aggregation since Prisma doesn't support groupBy well
    results = await db.query_raw(
        """
        SELECT
            "sourceName" as source_name,
            COUNT(*)::int as signal_count,
            COUNT(DISTINCT "activityNodeId")::int as node_count,
            ROUND(AVG("sourceAuthority")::numeric, 3)::float as avg_authority,
            ROUND(MIN("sourceAuthority")::numeric, 3)::float as min_authority,
            ROUND(MAX("sourceAuthority")::numeric, 3)::float as max_authority,
            MAX("extractedAt") as last_scraped_at,
            MIN("extractedAt") as oldest_signal_at
        FROM "QualitySignal"
        GROUP BY "sourceName"
        ORDER BY MAX("extractedAt") DESC NULLS LAST
        """
    )

    now = datetime.now(timezone.utc)
    sources = []
    stale_count = 0

    for row in results:
        last_scraped = row.get("last_scraped_at")
        staleness = _hours_since(last_scraped) if last_scraped else None
        threshold = _threshold_for_source(config, row["source_name"])
        is_stale = staleness is not None and staleness > threshold

        if is_stale:
            stale_count += 1

        sources.append(SourceSummary(
            source_name=row["source_name"],
            signal_count=row["signal_count"],
            node_count=row["node_count"],
            avg_authority=row["avg_authority"],
            min_authority=row["min_authority"],
            max_authority=row["max_authority"],
            last_scraped_at=last_scraped.isoformat() if last_scraped else None,
            oldest_signal_at=row["oldest_signal_at"].isoformat() if row.get("oldest_signal_at") else None,
            is_stale=is_stale,
            staleness_hours=staleness,
        ))

    return SourceListResponse(
        sources=sources,
        total=len(sources),
        stale_count=stale_count,
    )


@router.get("/alerts", response_model=AlertsResponse)
async def get_alerts(
    request: Request,
    db=Depends(get_db),
    actor_id: str = Depends(require_admin_user),
):
    """Return only stale sources exceeding their configured threshold."""
    redis = request.app.state.redis
    config = await _get_staleness_config(redis)

    results = await db.query_raw(
        """
        SELECT
            "sourceName" as source_name,
            COUNT(*)::int as signal_count,
            MAX("extractedAt") as last_scraped_at
        FROM "QualitySignal"
        GROUP BY "sourceName"
        ORDER BY MAX("extractedAt") ASC NULLS FIRST
        """
    )

    alerts = []
    for row in results:
        last_scraped = row.get("last_scraped_at")
        hours_since = _hours_since(last_scraped) if last_scraped else None
        threshold = _threshold_for_source(config, row["source_name"])

        # Stale if: no scrape ever, or exceeded threshold
        if hours_since is None or hours_since > threshold:
            alerts.append(StaleAlert(
                source_name=row["source_name"],
                last_scraped_at=last_scraped.isoformat() if last_scraped else None,
                threshold_hours=threshold,
                hours_since_scrape=hours_since,
                signal_count=row["signal_count"],
            ))

    return AlertsResponse(alerts=alerts, total=len(alerts))


@router.patch("/{source_name}")
async def update_source_authority(
    source_name: str,
    body: AuthorityUpdate,
    request: Request,
    db=Depends(get_db),
    actor_id: str = Depends(require_admin_user),
):
    """
    Bulk-update authority score for all QualitySignals from a given source.
    Logged to AuditLog with before/after snapshots.
    """
    # Get current authority stats for before snapshot
    before_stats = await db.query_raw(
        """
        SELECT
            ROUND(AVG("sourceAuthority")::numeric, 3)::float as avg_authority,
            ROUND(MIN("sourceAuthority")::numeric, 3)::float as min_authority,
            ROUND(MAX("sourceAuthority")::numeric, 3)::float as max_authority,
            COUNT(*)::int as signal_count
        FROM "QualitySignal"
        WHERE "sourceName" = $1
        """,
        source_name,
    )

    if not before_stats or before_stats[0]["signal_count"] == 0:
        raise HTTPException(status_code=404, detail=f"No signals found for source: {source_name}")

    before = before_stats[0]

    # Update all signals for this source
    update_count = await db.execute_raw(
        """
        UPDATE "QualitySignal"
        SET "sourceAuthority" = $1
        WHERE "sourceName" = $2
        """,
        body.authority_score,
        source_name,
    )

    after = {
        "avg_authority": body.authority_score,
        "min_authority": body.authority_score,
        "max_authority": body.authority_score,
        "signal_count": before["signal_count"],
    }

    await audit_action(
        db=db,
        request=request,
        actor_id=actor_id,
        action="source.authority.update",
        target_type="QualitySignal",
        target_id=source_name,
        before=before,
        after={**after, "new_authority": body.authority_score},
    )

    return {
        "source_name": source_name,
        "updated_count": update_count,
        "new_authority": body.authority_score,
        "audit_action": "source.authority.update",
    }


@router.get("/config", response_model=StalenessConfig)
async def get_staleness_config(
    request: Request,
    actor_id: str = Depends(require_admin_user),
):
    """Return current staleness threshold configuration."""
    redis = request.app.state.redis
    return await _get_staleness_config(redis)


@router.put("/config", response_model=StalenessConfig)
async def update_staleness_config(
    body: StalenessConfig,
    request: Request,
    db=Depends(get_db),
    actor_id: str = Depends(require_admin_user),
):
    """
    Update staleness thresholds. Changes audit-logged.
    """
    redis = request.app.state.redis

    before = await _get_staleness_config(redis)
    await _set_staleness_config(redis, body)

    await audit_action(
        db=db,
        request=request,
        actor_id=actor_id,
        action="source.config.update",
        target_type="StalenessConfig",
        target_id="global",
        before=before.model_dump(),
        after=body.model_dump(),
    )

    return body
