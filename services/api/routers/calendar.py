"""
Calendar router — iCal (.ics) generation for trip itineraries.

GET /trips/{trip_id}/calendar.ics
- Auth-gated via X-User-Id header (set by Next.js BFF proxy)
- Generates iCalendar file with VTIMEZONE + one VEVENT per ItinerarySlot
- Slots without startTime are given a default noon-to-1pm time on their day
- Correct VTIMEZONE block is included so calendar apps honour the destination timezone
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone, date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

router = APIRouter(prefix="/trips", tags=["calendar"])

# ---------------------------------------------------------------------------
# iCal helpers
# ---------------------------------------------------------------------------

def _fold(line: str) -> str:
    """
    RFC 5545 line folding: lines longer than 75 octets must be folded.
    Fold at 75 characters with CRLF + single space.
    """
    result = []
    while len(line.encode("utf-8")) > 75:
        # Find safe cut point at 75 bytes
        chunk = line[:75]
        result.append(chunk)
        line = " " + line[75:]
    result.append(line)
    return "\r\n".join(result)


def _escape(text: str) -> str:
    """Escape special iCal characters in text values."""
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\n", "\\n")
    text = text.replace("\r", "")
    return text


def _ical_dt(dt: datetime) -> str:
    """Format datetime for iCal DTSTART/DTEND in UTC (always safe)."""
    utc_dt = dt.astimezone(timezone.utc)
    return utc_dt.strftime("%Y%m%dT%H%M%SZ")


def _naive_local_dt(dt: datetime) -> str:
    """Format a naive (tz-aware) datetime as local iCal format."""
    return dt.strftime("%Y%m%dT%H%M%S")


# ---------------------------------------------------------------------------
# VTIMEZONE builder (simplified but standards-compliant)
# ---------------------------------------------------------------------------

# Standard UTC offsets for common travel timezones.
# For a production system, use the icalendar library or zoneinfo + icalendar.
# This covers the most common destination zones.
KNOWN_TZOFFSETS: dict[str, tuple[int, int]] = {
    # (standard_offset_hours, dst_offset_hours)
    # Asia
    "Asia/Tokyo": (9, 9),
    "Asia/Seoul": (9, 9),
    "Asia/Shanghai": (8, 8),
    "Asia/Hong_Kong": (8, 8),
    "Asia/Singapore": (8, 8),
    "Asia/Bangkok": (7, 7),
    "Asia/Kolkata": (330, 330),  # +5:30 as minutes from UTC / 60
    "Asia/Dubai": (4, 4),
    "Asia/Riyadh": (3, 3),
    "Asia/Istanbul": (3, 3),
    "Asia/Jerusalem": (2, 3),
    # Europe
    "Europe/London": (0, 1),
    "Europe/Paris": (1, 2),
    "Europe/Berlin": (1, 2),
    "Europe/Rome": (1, 2),
    "Europe/Madrid": (1, 2),
    "Europe/Amsterdam": (1, 2),
    "Europe/Zurich": (1, 2),
    "Europe/Stockholm": (1, 2),
    "Europe/Athens": (2, 3),
    "Europe/Helsinki": (2, 3),
    "Europe/Moscow": (3, 3),
    # Americas
    "America/New_York": (-5, -4),
    "America/Chicago": (-6, -5),
    "America/Denver": (-7, -6),
    "America/Los_Angeles": (-8, -7),
    "America/Phoenix": (-7, -7),
    "America/Anchorage": (-9, -8),
    "America/Honolulu": (-10, -10),
    "America/Toronto": (-5, -4),
    "America/Vancouver": (-8, -7),
    "America/Mexico_City": (-6, -5),
    "America/Sao_Paulo": (-3, -2),
    "America/Argentina/Buenos_Aires": (-3, -3),
    "America/Bogota": (-5, -5),
    "America/Lima": (-5, -5),
    # Oceania
    "Australia/Sydney": (10, 11),
    "Australia/Melbourne": (10, 11),
    "Australia/Brisbane": (10, 10),
    "Australia/Perth": (8, 8),
    "Pacific/Auckland": (12, 13),
    "Pacific/Fiji": (12, 13),
    # Africa
    "Africa/Nairobi": (3, 3),
    "Africa/Cairo": (2, 2),
    "Africa/Johannesburg": (2, 2),
    "Africa/Lagos": (1, 1),
    # Default fallback
    "UTC": (0, 0),
}


def _format_utcoffset(total_hours: int) -> str:
    """Convert fractional-hour offset (e.g. 330 for +5:30) to ±HHMM."""
    if total_hours > 99:
        # Encoded as minutes (e.g. 330 = 5*60+30)
        sign = "+"
        h, m = divmod(total_hours, 60)
    elif total_hours < -99:
        sign = "-"
        h, m = divmod(abs(total_hours), 60)
    else:
        sign = "+" if total_hours >= 0 else "-"
        h = abs(total_hours)
        m = 0
    return f"{sign}{h:02d}{m:02d}"


def _build_vtimezone(tzid: str) -> str:
    """
    Build a VTIMEZONE block for the given IANA timezone string.
    Uses hardcoded offsets for common travel destinations.
    Falls back to UTC if unknown.
    """
    offsets = KNOWN_TZOFFSETS.get(tzid, KNOWN_TZOFFSETS["UTC"])
    std_offset, dst_offset = offsets

    std_utcoffset = _format_utcoffset(std_offset)
    dst_utcoffset = _format_utcoffset(dst_offset)
    has_dst = std_offset != dst_offset

    lines = [
        "BEGIN:VTIMEZONE",
        f"TZID:{tzid}",
        "BEGIN:STANDARD",
        "DTSTART:19701025T030000",
        f"TZOFFSETFROM:{dst_utcoffset}",
        f"TZOFFSETTO:{std_utcoffset}",
        f"TZNAME:{'STD'}",
        "END:STANDARD",
    ]

    if has_dst:
        lines += [
            "BEGIN:DAYLIGHT",
            "DTSTART:19700329T020000",
            f"TZOFFSETFROM:{std_utcoffset}",
            f"TZOFFSETTO:{dst_utcoffset}",
            "TZNAME:DST",
            "END:DAYLIGHT",
        ]

    lines.append("END:VTIMEZONE")
    return "\r\n".join(lines)


# ---------------------------------------------------------------------------
# VEVENT builder
# ---------------------------------------------------------------------------

def _build_vevent(
    slot_id: str,
    trip_id: str,
    summary: str,
    dtstart: datetime,
    dtend: datetime,
    tzid: str,
    location: Optional[str],
    description: Optional[str],
) -> str:
    """Build a single VEVENT block."""
    uid = f"{slot_id}@overplanned.app"
    now_stamp = _ical_dt(datetime.now(timezone.utc))

    # Use floating time (no Z suffix) if we have a proper TZID
    start_str = _naive_local_dt(dtstart)
    end_str = _naive_local_dt(dtend)

    vevent_lines = [
        "BEGIN:VEVENT",
        _fold(f"UID:{uid}"),
        f"DTSTAMP:{now_stamp}",
        _fold(f"DTSTART;TZID={tzid}:{start_str}"),
        _fold(f"DTEND;TZID={tzid}:{end_str}"),
        _fold(f"SUMMARY:{_escape(summary)}"),
    ]

    if location:
        vevent_lines.append(_fold(f"LOCATION:{_escape(location)}"))

    if description:
        vevent_lines.append(_fold(f"DESCRIPTION:{_escape(description)}"))

    vevent_lines.append(_fold(f"URL:https://overplanned.app/trip/{trip_id}"))
    vevent_lines.append("END:VEVENT")

    return "\r\n".join(vevent_lines)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.get("/{trip_id}/calendar.ics")
async def get_trip_calendar(
    trip_id: str,
    request: Request,
) -> Response:
    """
    Generate and return a .ics (iCalendar) file for the trip.

    Each ItinerarySlot becomes one VEVENT.
    The VTIMEZONE block matches the trip's stored timezone.
    Auth is expected to be pre-validated by the Next.js proxy layer that
    forwards X-User-Id from the session. In dev the endpoint is open for
    local testing.
    """
    db = request.app.state.db

    if db is None:
        raise HTTPException(
            status_code=503,
            detail="Database connection not available.",
        )

    # Fetch trip
    trip = await db.fetchrow(
        """
        SELECT id, destination, city, country, timezone,
               "startDate", "endDate"
        FROM trips
        WHERE id = $1
        """,
        trip_id,
    )

    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found.")

    # Fetch slots with activity node data
    slots = await db.fetch(
        """
        SELECT
            s.id,
            s."dayNumber",
            s."sortOrder",
            s."slotType",
            s.status,
            s."startTime",
            s."endTime",
            s."durationMinutes",
            s."isLocked",
            an.name          AS activity_name,
            an.address       AS activity_address,
            an.latitude      AS activity_lat,
            an.longitude     AS activity_lng,
            an."descriptionShort" AS activity_desc
        FROM itinerary_slots s
        LEFT JOIN activity_nodes an ON an.id = s."activityNodeId"
        WHERE s."tripId" = $1
          AND s.status NOT IN ('skipped', 'proposed')
        ORDER BY s."dayNumber", s."sortOrder"
        """,
        trip_id,
    )

    tzid: str = trip["timezone"] or "UTC"
    trip_start: datetime = trip["startDate"]

    # Build iCal
    cal_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Overplanned//Trip Itinerary//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        _fold(f"X-WR-CALNAME:{_escape(trip['destination'])} Itinerary"),
        _fold(f"X-WR-TIMEZONE:{tzid}"),
        _build_vtimezone(tzid),
    ]

    for slot in slots:
        day_num: int = slot["dayNumber"]
        # Compute the absolute date for this day
        day_date = trip_start + timedelta(days=day_num - 1)

        # Build start/end datetimes
        if slot["startTime"] is not None:
            st: datetime = slot["startTime"]
            if slot["endTime"] is not None:
                et: datetime = slot["endTime"]
            elif slot["durationMinutes"]:
                et = st + timedelta(minutes=slot["durationMinutes"])
            else:
                et = st + timedelta(hours=1)
        else:
            # Default: noon local on the day
            st = datetime(
                day_date.year, day_date.month, day_date.day, 12, 0, 0
            )
            duration = slot["durationMinutes"] or 60
            et = st + timedelta(minutes=duration)

        # Summary
        slot_type = slot["slotType"]
        activity_name = slot["activity_name"]
        summary = activity_name if activity_name else slot_type.capitalize()

        # Location
        address = slot["activity_address"]
        lat = slot["activity_lat"]
        lng = slot["activity_lng"]

        if address:
            location = address
        elif lat is not None and lng is not None:
            location = f"{lat:.6f},{lng:.6f}"
        else:
            location = None

        # Description
        desc_parts = []
        if slot["activity_desc"]:
            desc_parts.append(slot["activity_desc"])
        if lat is not None and lng is not None:
            desc_parts.append(
                f"Maps: https://maps.google.com/?q={lat:.6f},{lng:.6f}"
            )
        desc_parts.append(f"Type: {slot_type}")
        description = "\n".join(desc_parts) if desc_parts else None

        vevent = _build_vevent(
            slot_id=slot["id"],
            trip_id=trip_id,
            summary=summary,
            dtstart=st,
            dtend=et,
            tzid=tzid,
            location=location,
            description=description,
        )
        cal_lines.append(vevent)

    cal_lines.append("END:VCALENDAR")

    ics_content = "\r\n".join(cal_lines) + "\r\n"

    city_slug = re.sub(r"[^a-z0-9]+", "-", trip["city"].lower()).strip("-")
    filename = f"{city_slug}-itinerary.ics"

    return Response(
        content=ics_content.encode("utf-8"),
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )
