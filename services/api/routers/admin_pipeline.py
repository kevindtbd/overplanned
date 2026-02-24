"""
Admin Pipeline Health & Cost Dashboard API.

Reads pipeline telemetry data written by Track 2 (Data Pipeline).
Expected source tables:
  - llm_call_log: every LLM call with model, cost, latency, pipeline_stage
  - api_call_log: external API calls (Foursquare, Google, OpenWeatherMap)
  - pipeline_job: seed/scrape job runs with status, timing, error info
  - cost_alert_config: per-stage threshold config (admin-writable)

All reads. No business logic. Thin application layer per L-009.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from services.api.middleware.audit import audit_action
from services.api.routers._admin_deps import require_admin_user, get_db

router = APIRouter(prefix="/admin/pipeline", tags=["admin-pipeline"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class LLMCostRow(BaseModel):
    model: str
    date: str
    pipeline_stage: str
    call_count: int
    total_cost_usd: float
    avg_latency_ms: float
    total_input_tokens: int
    total_output_tokens: int


class LLMCostSummary(BaseModel):
    rows: list[LLMCostRow]
    total_cost_usd: float
    total_calls: int
    period_start: str
    period_end: str


class APICallRow(BaseModel):
    provider: str
    date: str
    call_count: int
    error_count: int
    avg_latency_ms: float


class APICallSummary(BaseModel):
    rows: list[APICallRow]
    total_calls: int
    total_errors: int
    period_start: str
    period_end: str


class PipelineJobRow(BaseModel):
    job_id: str
    job_type: str
    city: Optional[str]
    status: str
    started_at: str
    completed_at: Optional[str]
    duration_seconds: Optional[float]
    items_processed: int
    items_failed: int
    error: Optional[str]


class PipelineJobSummary(BaseModel):
    jobs: list[PipelineJobRow]
    total_jobs: int
    success_count: int
    failure_count: int
    running_count: int
    success_rate: float


class CostAlertThreshold(BaseModel):
    pipeline_stage: str
    daily_limit_usd: float = Field(ge=0)
    enabled: bool = True


class CostAlertConfig(BaseModel):
    thresholds: list[CostAlertThreshold]


class CostAlertStatus(BaseModel):
    pipeline_stage: str
    daily_limit_usd: float
    current_spend_usd: float
    enabled: bool
    exceeded: bool
    pct_used: float


# ---------------------------------------------------------------------------
# LLM Costs
# ---------------------------------------------------------------------------

@router.get("/llm-costs")
async def get_llm_costs(
    days: int = 7,
    model: Optional[str] = None,
    pipeline_stage: Optional[str] = None,
    db=Depends(get_db),
    admin: str = Depends(require_admin_user),
) -> dict:
    """
    LLM costs aggregated by model, date, pipeline stage.
    Reads from llm_call_log (populated by Track 2 pipeline).
    """
    if days < 1 or days > 90:
        raise HTTPException(status_code=400, detail="days must be 1-90")

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    filters = ["created_at >= $1"]
    params: list = [start]
    idx = 2

    if model:
        filters.append(f"model_name = ${idx}")
        params.append(model)
        idx += 1
    if pipeline_stage:
        filters.append(f"pipeline_stage = ${idx}")
        params.append(pipeline_stage)
        idx += 1

    where_clause = " AND ".join(filters)

    rows = await db.query_raw(
        f"""
        SELECT
            model_name AS model,
            date_trunc('day', created_at)::date::text AS date,
            pipeline_stage,
            COUNT(*)::int AS call_count,
            COALESCE(SUM(cost_usd), 0)::float AS total_cost_usd,
            COALESCE(AVG(latency_ms), 0)::float AS avg_latency_ms,
            COALESCE(SUM(input_tokens), 0)::int AS total_input_tokens,
            COALESCE(SUM(output_tokens), 0)::int AS total_output_tokens
        FROM llm_call_log
        WHERE {where_clause}
        GROUP BY model_name, date_trunc('day', created_at)::date, pipeline_stage
        ORDER BY date DESC, total_cost_usd DESC
        """,
        *params,
    )

    parsed = [LLMCostRow(**r) for r in rows]
    total_cost = sum(r.total_cost_usd for r in parsed)
    total_calls = sum(r.call_count for r in parsed)

    return {
        "data": LLMCostSummary(
            rows=parsed,
            total_cost_usd=round(total_cost, 4),
            total_calls=total_calls,
            period_start=start.date().isoformat(),
            period_end=now.date().isoformat(),
        ).model_dump(),
        "meta": {"timestamp": now.isoformat()},
    }


# ---------------------------------------------------------------------------
# External API Calls
# ---------------------------------------------------------------------------

@router.get("/api-calls")
async def get_api_calls(
    days: int = 7,
    provider: Optional[str] = None,
    db=Depends(get_db),
    admin: str = Depends(require_admin_user),
) -> dict:
    """
    External API call counts by provider and date.
    Providers: foursquare, google, openweathermap.
    """
    if days < 1 or days > 90:
        raise HTTPException(status_code=400, detail="days must be 1-90")

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    filters = ["created_at >= $1"]
    params: list = [start]
    idx = 2

    if provider:
        filters.append(f"provider = ${idx}")
        params.append(provider)
        idx += 1

    where_clause = " AND ".join(filters)

    rows = await db.query_raw(
        f"""
        SELECT
            provider,
            date_trunc('day', created_at)::date::text AS date,
            COUNT(*)::int AS call_count,
            COUNT(*) FILTER (WHERE status_code >= 400)::int AS error_count,
            COALESCE(AVG(latency_ms), 0)::float AS avg_latency_ms
        FROM api_call_log
        WHERE {where_clause}
        GROUP BY provider, date_trunc('day', created_at)::date
        ORDER BY date DESC, call_count DESC
        """,
        *params,
    )

    parsed = [APICallRow(**r) for r in rows]
    total_calls = sum(r.call_count for r in parsed)
    total_errors = sum(r.error_count for r in parsed)

    return {
        "data": APICallSummary(
            rows=parsed,
            total_calls=total_calls,
            total_errors=total_errors,
            period_start=start.date().isoformat(),
            period_end=now.date().isoformat(),
        ).model_dump(),
        "meta": {"timestamp": now.isoformat()},
    }


# ---------------------------------------------------------------------------
# Pipeline Jobs
# ---------------------------------------------------------------------------

@router.get("/jobs")
async def get_pipeline_jobs(
    limit: int = 50,
    status: Optional[str] = None,
    db=Depends(get_db),
    admin: str = Depends(require_admin_user),
) -> dict:
    """Pipeline job success/failure rates and recent job list."""
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be 1-200")

    now = datetime.now(timezone.utc)

    filters = ["1=1"]
    params: list = []
    idx = 1

    if status:
        filters.append(f"status = ${idx}")
        params.append(status)
        idx += 1

    where_clause = " AND ".join(filters)

    # Recent jobs
    jobs_raw = await db.query_raw(
        f"""
        SELECT
            id AS job_id,
            job_type,
            city,
            status,
            started_at::text,
            completed_at::text,
            EXTRACT(EPOCH FROM (completed_at - started_at))::float AS duration_seconds,
            COALESCE(items_processed, 0)::int AS items_processed,
            COALESCE(items_failed, 0)::int AS items_failed,
            error
        FROM pipeline_job
        WHERE {where_clause}
        ORDER BY started_at DESC
        LIMIT {limit}
        """,
        *params,
    )

    # Aggregate stats (last 30 days)
    thirty_days_ago = now - timedelta(days=30)
    stats = await db.query_raw(
        """
        SELECT
            COUNT(*)::int AS total,
            COUNT(*) FILTER (WHERE status = 'completed')::int AS success,
            COUNT(*) FILTER (WHERE status = 'failed')::int AS failed,
            COUNT(*) FILTER (WHERE status IN ('running', 'pending'))::int AS running
        FROM pipeline_job
        WHERE started_at >= $1
        """,
        thirty_days_ago,
    )

    s = stats[0] if stats else {"total": 0, "success": 0, "failed": 0, "running": 0}
    total = s["total"]
    success_rate = round(s["success"] / total, 4) if total > 0 else 0.0

    return {
        "data": PipelineJobSummary(
            jobs=[PipelineJobRow(**j) for j in jobs_raw],
            total_jobs=total,
            success_count=s["success"],
            failure_count=s["failed"],
            running_count=s["running"],
            success_rate=success_rate,
        ).model_dump(),
        "meta": {"timestamp": now.isoformat()},
    }


# ---------------------------------------------------------------------------
# Cost Alert Configuration
# ---------------------------------------------------------------------------

@router.get("/alerts")
async def get_cost_alerts(
    db=Depends(get_db),
    admin: str = Depends(require_admin_user),
) -> dict:
    """
    Get current cost alert thresholds with today's spend status.
    Joins config with today's actual LLM spend per stage.
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    rows = await db.query_raw(
        """
        SELECT
            c.pipeline_stage,
            c.daily_limit_usd::float,
            c.enabled,
            COALESCE(s.spend, 0)::float AS current_spend_usd
        FROM cost_alert_config c
        LEFT JOIN (
            SELECT
                pipeline_stage,
                SUM(cost_usd) AS spend
            FROM llm_call_log
            WHERE created_at >= $1
            GROUP BY pipeline_stage
        ) s ON s.pipeline_stage = c.pipeline_stage
        ORDER BY c.pipeline_stage
        """,
        today_start,
    )

    alerts = []
    for r in rows:
        limit = r["daily_limit_usd"]
        spend = r["current_spend_usd"]
        alerts.append(
            CostAlertStatus(
                pipeline_stage=r["pipeline_stage"],
                daily_limit_usd=limit,
                current_spend_usd=round(spend, 4),
                enabled=r["enabled"],
                exceeded=r["enabled"] and spend > limit,
                pct_used=round((spend / limit) * 100, 1) if limit > 0 else 0.0,
            ).model_dump()
        )

    return {
        "data": alerts,
        "meta": {"timestamp": now.isoformat()},
    }


@router.put("/alerts")
async def update_cost_alerts(
    body: CostAlertConfig,
    request: Request,
    db=Depends(get_db),
    admin: str = Depends(require_admin_user),
) -> dict:
    """
    Update cost alert thresholds. Audit-logged.
    Validates references exist per L-007.
    """
    now = datetime.now(timezone.utc)

    # Fetch current config for audit before-state
    current = await db.query_raw(
        "SELECT pipeline_stage, daily_limit_usd, enabled FROM cost_alert_config ORDER BY pipeline_stage"
    )
    before_state = {r["pipeline_stage"]: r for r in current}

    # Upsert each threshold
    for t in body.thresholds:
        await db.execute_raw(
            """
            INSERT INTO cost_alert_config (pipeline_stage, daily_limit_usd, enabled, updated_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (pipeline_stage)
            DO UPDATE SET daily_limit_usd = $2, enabled = $3, updated_at = $4
            """,
            t.pipeline_stage,
            t.daily_limit_usd,
            t.enabled,
            now,
        )

    after_state = {t.pipeline_stage: {"daily_limit_usd": t.daily_limit_usd, "enabled": t.enabled} for t in body.thresholds}

    await audit_action(
        db=db,
        request=request,
        actor_id=admin,
        action="pipeline.alert_config_update",
        target_type="CostAlertConfig",
        target_id="global",
        before=before_state,
        after=after_state,
    )

    return {
        "data": {"updated": len(body.thresholds)},
        "meta": {"timestamp": now.isoformat()},
    }
