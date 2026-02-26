"""
Admin City Seeding API — Trigger and monitor city seed jobs.

Endpoints:
  POST /admin/seeding/estimate  — cost estimate for a city
  POST /admin/seeding/trigger   — start seed job (rate-limited: 2/min)
  GET  /admin/seeding/progress  — per-city progress dashboard

Rate limit enforced via Redis sliding window (2 triggers/min global for admin).
All actions audit-logged.
"""

import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/admin/seeding", tags=["admin-seeding"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class SeedEstimateRequest(BaseModel):
    city: str = Field(..., min_length=1, max_length=200)
    country_code: str = Field(..., min_length=2, max_length=3)


class SeedEstimateResponse(BaseModel):
    city: str
    country_code: str
    estimated_api_calls: int
    estimated_cost_usd: float
    estimated_duration_minutes: int
    sources: list[str]


class SeedTriggerRequest(BaseModel):
    city: str = Field(..., min_length=1, max_length=200)
    country_code: str = Field(..., min_length=2, max_length=3)
    confirmed: bool = Field(
        ..., description="Must be true — confirms admin reviewed the cost estimate"
    )


class SeedTriggerResponse(BaseModel):
    job_id: str
    city: str
    status: str
    started_at: str


class CityProgress(BaseModel):
    city: str
    country_code: str
    job_id: str
    status: str  # pending | scraping | resolving | tagging | indexing | completed | failed
    scraped: int = 0
    resolved: int = 0
    tagged: int = 0
    indexed: int = 0
    total_expected: int = 0
    error: Optional[str] = None
    started_at: str
    updated_at: str


class ProgressResponse(BaseModel):
    jobs: list[CityProgress]


# ---------------------------------------------------------------------------
# Rate limiting (Redis sliding window — 2 triggers per 60s)
# ---------------------------------------------------------------------------

RATE_LIMIT_KEY = "admin:seeding:trigger_timestamps"
RATE_LIMIT_MAX = 2
RATE_LIMIT_WINDOW_S = 60


async def _check_rate_limit(redis) -> None:
    """Enforce 2-trigger-per-minute sliding window via Redis sorted set."""
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW_S

    pipe = redis.pipeline()
    # Remove entries older than window
    pipe.zremrangebyscore(RATE_LIMIT_KEY, "-inf", cutoff)
    # Count remaining entries
    pipe.zcard(RATE_LIMIT_KEY)
    results = await pipe.execute()

    current_count = results[1]
    if current_count >= RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded: max {RATE_LIMIT_MAX} seed triggers "
                f"per {RATE_LIMIT_WINDOW_S}s. Try again shortly."
            ),
        )

    # Record this trigger
    await redis.zadd(RATE_LIMIT_KEY, {str(now): now})
    await redis.expire(RATE_LIMIT_KEY, RATE_LIMIT_WINDOW_S + 10)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Rough per-source cost model (API calls × avg cost per call)
_SOURCE_COSTS = {
    "google_places": {"calls_per_city": 80, "cost_per_call": 0.017},
    "reddit": {"calls_per_city": 40, "cost_per_call": 0.0},
    "tabelog": {"calls_per_city": 60, "cost_per_call": 0.0},
}


def _estimate_city(city: str, country_code: str) -> SeedEstimateResponse:
    """Build a cost estimate for seeding a single city."""
    # Tabelog only applies to JP cities
    sources = {k: v for k, v in _SOURCE_COSTS.items()}
    if country_code.upper() != "JP":
        sources.pop("tabelog", None)

    total_calls = sum(s["calls_per_city"] for s in sources.values())
    total_cost = sum(
        s["calls_per_city"] * s["cost_per_call"] for s in sources.values()
    )
    # ~3 min per 100 API calls (conservative)
    duration = max(1, int(total_calls / 100 * 3))

    return SeedEstimateResponse(
        city=city,
        country_code=country_code.upper(),
        estimated_api_calls=total_calls,
        estimated_cost_usd=round(total_cost, 2),
        estimated_duration_minutes=duration,
        sources=list(sources.keys()),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/estimate", response_model=SeedEstimateResponse)
async def estimate_seed(body: SeedEstimateRequest):
    """Return cost estimate for seeding a city. No side effects."""
    return _estimate_city(body.city, body.country_code)


@router.post("/trigger", response_model=SeedTriggerResponse)
async def trigger_seed(
    body: SeedTriggerRequest,
    request: Request,
):
    """
    Trigger a city seed job.

    Requires `confirmed: true` to proceed (admin must have reviewed estimate).
    Rate-limited to 2 triggers per minute across all admins.
    """
    if not body.confirmed:
        raise HTTPException(
            status_code=400,
            detail="confirmed must be true — review the cost estimate first",
        )

    # Rate limit check
    redis = request.app.state.redis
    await _check_rate_limit(redis)

    now_iso = datetime.now(timezone.utc).isoformat()

    # Create job record in Redis (acts as lightweight job queue)
    import uuid
    job_id = f"seed-{uuid.uuid4().hex[:12]}"

    job_data = {
        "job_id": job_id,
        "city": body.city,
        "country_code": body.country_code.upper(),
        "status": "pending",
        "scraped": 0,
        "resolved": 0,
        "tagged": 0,
        "indexed": 0,
        "total_expected": 0,
        "error": "",
        "started_at": now_iso,
        "updated_at": now_iso,
    }
    job_key = f"admin:seeding:job:{job_id}"
    await redis.hset(job_key, mapping=job_data)
    # Keep job data for 24h
    await redis.expire(job_key, 86400)

    # Add to active jobs set
    await redis.sadd("admin:seeding:active_jobs", job_id)

    # Audit log
    from services.api.middleware.audit import audit_action

    actor_id = getattr(request.state, "admin_user_id", "unknown")
    await audit_action(
        db=request.app.state.db,
        request=request,
        actor_id=actor_id,
        action="seeding.trigger",
        target_type="CitySeed",
        target_id=job_id,
        after={"city": body.city, "country_code": body.country_code.upper()},
    )

    # NOTE: Actual pipeline dispatch happens via Track 2 orchestrator.
    # This endpoint creates the job record; the orchestrator polls for
    # pending jobs and updates progress.

    return SeedTriggerResponse(
        job_id=job_id,
        city=body.city,
        status="pending",
        started_at=now_iso,
    )


# ---------------------------------------------------------------------------
# Persona seeding
# ---------------------------------------------------------------------------

class PersonaSeedRequest(BaseModel):
    cities: list[str] = Field(
        default=["Tokyo"],
        description="Cities to generate trips for (must have ActivityNodes)",
    )
    personas_per_archetype: int = Field(
        default=3, ge=1, le=20,
        description="Number of fake users per archetype (6 archetypes total)",
    )


class PersonaSeedResponse(BaseModel):
    users_created: int
    trips_created: int
    slots_created: int
    signals_created: int
    errors: list[str]


@router.post("/personas", response_model=PersonaSeedResponse)
async def seed_personas(body: PersonaSeedRequest, request: Request):
    """
    Seed fake personas with behavioral signal histories for shadow model training.

    Creates users with archetype-driven trip patterns and realistic
    confirm/skip/love/dislike signals suitable for BPR training.
    """
    from services.api.pipeline.persona_seeder import run_persona_seed

    db_pool = request.app.state.db
    result = await run_persona_seed(
        db_pool,
        cities=body.cities,
        personas_per_archetype=body.personas_per_archetype,
    )
    return PersonaSeedResponse(
        users_created=result.users_created,
        trips_created=result.trips_created,
        slots_created=result.slots_created,
        signals_created=result.signals_created,
        errors=result.errors,
    )


class TrainingDataSeedResponse(BaseModel):
    model_registry_seeded: int
    signals_backfilled: int
    persona_dimensions_created: int
    ranking_events_created: int
    errors: list[str]


@router.post("/training-data", response_model=TrainingDataSeedResponse)
async def seed_training_data(request: Request):
    """
    Seed training data: ModelRegistry, PersonaDimension, RankingEvent.

    Fixes the 3 BPR training blockers. Idempotent — safe to re-run.
    """
    from services.api.pipeline.training_data_seeder import seed_training_data as run_seed

    db_pool = request.app.state.db
    result = await run_seed(db_pool)
    return TrainingDataSeedResponse(
        model_registry_seeded=result.model_registry_seeded,
        signals_backfilled=result.signals_backfilled,
        persona_dimensions_created=result.persona_dimensions_created,
        ranking_events_created=result.ranking_events_created,
        errors=result.errors,
    )


class EnrichmentResponse(BaseModel):
    pivot_events_created: int
    intention_signals_created: int
    discovery_signals_created: int
    weather_signals_updated: int
    trips_made_abandoned: int
    trips_made_recent: int
    errors: list[str]


@router.post("/enrich", response_model=EnrichmentResponse)
async def enrich_training_data(request: Request):
    """
    Run training data enrichments: PivotEvents, IntentionSignals,
    Discovery swipes, WeatherContext, Trip realism.

    Operates on existing shadow users. Idempotent — safe to re-run.
    """
    from services.api.pipeline.training_data_seeder import enrich_training_data as run_enrich

    db_pool = request.app.state.db
    result = await run_enrich(db_pool)
    return EnrichmentResponse(
        pivot_events_created=result.pivot_events_created,
        intention_signals_created=result.intention_signals_created,
        discovery_signals_created=result.discovery_signals_created,
        weather_signals_updated=result.weather_signals_updated,
        trips_made_abandoned=result.trips_made_abandoned,
        trips_made_recent=result.trips_made_recent,
        errors=result.errors,
    )


@router.get("/progress", response_model=ProgressResponse)
async def get_progress(request: Request):
    """Return progress for all active and recent seed jobs."""
    redis = request.app.state.redis

    job_ids = await redis.smembers("admin:seeding:active_jobs")

    jobs: list[CityProgress] = []
    stale_ids: list[str] = []

    for job_id_bytes in job_ids:
        job_id = (
            job_id_bytes.decode()
            if isinstance(job_id_bytes, bytes)
            else str(job_id_bytes)
        )
        job_key = f"admin:seeding:job:{job_id}"
        data = await redis.hgetall(job_key)

        if not data:
            stale_ids.append(job_id)
            continue

        # Decode bytes if needed
        d = {
            (k.decode() if isinstance(k, bytes) else k): (
                v.decode() if isinstance(v, bytes) else v
            )
            for k, v in data.items()
        }

        jobs.append(
            CityProgress(
                city=d.get("city", ""),
                country_code=d.get("country_code", ""),
                job_id=d.get("job_id", job_id),
                status=d.get("status", "unknown"),
                scraped=int(d.get("scraped", 0)),
                resolved=int(d.get("resolved", 0)),
                tagged=int(d.get("tagged", 0)),
                indexed=int(d.get("indexed", 0)),
                total_expected=int(d.get("total_expected", 0)),
                error=d.get("error") or None,
                started_at=d.get("started_at", ""),
                updated_at=d.get("updated_at", ""),
            )
        )

    # Clean up stale refs
    if stale_ids:
        await redis.srem("admin:seeding:active_jobs", *stale_ids)

    # Sort: active first, then by started_at descending
    status_order = {
        "scraping": 0, "resolving": 1, "tagging": 2, "indexing": 3,
        "pending": 4, "failed": 5, "completed": 6,
    }
    jobs.sort(key=lambda j: (status_order.get(j.status, 99), j.started_at), reverse=False)

    return ProgressResponse(jobs=jobs)
