"""
Post-trip re-engagement email service via Resend.

7-day email: trip memory summary + "Where next?" destination suggestion.

Security & compliance:
- SPF/DKIM/DMARC: Resend handles via verified sending domain
- One-click unsubscribe via List-Unsubscribe header (RFC 8058)
- Rate limit: max 1 re-engagement email per user per 7 days
- One-time-use login links for deep links (15-min expiry, single use)
- No session tokens in email links
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.config import settings

logger = logging.getLogger(__name__)

# Rate limit: 1 re-engagement email per 7 days
EMAIL_RATE_LIMIT_DAYS = 7
EMAIL_RATE_LIMIT_KEY = "posttrip:email:sent:{user_id}"
EMAIL_RATE_LIMIT_TTL_S = 60 * 60 * 24 * 7  # 7 days

# Login link expiry
LOGIN_LINK_EXPIRY_MINUTES = 15
LOGIN_LINK_KEY = "posttrip:login:{token}"
LOGIN_LINK_TTL_S = 60 * 15  # 15 minutes

# Resend API
RESEND_API_URL = "https://api.resend.com/emails"
FROM_ADDRESS = "Overplanned <trips@overplanned.app>"


async def generate_login_link(
    redis_client,
    *,
    user_id: str,
    redirect_path: str,
) -> str:
    """
    Generate a one-time-use login link for email deep links.

    The token is:
    - Cryptographically random (32 bytes, URL-safe)
    - Single use (deleted from Redis on consumption)
    - 15-minute expiry
    - Maps to user_id + redirect_path
    """
    token = secrets.token_urlsafe(32)
    key = LOGIN_LINK_KEY.format(token=token)

    import json
    await redis_client.setex(
        key,
        LOGIN_LINK_TTL_S,
        json.dumps({
            "user_id": user_id,
            "redirect_path": redirect_path,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }),
    )

    base_url = getattr(settings, "app_base_url", "https://overplanned.app")
    return f"{base_url}/auth/magic?token={token}"


async def consume_login_link(
    redis_client,
    *,
    token: str,
) -> dict[str, str] | None:
    """
    Consume a one-time-use login link. Returns user info or None if invalid/expired.

    The token is deleted immediately (single use).
    """
    import json
    key = LOGIN_LINK_KEY.format(token=token)

    # GET + DEL atomically via pipeline
    pipe = redis_client.pipeline()
    pipe.get(key)
    pipe.delete(key)
    results = await pipe.execute()

    raw = results[0]
    if raw is None:
        return None

    return json.loads(raw)


async def check_email_rate_limit(
    redis_client,
    user_id: str,
) -> bool:
    """
    Check if we can send a re-engagement email to this user.

    Returns True if allowed, False if rate limited.
    """
    key = EMAIL_RATE_LIMIT_KEY.format(user_id=user_id)
    return not await redis_client.exists(key)


async def mark_email_sent(
    redis_client,
    user_id: str,
) -> None:
    """Mark that we sent a re-engagement email (starts 7-day cooldown)."""
    key = EMAIL_RATE_LIMIT_KEY.format(user_id=user_id)
    await redis_client.setex(key, EMAIL_RATE_LIMIT_TTL_S, "1")


async def check_unsubscribed(session: AsyncSession, user_id: str) -> bool:
    """Check if user has unsubscribed from re-engagement emails."""
    result = await session.execute(
        text("""
        SELECT 1 FROM email_preferences
        WHERE "userId" = :user_id AND "category" = 'reengagement' AND "unsubscribed" = true
        """),
        {"user_id": user_id},
    )
    return result.first() is not None


async def unsubscribe_user(session: AsyncSession, user_id: str) -> None:
    """Unsubscribe user from re-engagement emails."""
    await session.execute(
        text("""
        INSERT INTO email_preferences (id, "userId", "category", "unsubscribed", "updatedAt")
        VALUES (gen_random_uuid(), :user_id, 'reengagement', true, NOW())
        ON CONFLICT ("userId", "category")
        DO UPDATE SET "unsubscribed" = true, "updatedAt" = NOW()
        """),
        {"user_id": user_id},
    )
    await session.commit()


async def send_trip_memory_email(
    redis_client,
    session: AsyncSession,
    *,
    user_id: str,
    trip_id: str,
    user_email: str,
    user_name: str | None,
    trip_destination: str,
    trip_dates: str,
    highlights: list[dict[str, Any]],
    next_destination: dict[str, Any] | None = None,
) -> bool:
    """
    Send the 7-day post-trip memory + "Where next?" email via Resend.

    Args:
        redis_client: Async Redis client (rate limit + login links)
        session: SA async session (unsubscribe check)
        user_id: Target user
        trip_id: Completed trip
        user_email: User's email address
        user_name: User's display name (for personalization)
        trip_destination: City name
        trip_dates: Formatted date range string
        highlights: List of trip highlight dicts (name, category, image_url)
        next_destination: Optional suggested next destination dict

    Returns:
        True if email sent, False if skipped (rate limited, unsubscribed, error)
    """
    # Check unsubscribe
    if await check_unsubscribed(session, user_id):
        logger.info("User %s unsubscribed from reengagement emails", user_id)
        return False

    # Check rate limit
    if not await check_email_rate_limit(redis_client, user_id):
        logger.info("User %s rate limited for reengagement email", user_id)
        return False

    # Generate one-time login link for the trip memory page
    memory_path = f"/trip/{trip_id}/memory"
    login_url = await generate_login_link(
        redis_client,
        user_id=user_id,
        redirect_path=memory_path,
    )

    # Generate unsubscribe token (also one-time)
    unsubscribe_url = await generate_login_link(
        redis_client,
        user_id=user_id,
        redirect_path="/settings/email?action=unsubscribe&category=reengagement",
    )

    # Build email HTML
    greeting = f"Hi {user_name}," if user_name else "Hi there,"
    html = _build_trip_memory_html(
        greeting=greeting,
        destination=trip_destination,
        dates=trip_dates,
        highlights=highlights,
        next_destination=next_destination,
        memory_url=login_url,
        unsubscribe_url=unsubscribe_url,
    )

    subject = f"Your {trip_destination} memories are ready"

    # Send via Resend
    success = await _send_via_resend(
        to_email=user_email,
        subject=subject,
        html=html,
        unsubscribe_url=unsubscribe_url,
        tags=[
            {"name": "category", "value": "reengagement"},
            {"name": "trip_id", "value": trip_id},
        ],
    )

    if success:
        await mark_email_sent(redis_client, user_id)
        logger.info(
            "Sent trip memory email to user=%s trip=%s",
            user_id, trip_id,
        )

    return success


async def _send_via_resend(
    *,
    to_email: str,
    subject: str,
    html: str,
    unsubscribe_url: str,
    tags: list[dict[str, str]] | None = None,
) -> bool:
    """
    Send email via Resend API.

    Includes List-Unsubscribe header for one-click unsubscribe (RFC 8058).
    SPF/DKIM/DMARC are handled by Resend's verified domain configuration.
    """
    resend_api_key = getattr(settings, "resend_api_key", "")
    if not resend_api_key:
        logger.warning("Resend API key not configured, skipping email send")
        return False

    import httpx

    payload: dict[str, Any] = {
        "from": FROM_ADDRESS,
        "to": [to_email],
        "subject": subject,
        "html": html,
        "headers": {
            # RFC 8058: One-click unsubscribe
            "List-Unsubscribe": f"<{unsubscribe_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    }

    if tags:
        payload["tags"] = tags

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                RESEND_API_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {resend_api_key}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code in (200, 201):
                return True
            else:
                logger.error(
                    "Resend API error: status=%d body=%s",
                    resp.status_code,
                    resp.text[:300],
                )
                return False
    except httpx.HTTPError as exc:
        logger.error("Resend request failed: %s", str(exc))
        return False


def _build_trip_memory_html(
    *,
    greeting: str,
    destination: str,
    dates: str,
    highlights: list[dict[str, Any]],
    next_destination: dict[str, Any] | None,
    memory_url: str,
    unsubscribe_url: str,
) -> str:
    """
    Build the trip memory email HTML.

    Uses inline styles (email client compatibility).
    Design system: Sora headings, DM Mono data, Terracotta accent #C4694F.
    """
    # Build highlights section
    highlights_html = ""
    for h in highlights[:5]:  # Cap at 5 highlights
        name = _escape_html(h.get("name", ""))
        category = _escape_html(h.get("category", ""))
        image_url = h.get("image_url", "")
        img_tag = (
            f'<img src="{_escape_html(image_url)}" alt="{name}" '
            f'style="width:100%;height:120px;object-fit:cover;border-radius:8px;" />'
            if image_url else ""
        )
        highlights_html += f"""
        <div style="display:inline-block;width:140px;margin:8px;vertical-align:top;">
            {img_tag}
            <p style="font-family:'Sora',sans-serif;font-size:14px;margin:4px 0 0;color:#1a1a1a;">{name}</p>
            <p style="font-family:'DM Mono',monospace;font-size:11px;color:#666;margin:2px 0 0;">{category}</p>
        </div>"""

    # Build "Where next?" section
    next_section = ""
    if next_destination:
        next_city = _escape_html(next_destination.get("city", ""))
        next_country = _escape_html(next_destination.get("country", ""))
        next_reason = _escape_html(next_destination.get("reason", ""))
        next_section = f"""
        <div style="background:#FFF8F5;border-left:4px solid #C4694F;padding:16px;margin:24px 0;border-radius:0 8px 8px 0;">
            <p style="font-family:'Sora',sans-serif;font-size:16px;font-weight:600;color:#C4694F;margin:0 0 8px;">
                Where next?
            </p>
            <p style="font-family:'Sora',sans-serif;font-size:18px;font-weight:700;color:#1a1a1a;margin:0 0 4px;">
                {next_city}, {next_country}
            </p>
            <p style="font-family:'DM Mono',monospace;font-size:13px;color:#555;margin:0;">
                {next_reason}
            </p>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#FAF7F5;font-family:'Sora',Helvetica,Arial,sans-serif;">
<div style="max-width:600px;margin:0 auto;padding:32px 24px;">

    <div style="text-align:center;margin-bottom:24px;">
        <p style="font-family:'Sora',sans-serif;font-size:24px;font-weight:700;color:#1a1a1a;margin:0;">
            Overplanned
        </p>
    </div>

    <p style="font-size:16px;color:#1a1a1a;margin:0 0 16px;">{_escape_html(greeting)}</p>

    <p style="font-size:15px;color:#333;line-height:1.6;margin:0 0 8px;">
        Your time in <strong>{_escape_html(destination)}</strong> wrapped up
        <span style="font-family:'DM Mono',monospace;font-size:13px;color:#666;">({_escape_html(dates)})</span>.
    </p>
    <p style="font-size:15px;color:#333;line-height:1.6;margin:0 0 24px;">
        We put together your trip memories -- the spots you loved, the ones you discovered, and a few surprises.
    </p>

    <div style="text-align:center;margin:0 0 24px;">
        <a href="{_escape_html(memory_url)}"
           style="display:inline-block;background:#C4694F;color:#fff;font-family:'Sora',sans-serif;
                  font-size:15px;font-weight:600;padding:12px 32px;border-radius:8px;
                  text-decoration:none;">
            View your trip memories
        </a>
    </div>

    {highlights_html and f'<div style="margin:0 0 24px;text-align:center;">{highlights_html}</div>' or ''}

    {next_section}

    <hr style="border:none;border-top:1px solid #E8E0DB;margin:32px 0 16px;" />
    <p style="font-family:'DM Mono',monospace;font-size:11px;color:#999;text-align:center;margin:0 0 4px;">
        You received this because you completed a trip on Overplanned.
    </p>
    <p style="font-family:'DM Mono',monospace;font-size:11px;color:#999;text-align:center;margin:0;">
        <a href="{_escape_html(unsubscribe_url)}" style="color:#999;">Unsubscribe from trip emails</a>
    </p>

</div>
</body>
</html>"""


def _escape_html(text: str) -> str:
    """Minimal HTML escaping for email content."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
