"""
Off-Plan Signal Handler — V2 ML Pipeline Phase 1.4.

Handles the case where a user adds a place to their itinerary mid-trip that
was NOT in the pre-generated plan. Two outcomes:

Matched path (activityNodeId provided — entity resolution succeeded)
    Write a BehavioralSignal with:
        signalType   = "slot_confirm"
        signal_weight = 1.4   (strong positive — user sought this out)
        source       = "user_behavioral"
        subflow      = "onthefly_add"

Unmatched path (no activityNodeId — place not in our corpus)
    Write a CorpusIngestionRequest row with:
        source  = "off_plan_add"
        status  = "pending"
    The ingestion pipeline will scrape + embed the place and create an
    ActivityNode, at which point the signal can be backfilled.

Deduplication
    At most one ``user_added_off_plan`` signal per (user, venue, trip).
    The venue key is the activityNodeId for matched paths, or a normalized
    form of place_name for unmatched paths. Callers must pass the db_pool
    to enable the dedup check.

Security note
    signal_weight is server-side only and never returned to the client.
    The DB CHECK constraint enforces [-1.0, 3.0]; 1.4 is within range.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SIGNAL_TYPE_MATCHED: str = "slot_confirm"
_SIGNAL_WEIGHT_MATCHED: float = 1.4
_SIGNAL_SOURCE_MATCHED: str = "user_behavioral"
_SIGNAL_SUBFLOW: str = "onthefly_add"

_INGESTION_SOURCE: str = "off_plan_add"
_INGESTION_STATUS: str = "pending"

# Dedup uses the same signalType as the insert so the check actually finds matches
_DEDUP_SIGNAL_TYPE: str = "slot_confirm"


# ---------------------------------------------------------------------------
# SQL helpers (asyncpg-style $N placeholders)
# ---------------------------------------------------------------------------

_SQL_DEDUP_CHECK = """
    SELECT 1
    FROM behavioral_signals
    WHERE "userId" = $1
      AND "tripId" = $2
      AND "signalType" = $3
      AND (
            "activityNodeId" = $4
         OR ("activityNodeId" IS NULL AND "rawAction" = $5)
      )
    LIMIT 1
"""

_SQL_INSERT_SIGNAL = """
    INSERT INTO behavioral_signals (
        id, "userId", "tripId", "activityNodeId",
        "signalType", "signalValue", "tripPhase",
        "rawAction", "source", "subflow", "signal_weight",
        "createdAt"
    ) VALUES (
        $1, $2, $3, $4,
        $5, $6, $7,
        $8, $9, $10, $11,
        $12
    )
    RETURNING id, "userId", "tripId", "activityNodeId",
              "signalType", "signal_weight", "source", "subflow", "createdAt"
"""

_SQL_INSERT_INGESTION = """
    INSERT INTO corpus_ingestion_requests (
        id, "rawPlaceName", "tripId", "userId",
        source, status, "createdAt"
    ) VALUES (
        $1, $2, $3, $4,
        $5, $6, $7
    )
    RETURNING id, "rawPlaceName", source, status, "createdAt"
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def handle_off_plan_add(
    user_id: str,
    trip_id: str,
    place_name: str,
    activity_node_id: str | None,
    db_pool,
) -> dict:
    """
    Record a user-initiated off-plan activity add.

    Args:
        user_id:          ID of the user who added the activity.
        trip_id:          ID of the active trip.
        place_name:       Human-readable place name (used for unmatched path
                          and as the dedup key when activityNodeId is None).
        activity_node_id: ActivityNode ID from entity resolution, or None if
                          the place is not yet in the corpus.
        db_pool:          Async database pool (asyncpg-compatible). Must
                          support ``fetchrow`` and ``execute``.

    Returns:
        dict with one of:
          - Matched: ``{"type": "signal", "id": ..., "signalType": ...,
                        "subflow": ..., "source": ..., "createdAt": ...}``
          - Unmatched: ``{"type": "ingestion_request", "id": ...,
                          "rawPlaceName": ..., "source": ..., "status": ...,
                          "createdAt": ...}``
          - Deduplicated: ``{"type": "duplicate", "message": ...}``

    Raises:
        ValueError: If user_id, trip_id, or place_name are empty.
    """
    if not user_id:
        raise ValueError("user_id is required")
    if not trip_id:
        raise ValueError("trip_id is required")
    if not place_name or not place_name.strip():
        raise ValueError("place_name is required")

    normalized_place = place_name.strip().lower()
    now_utc = datetime.now(timezone.utc)

    # -------------------------------------------------------------------------
    # Deduplication check — max 1 per (user, venue, trip)
    # -------------------------------------------------------------------------
    raw_action_key = f"off_plan_add:{normalized_place}"
    existing = await db_pool.fetchrow(
        _SQL_DEDUP_CHECK,
        user_id,
        trip_id,
        _DEDUP_SIGNAL_TYPE,
        activity_node_id,   # matched: dedup by node id
        raw_action_key,     # unmatched: dedup by place name slug in rawAction
    )
    if existing:
        logger.info(
            "handle_off_plan_add: dedup — user=%s trip=%s place=%r already recorded",
            user_id,
            trip_id,
            place_name,
        )
        return {
            "type": "duplicate",
            "message": f"Off-plan add for '{place_name}' already recorded for this trip.",
        }

    # -------------------------------------------------------------------------
    # Matched path — entity resolution succeeded
    # -------------------------------------------------------------------------
    if activity_node_id:
        record = await db_pool.fetchrow(
            _SQL_INSERT_SIGNAL,
            str(uuid.uuid4()),        # $1  id
            user_id,                   # $2  userId
            trip_id,                   # $3  tripId
            activity_node_id,          # $4  activityNodeId
            _SIGNAL_TYPE_MATCHED,      # $5  signalType
            1.0,                       # $6  signalValue
            "active",                # $7  tripPhase
            raw_action_key,            # $8  rawAction  (also used as dedup key)
            _SIGNAL_SOURCE_MATCHED,    # $9  source
            _SIGNAL_SUBFLOW,           # $10 subflow
            _SIGNAL_WEIGHT_MATCHED,    # $11 signal_weight
            now_utc,                   # $12 createdAt
        )

        logger.info(
            "handle_off_plan_add: matched signal created id=%s user=%s trip=%s node=%s",
            record["id"],
            user_id,
            trip_id,
            activity_node_id,
        )

        return {
            "type": "signal",
            "id": record["id"],
            "userId": user_id,
            "tripId": trip_id,
            "activityNodeId": activity_node_id,
            "signalType": record["signalType"],
            "subflow": record["subflow"],
            "source": record["source"],
            "createdAt": record["createdAt"].isoformat(),
        }

    # -------------------------------------------------------------------------
    # Unmatched path — place not in corpus yet; queue for ingestion
    # -------------------------------------------------------------------------
    record = await db_pool.fetchrow(
        _SQL_INSERT_INGESTION,
        str(uuid.uuid4()),   # $1  id
        place_name.strip(),  # $2  placeName (preserve original casing)
        trip_id,             # $3  tripId
        user_id,             # $4  userId
        _INGESTION_SOURCE,   # $5  source
        _INGESTION_STATUS,   # $6  status
        now_utc,             # $7  createdAt
    )

    logger.info(
        "handle_off_plan_add: unmatched — queued ingestion id=%s place=%r user=%s trip=%s",
        record["id"],
        place_name,
        user_id,
        trip_id,
    )

    return {
        "type": "ingestion_request",
        "id": record["id"],
        "rawPlaceName": record["rawPlaceName"],
        "source": record["source"],
        "status": record["status"],
        "createdAt": record["createdAt"].isoformat(),
    }
