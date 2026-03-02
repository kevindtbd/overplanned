"""
Admin Seed Viz API — Pipeline visualization endpoints.

Endpoints:
  GET /admin/seed-viz/overview  — aggregated city progress from JSON files + DB
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.routers._admin_deps import get_db, require_admin_user

router = APIRouter(prefix="/admin/seed-viz", tags=["admin-seed-viz"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STEP_ORDER = [
    "reddit_download",
    "scrape",
    "llm_fallback",
    "geocode_backfill",
    "business_status",
    "entity_resolution",
    "vibe_extraction",
    "rule_inference",
    "convergence",
    "qdrant_sync",
]

# Path to seed_progress JSON files, relative to repo root
_REPO_ROOT = Path(__file__).parent.parent.parent.parent
SEED_PROGRESS_DIR = _REPO_ROOT / "data" / "seed_progress"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_dt(val: Optional[str]) -> Optional[datetime]:
    """Parse ISO datetime string to datetime object, return None on failure."""
    if not val:
        return None
    try:
        return datetime.fromisoformat(val)
    except (ValueError, TypeError):
        return None


def _step_duration(step: dict) -> Optional[float]:
    """Compute step duration in seconds from started_at/finished_at."""
    started = _parse_dt(step.get("started_at"))
    finished = _parse_dt(step.get("finished_at"))
    if started and finished:
        return (finished - started).total_seconds()
    return None


def _extract_llm_cost(steps: dict) -> float:
    """Sum estimated_cost_usd across all step metrics."""
    total = 0.0
    for step_data in steps.values():
        metrics = step_data.get("metrics") or {}
        cost = metrics.get("estimated_cost_usd")
        if isinstance(cost, (int, float)):
            total += float(cost)
    return total


def _city_duration(data: dict) -> Optional[float]:
    """Total wall-clock duration from first started_at to finished_at."""
    started = _parse_dt(data.get("started_at"))
    finished = _parse_dt(data.get("finished_at"))
    if started and finished:
        return (finished - started).total_seconds()
    return None


def _read_seed_files() -> list[dict]:
    """Read all seed_progress/*.json files. Returns list of parsed dicts."""
    results = []
    if not SEED_PROGRESS_DIR.exists():
        return results
    for fpath in sorted(SEED_PROGRESS_DIR.glob("*.json")):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            results.append(data)
        except Exception:
            pass
    return results


async def _query_category_counts(session: AsyncSession) -> dict[str, list[dict]]:
    """
    Single query: city -> [{name, count, pct}, ...]
    activity_nodes.city stores display names like "Asheville", "Bend".
    We lower() both sides to join with seed file city names (lowercase).
    """
    sql = text(
        "SELECT LOWER(city) AS city_lower, category, COUNT(*) AS cnt "
        "FROM activity_nodes "
        "WHERE city IS NOT NULL AND category IS NOT NULL "
        "GROUP BY city_lower, category "
        "ORDER BY city_lower, cnt DESC"
    )
    result = await session.execute(sql)
    rows = result.fetchall()

    # Group by city
    by_city: dict[str, dict[str, int]] = {}
    for row in rows:
        city_lower = row[0]
        category = row[1]
        cnt = int(row[2])
        if city_lower not in by_city:
            by_city[city_lower] = {}
        by_city[city_lower][category] = cnt

    # Convert to list with pct
    output: dict[str, list[dict]] = {}
    for city_lower, cats in by_city.items():
        total = sum(cats.values())
        output[city_lower] = [
            {
                "name": cat,
                "count": cnt,
                "pct": round(cnt / total * 100, 1) if total > 0 else 0.0,
            }
            for cat, cnt in sorted(cats.items(), key=lambda x: -x[1])
        ]
    return output


async def _build_overview(session: Optional[AsyncSession]) -> dict[str, Any]:
    """Core logic: read seed files + DB, return overview payload."""
    seed_files = _read_seed_files()

    # Fetch category counts from DB (graceful degradation if unavailable)
    cat_by_city: dict[str, list[dict]] = {}
    if session is not None:
        try:
            cat_by_city = await _query_category_counts(session)
        except Exception:
            pass

    cities = []
    total_nodes = 0
    total_cost = 0.0
    status_counts = {"completed": 0, "in_progress": 0, "failed": 0, "pending": 0}

    for data in seed_files:
        city_slug = (data.get("city") or "").lower().strip()
        overall_status = data.get("overall_status", "pending")

        # Clamp unknown statuses to pending
        if overall_status not in status_counts:
            overall_status = "pending"

        status_counts[overall_status] = status_counts.get(overall_status, 0) + 1

        steps_raw = data.get("steps") or {}
        # Build per-step summary in canonical order
        steps_out: dict[str, dict] = {}
        for step_name in STEP_ORDER:
            step_data = steps_raw.get(step_name) or {}
            dur = _step_duration(step_data)
            steps_out[step_name] = {
                "status": step_data.get("status", "pending"),
                "duration_s": round(dur) if dur is not None else None,
                "error": step_data.get("error"),
            }

        # Node counts from JSON
        nodes_scraped = data.get("nodes_scraped") or 0
        nodes_resolved = data.get("nodes_resolved") or 0
        nodes_tagged = data.get("nodes_tagged") or 0
        nodes_indexed = data.get("nodes_indexed") or 0

        # Category data from DB (keyed by lowercase slug)
        categories = cat_by_city.get(city_slug, [])
        nodes_in_db = sum(c["count"] for c in categories) if categories else 0

        # LLM cost from step metrics
        llm_cost = _extract_llm_cost(steps_raw)
        total_cost += llm_cost

        # Duration
        dur_s = _city_duration(data)

        # Top category
        top_cat = categories[0]["name"] if categories else None
        top_cat_pct = categories[0]["pct"] if categories else 0.0

        total_nodes += nodes_in_db

        cities.append(
            {
                "city": city_slug,
                "overall_status": overall_status,
                "nodes_scraped": nodes_scraped,
                "nodes_resolved": nodes_resolved,
                "nodes_tagged": nodes_tagged,
                "nodes_indexed": nodes_indexed,
                "nodes_in_db": nodes_in_db,
                "category_count": len(categories),
                "top_category": top_cat,
                "top_category_pct": top_cat_pct,
                "duration_seconds": round(dur_s, 1) if dur_s is not None else None,
                "llm_cost_usd": round(llm_cost, 4),
                "steps": steps_out,
                "categories": categories,
            }
        )

    # Sort: in_progress first, then completed, then failed, then pending
    STATUS_SORT = {"in_progress": 0, "completed": 1, "failed": 2, "pending": 3}
    cities.sort(key=lambda c: (STATUS_SORT.get(c["overall_status"], 9), c["city"]))

    return {
        "cities": cities,
        "totals": {
            "cities_total": len(cities),
            "completed": status_counts["completed"],
            "in_progress": status_counts["in_progress"],
            "failed": status_counts.get("failed", 0),
            "pending": status_counts.get("pending", 0),
            "total_nodes": total_nodes,
            "total_cost_usd": round(total_cost, 4),
        },
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/overview")
async def seed_viz_overview(
    _actor: str = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """
    Aggregated city pipeline progress.
    Reads data/seed_progress/*.json + queries activity_nodes for category distribution.
    """
    return await _build_overview(session)
