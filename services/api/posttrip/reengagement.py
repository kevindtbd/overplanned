"""
Post-trip re-engagement orchestrator.

Coordinates the full re-engagement pipeline after trip completion:
1. Next destination suggestion via Qdrant persona vector search
2. 24-hour push notification (FCM) -- "Your trip memories are ready"
3. 7-day email via Resend -- trip memory + "Where next?"

Entry points:
- on_trip_completed(): Called when a trip transitions to completed status
- process_pending_pushes(): Cron job for deferred push delivery
- process_pending_emails(): Cron job for 7-day email delivery

Security invariants:
- No session tokens in push notification deep links
- Email deep links use one-time-use login tokens (15-min expiry)
- Rate limit: max 1 re-engagement email per user per 7 days
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.db.models import BehavioralSignal, Trip
from services.api.embedding.service import embedding_service
from services.api.posttrip.email_service import (
    check_email_rate_limit,
    check_unsubscribed,
    send_trip_memory_email,
)
from services.api.posttrip.push_service import (
    enqueue_trip_completion_push,
    process_push_queue,
)
from services.api.search.qdrant_client import QdrantSearchClient

logger = logging.getLogger(__name__)

# Scheduling delays
PUSH_DELAY_HOURS = 24
EMAIL_DELAY_DAYS = 7

# Redis keys for email scheduling
EMAIL_QUEUE_KEY = "posttrip:email:queue"

# Qdrant search for next destination
DESTINATION_SEARCH_LIMIT = 5
DESTINATION_SCORE_THRESHOLD = 0.4


async def suggest_next_destination(
    session: AsyncSession,
    qdrant: QdrantSearchClient,
    *,
    user_id: str,
    completed_trip_id: str,
) -> dict[str, Any] | None:
    """
    Suggest the next travel destination based on accumulated behavioral signals.

    Builds a persona vector from the user's behavioral signals across all trips,
    then searches Qdrant for high-affinity activity clusters in cities they
    haven't visited yet.
    """
    # Step 1: Get user's positive behavioral signals for persona embedding
    stmt = (
        select(BehavioralSignal)
        .where(
            and_(
                BehavioralSignal.userId == user_id,
                BehavioralSignal.signalType.in_([
                    "slot_confirm",
                    "slot_complete",
                    "post_loved",
                    "discover_swipe_right",
                    "discover_shortlist",
                    "pivot_accepted",
                    "soft_positive",
                ]),
                BehavioralSignal.signalValue >= 0.5,
            )
        )
        .order_by(BehavioralSignal.createdAt.desc())
        .limit(100)
    )
    result = await session.execute(stmt)
    positive_signals = result.scalars().all()

    if len(positive_signals) < 3:
        logger.info(
            "Insufficient signals (%d) for user=%s destination suggestion",
            len(positive_signals), user_id,
        )
        return None

    # Step 2: Get activity names for embedding (from the signals' associated activities)
    activity_ids = [
        s.activityNodeId for s in positive_signals
        if s.activityNodeId is not None
    ]
    if not activity_ids:
        return None

    # Deduplicate
    unique_ids = list(dict.fromkeys(activity_ids))[:30]

    # ActivityNode is not in SA models scope -- use raw SQL
    activities_result = await session.execute(
        text("""
        SELECT id, name, category, city
        FROM activity_nodes
        WHERE id = ANY(:ids)
        """),
        {"ids": unique_ids},
    )
    activities = activities_result.mappings().all()

    if not activities:
        return None

    # Step 3: Build persona query from loved activities
    activity_descriptions = []
    visited_cities: set[str] = set()
    for a in activities:
        activity_descriptions.append(f"{a['name']} ({a['category']})")
        visited_cities.add(a["city"].lower())

    # Also get the completed trip's city to exclude
    trip_stmt = select(Trip).where(Trip.id == completed_trip_id)
    trip_result = await session.execute(trip_stmt)
    completed_trip = trip_result.scalars().first()
    if completed_trip and completed_trip.city:
        visited_cities.add(completed_trip.city.lower())

    persona_query = "traveler who enjoys: " + ", ".join(activity_descriptions[:15])

    # Step 4: Embed persona query
    persona_vector = embedding_service.embed_single(persona_query, is_query=True)

    # Step 5: Search Qdrant for matching activities in OTHER cities
    try:
        from qdrant_client.models import (
            Filter,
            FieldCondition,
            MatchValue,
            SearchParams,
        )

        must_conditions = [
            FieldCondition(key="is_canonical", match=MatchValue(value=True)),
        ]
        must_not_conditions = [
            FieldCondition(key="city", match=MatchValue(value=city))
            for city in visited_cities
        ]

        qdrant_filter = Filter(
            must=must_conditions,
            must_not=must_not_conditions if must_not_conditions else None,
        )

        client = await qdrant._get_client()
        results = await client.search(
            collection_name="activity_nodes",
            query_vector=persona_vector,
            query_filter=qdrant_filter,
            limit=DESTINATION_SEARCH_LIMIT * 3,
            score_threshold=DESTINATION_SCORE_THRESHOLD,
            search_params=SearchParams(hnsw_ef=128, exact=False),
        )
    except Exception:
        logger.exception("Qdrant search failed for destination suggestion")
        return None

    if not results:
        return None

    # Step 6: Group by city, pick the city with highest aggregate score
    city_scores: dict[str, dict[str, Any]] = {}
    for hit in results:
        payload = hit.payload or {}
        city = payload.get("city", "").lower()
        if not city:
            continue

        if city not in city_scores:
            city_scores[city] = {
                "city": payload.get("city", city),
                "country": payload.get("country", ""),
                "total_score": 0.0,
                "count": 0,
                "top_activities": [],
            }

        entry = city_scores[city]
        entry["total_score"] += hit.score
        entry["count"] += 1
        if len(entry["top_activities"]) < 3:
            entry["top_activities"].append({
                "name": payload.get("name", ""),
                "category": payload.get("category", ""),
                "score": hit.score,
            })

    if not city_scores:
        return None

    best_city = max(
        city_scores.values(),
        key=lambda c: (c["total_score"] / c["count"]) * min(c["count"], 5),
    )

    categories = [a["category"] for a in best_city["top_activities"]]
    unique_categories = list(dict.fromkeys(categories))[:3]
    reason = f"Based on your love for {', '.join(unique_categories)}"

    return {
        "city": best_city["city"],
        "country": best_city["country"],
        "reason": reason,
        "top_activities": best_city["top_activities"],
        "confidence": best_city["total_score"] / best_city["count"],
    }


async def on_trip_completed(
    session: AsyncSession,
    redis_client,
    qdrant: QdrantSearchClient,
    *,
    trip_id: str,
    user_id: str,
) -> dict[str, Any]:
    """
    Main entry point: called when a trip transitions to 'completed' status.

    Orchestrates:
    1. Enqueue 24-hour push notification
    2. Schedule 7-day email
    3. Pre-compute next destination suggestion (cached for email)
    """
    import json

    result: dict[str, Any] = {
        "trip_id": trip_id,
        "user_id": user_id,
        "push_enqueued": False,
        "email_scheduled": False,
        "destination_suggestion": None,
    }

    # Fetch trip details
    trip_stmt = select(Trip).where(Trip.id == trip_id)
    trip_result = await session.execute(trip_stmt)
    trip = trip_result.scalars().first()
    if not trip:
        logger.error("Trip %s not found for re-engagement", trip_id)
        return result

    # Fetch user details via raw SQL (User model not in SA scope)
    user_result = await session.execute(
        text('SELECT id, email, name FROM users WHERE id = :user_id'),
        {"user_id": user_id},
    )
    user = user_result.mappings().first()
    if not user:
        logger.error("User %s not found for re-engagement", user_id)
        return result

    now = datetime.now(timezone.utc)

    # 1. Enqueue 24-hour push notification
    push_scheduled_for = now + timedelta(hours=PUSH_DELAY_HOURS)
    result["push_enqueued"] = await enqueue_trip_completion_push(
        redis_client,
        user_id=user_id,
        trip_id=trip_id,
        trip_destination=trip.destination or "",
        scheduled_for=push_scheduled_for,
    )

    # 2. Pre-compute destination suggestion (used in both push context and email)
    try:
        suggestion = await suggest_next_destination(
            session, qdrant,
            user_id=user_id,
            completed_trip_id=trip_id,
        )
        result["destination_suggestion"] = suggestion

        # Cache suggestion for 7-day email
        if suggestion:
            cache_key = f"posttrip:suggestion:{user_id}:{trip_id}"
            await redis_client.setex(
                cache_key,
                60 * 60 * 24 * 8,  # 8 days TTL (outlasts email delay)
                json.dumps(suggestion),
            )
    except Exception:
        logger.exception("Failed to compute destination suggestion for trip=%s", trip_id)

    # 3. Schedule 7-day email
    email_scheduled_for = now + timedelta(days=EMAIL_DELAY_DAYS)
    email_payload = json.dumps({
        "type": "trip_memory_7d",
        "user_id": user_id,
        "trip_id": trip_id,
        "user_email": user["email"],
        "user_name": user["name"],
        "destination": trip.destination or "",
        "city": trip.city or "",
        "country": trip.country or "",
        "start_date": trip.startDate.isoformat() if trip.startDate else "",
        "end_date": trip.endDate.isoformat() if trip.endDate else "",
        "scheduled_for": email_scheduled_for.isoformat(),
    })

    await redis_client.zadd(
        EMAIL_QUEUE_KEY,
        {email_payload: email_scheduled_for.timestamp()},
    )
    result["email_scheduled"] = True

    logger.info(
        "Re-engagement scheduled for trip=%s: push=%s email=%s suggestion=%s",
        trip_id,
        result["push_enqueued"],
        result["email_scheduled"],
        result["destination_suggestion"] is not None,
    )

    return result


async def process_pending_emails(
    redis_client,
    session: AsyncSession,
    *,
    batch_size: int = 20,
) -> dict[str, int]:
    """
    Cron job: process due 7-day re-engagement emails.

    Pulls items from the email queue where scheduled_for <= now.
    """
    import json

    now = datetime.now(timezone.utc).timestamp()
    stats = {"sent": 0, "failed": 0, "skipped": 0, "rate_limited": 0}

    items = await redis_client.zrangebyscore(
        EMAIL_QUEUE_KEY, "-inf", now, start=0, num=batch_size,
    )

    if not items:
        return stats

    for raw_payload in items:
        payload = json.loads(raw_payload)
        user_id = payload["user_id"]
        trip_id = payload["trip_id"]

        # Remove from queue immediately
        await redis_client.zrem(EMAIL_QUEUE_KEY, raw_payload)

        # Check unsubscribe
        if await check_unsubscribed(session, user_id):
            stats["skipped"] += 1
            continue

        # Check rate limit
        if not await check_email_rate_limit(redis_client, user_id):
            stats["rate_limited"] += 1
            continue

        # Fetch trip highlights (top completed/loved slots)
        highlights = await _get_trip_highlights(session, trip_id)

        # Retrieve cached destination suggestion
        cache_key = f"posttrip:suggestion:{user_id}:{trip_id}"
        raw_suggestion = await redis_client.get(cache_key)
        next_destination = json.loads(raw_suggestion) if raw_suggestion else None

        # Format date range
        start_date = payload.get("start_date", "")
        end_date = payload.get("end_date", "")
        trip_dates = _format_date_range(start_date, end_date)

        # Send email
        success = await send_trip_memory_email(
            redis_client,
            session,
            user_id=user_id,
            trip_id=trip_id,
            user_email=payload["user_email"],
            user_name=payload.get("user_name"),
            trip_destination=payload["destination"],
            trip_dates=trip_dates,
            highlights=highlights,
            next_destination=next_destination,
        )

        if success:
            stats["sent"] += 1
        else:
            stats["failed"] += 1

    logger.info("Email queue processed: %s", stats)
    return stats


async def process_pending_pushes(
    redis_client,
    session: AsyncSession,
    *,
    batch_size: int = 50,
) -> dict[str, int]:
    """
    Cron job: process due 24-hour push notifications.

    Thin wrapper around push_service.process_push_queue for the cron entry point.
    """
    return await process_push_queue(redis_client, session, batch_size=batch_size)


async def _get_trip_highlights(
    session: AsyncSession,
    trip_id: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Get top highlights from a completed trip for the memory email.

    Prioritizes: completed slots with post_loved signals > completed slots > confirmed slots.
    Uses raw SQL since ActivityNode is not in SA models scope.
    """
    # Get completed/confirmed slots with their activity nodes
    slots_result = await session.execute(
        text("""
        SELECT
            s.id, s."dayNumber", s."activityNodeId",
            a.id AS "nodeId", a.name, a.category, a."primaryImageUrl"
        FROM itinerary_slots s
        LEFT JOIN activity_nodes a ON s."activityNodeId" = a.id
        WHERE s."tripId" = :trip_id
          AND s.status IN ('completed', 'confirmed')
          AND s."activityNodeId" IS NOT NULL
        ORDER BY s."dayNumber" ASC
        LIMIT :limit_count
        """),
        {"trip_id": trip_id, "limit_count": limit * 2},
    )
    slot_rows = slots_result.mappings().all()

    if not slot_rows:
        return []

    # Get loved signals for these activity nodes
    activity_node_ids = [
        r["activityNodeId"] for r in slot_rows
        if r["activityNodeId"] is not None
    ]

    loved_ids: set[str] = set()
    if activity_node_ids:
        loved_result = await session.execute(
            select(BehavioralSignal.activityNodeId).where(
                and_(
                    BehavioralSignal.activityNodeId.in_(activity_node_ids),
                    BehavioralSignal.signalType == "post_loved",
                )
            )
        )
        loved_ids = {row[0] for row in loved_result.all() if row[0]}

    # Build highlights, prioritizing loved activities
    highlights: list[dict[str, Any]] = []
    for row_data in slot_rows:
        if row_data["nodeId"] is None:
            continue
        highlights.append({
            "name": row_data["name"],
            "category": row_data["category"],
            "image_url": row_data["primaryImageUrl"] or "",
            "is_loved": row_data["nodeId"] in loved_ids,
            "day": row_data["dayNumber"],
        })

    # Sort: loved first, then by day
    highlights.sort(key=lambda h: (not h["is_loved"], h["day"]))

    return highlights[:limit]


def _format_date_range(start_iso: str, end_iso: str) -> str:
    """Format ISO date strings into a human-readable range."""
    try:
        start = datetime.fromisoformat(start_iso)
        end = datetime.fromisoformat(end_iso)

        if start.month == end.month and start.year == end.year:
            return f"{start.strftime('%b %d')}-{end.strftime('%d, %Y')}"
        elif start.year == end.year:
            return f"{start.strftime('%b %d')} - {end.strftime('%b %d, %Y')}"
        else:
            return f"{start.strftime('%b %d, %Y')} - {end.strftime('%b %d, %Y')}"
    except (ValueError, TypeError):
        return ""
