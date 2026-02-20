"""
FCM push notification service for post-trip re-engagement.

24-hour post-completion push: "Your trip memories are ready"
Uses Redis queue for async delivery with deduplication.

Security:
- No session tokens in push notification deep links
- Deep links use trip ID only (requires auth on open)
- PushToken stored per-device, revocable
"""

import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any

import httpx
from prisma import Prisma

from services.api.config import settings

logger = logging.getLogger(__name__)

# Redis key prefixes
PUSH_QUEUE_KEY = "posttrip:push:queue"
PUSH_SENT_KEY = "posttrip:push:sent:{user_id}:{trip_id}"
PUSH_SENT_TTL_S = 60 * 60 * 24 * 30  # 30 days dedup window

# FCM v1 API endpoint
FCM_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"


async def register_push_token(
    db: Prisma,
    *,
    user_id: str,
    device_token: str,
    platform: str,
    device_id: str,
) -> dict[str, Any]:
    """
    Register or update a push notification token for a user device.

    Args:
        db: Prisma client
        user_id: User registering the token
        device_token: FCM device token
        platform: 'ios' | 'android' | 'web'
        device_id: Unique device identifier for upsert

    Returns:
        Created/updated push token record
    """
    if platform not in ("ios", "android", "web"):
        raise ValueError(f"Invalid platform '{platform}'. Must be ios, android, or web.")

    # Upsert by user + device_id to handle token refresh
    # Using raw SQL since Prisma Python doesn't support upsert on composite keys easily
    existing = await db.query_raw(
        """
        SELECT id FROM "PushToken"
        WHERE "userId" = $1 AND "deviceId" = $2
        """,
        user_id,
        device_id,
    )

    if existing:
        token_record = await db.query_raw(
            """
            UPDATE "PushToken"
            SET "deviceToken" = $1, "platform" = $2, "updatedAt" = NOW(), "isActive" = true
            WHERE "userId" = $3 AND "deviceId" = $4
            RETURNING id, "userId", "deviceId", "platform", "isActive", "createdAt", "updatedAt"
            """,
            device_token,
            platform,
            user_id,
            device_id,
        )
    else:
        token_record = await db.query_raw(
            """
            INSERT INTO "PushToken" (id, "userId", "deviceToken", "deviceId", "platform", "isActive", "createdAt", "updatedAt")
            VALUES ($1, $2, $3, $4, $5, true, NOW(), NOW())
            RETURNING id, "userId", "deviceId", "platform", "isActive", "createdAt", "updatedAt"
            """,
            secrets.token_urlsafe(16),
            user_id,
            device_token,
            device_id,
            platform,
        )

    return token_record[0] if token_record else {}


async def revoke_push_token(
    db: Prisma,
    *,
    user_id: str,
    device_id: str,
) -> bool:
    """Deactivate a push token (logout, uninstall)."""
    result = await db.query_raw(
        """
        UPDATE "PushToken"
        SET "isActive" = false, "updatedAt" = NOW()
        WHERE "userId" = $1 AND "deviceId" = $2 AND "isActive" = true
        RETURNING id
        """,
        user_id,
        device_id,
    )
    return len(result) > 0


async def get_active_tokens(db: Prisma, user_id: str) -> list[dict[str, Any]]:
    """Get all active push tokens for a user."""
    tokens = await db.query_raw(
        """
        SELECT id, "deviceToken", "platform", "deviceId"
        FROM "PushToken"
        WHERE "userId" = $1 AND "isActive" = true
        """,
        user_id,
    )
    return tokens


async def enqueue_trip_completion_push(
    redis_client,
    *,
    user_id: str,
    trip_id: str,
    trip_destination: str,
    scheduled_for: datetime,
) -> bool:
    """
    Enqueue a 24-hour post-completion push notification.

    Checks dedup key to avoid double-sends.
    Deep link uses trip ID only — NO session tokens.

    Args:
        redis_client: Async Redis client
        user_id: Target user
        trip_id: Completed trip
        trip_destination: City name for notification text
        scheduled_for: When to send (completion + 24h)

    Returns:
        True if enqueued, False if already sent
    """
    dedup_key = PUSH_SENT_KEY.format(user_id=user_id, trip_id=trip_id)

    # Check dedup
    if await redis_client.exists(dedup_key):
        logger.info(
            "Push already sent for user=%s trip=%s, skipping",
            user_id, trip_id,
        )
        return False

    payload = json.dumps({
        "type": "trip_completion_24h",
        "user_id": user_id,
        "trip_id": trip_id,
        "destination": trip_destination,
        "scheduled_for": scheduled_for.isoformat(),
        "enqueued_at": datetime.now(timezone.utc).isoformat(),
    })

    # ZADD with scheduled_for timestamp as score for delayed processing
    score = scheduled_for.timestamp()
    await redis_client.zadd(PUSH_QUEUE_KEY, {payload: score})

    logger.info(
        "Enqueued push for user=%s trip=%s at %s",
        user_id, trip_id, scheduled_for.isoformat(),
    )
    return True


async def process_push_queue(
    redis_client,
    db: Prisma,
    *,
    batch_size: int = 50,
) -> dict[str, int]:
    """
    Process due push notifications from the Redis sorted set queue.

    Pulls items with score <= now (scheduled_for has passed).

    Returns:
        Stats dict with sent/failed/skipped counts
    """
    now = datetime.now(timezone.utc).timestamp()
    stats = {"sent": 0, "failed": 0, "skipped": 0}

    # Get due items
    items = await redis_client.zrangebyscore(
        PUSH_QUEUE_KEY, "-inf", now, start=0, num=batch_size,
    )

    if not items:
        return stats

    for raw_payload in items:
        payload = json.loads(raw_payload)
        user_id = payload["user_id"]
        trip_id = payload["trip_id"]

        # Remove from queue immediately (at-most-once delivery)
        await redis_client.zrem(PUSH_QUEUE_KEY, raw_payload)

        # Check dedup again (race condition guard)
        dedup_key = PUSH_SENT_KEY.format(user_id=user_id, trip_id=trip_id)
        if await redis_client.exists(dedup_key):
            stats["skipped"] += 1
            continue

        # Get user's active push tokens
        tokens = await get_active_tokens(db, user_id)
        if not tokens:
            logger.info("No active push tokens for user=%s", user_id)
            stats["skipped"] += 1
            continue

        # Send to all active devices
        destination = payload["destination"]
        success = await _send_fcm_notification(
            tokens=tokens,
            title="Your trip memories are ready",
            body=f"Relive your time in {destination} and discover where to go next.",
            data={
                "type": "trip_memory",
                "trip_id": trip_id,
                # NO session token — app must authenticate on open
            },
        )

        if success:
            # Mark as sent (dedup)
            await redis_client.setex(dedup_key, PUSH_SENT_TTL_S, "1")
            stats["sent"] += 1
        else:
            stats["failed"] += 1

    logger.info("Push queue processed: %s", stats)
    return stats


async def _send_fcm_notification(
    tokens: list[dict[str, Any]],
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> bool:
    """
    Send FCM v1 push notification to all provided device tokens.

    Uses service account credentials from settings.
    Returns True if at least one device received the notification.
    """
    fcm_project_id = getattr(settings, "fcm_project_id", "")
    fcm_service_account_key = getattr(settings, "fcm_service_account_key", "")

    if not fcm_project_id or not fcm_service_account_key:
        logger.warning("FCM not configured, skipping push send")
        return False

    url = FCM_SEND_URL.format(project_id=fcm_project_id)
    any_success = False

    async with httpx.AsyncClient(timeout=10.0) as client:
        for token_record in tokens:
            device_token = token_record["deviceToken"]
            platform = token_record["platform"]

            message: dict[str, Any] = {
                "message": {
                    "token": device_token,
                    "notification": {
                        "title": title,
                        "body": body,
                    },
                }
            }

            if data:
                message["message"]["data"] = data

            # Platform-specific config
            if platform == "ios":
                message["message"]["apns"] = {
                    "payload": {
                        "aps": {"sound": "default", "badge": 1}
                    }
                }
            elif platform == "android":
                message["message"]["android"] = {
                    "priority": "normal",
                    "notification": {"sound": "default"},
                }

            try:
                resp = await client.post(
                    url,
                    json=message,
                    headers={
                        "Authorization": f"Bearer {fcm_service_account_key}",
                        "Content-Type": "application/json",
                    },
                )
                if resp.status_code == 200:
                    any_success = True
                else:
                    logger.warning(
                        "FCM send failed for device=%s status=%d body=%s",
                        token_record["deviceId"],
                        resp.status_code,
                        resp.text[:200],
                    )
            except httpx.HTTPError as exc:
                logger.error(
                    "FCM request error for device=%s: %s",
                    token_record["deviceId"],
                    str(exc),
                )

    return any_success
