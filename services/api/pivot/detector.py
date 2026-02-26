"""
PivotDetector — orchestrates all pivot triggers and writes PivotEvent records.

Flow per slot evaluation:
  1. Fetch current weather for trip city (shared across all slots in one run)
  2. Run each trigger against the slot
  3. On first firing trigger:
     a. Check MAX_PIVOT_DEPTH=1 (no cascading pivots)
     b. Query ActivitySearchService for ranked alternatives (same city, different node)
     c. Insert PivotEvent(status=proposed) into Postgres
     d. Return PivotEvent dict to caller
  4. Log all trigger evaluations as BehavioralSignals

MAX_PIVOT_DEPTH enforcement:
  A slot is skipped if ItinerarySlot.wasSwapped is True.
  This guarantees no cascading: a pivot replacement slot is never itself pivoted.

Database writes:
  PivotDetector owns all DB interaction for the pivot subsystem.
  Trigger classes are kept pure (no DB).

Alternative ranking strategy:
  Uses ActivitySearchService.search() with a natural-language query derived
  from the original slot's category + vibe tags. Top MAX_ALTERNATIVES results
  are stored as PivotEvent.alternativeIds (ordered by score).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from services.api.pivot.triggers import (
    WeatherTrigger,
    VenueClosureTrigger,
    TimeOverrunTrigger,
    UserMoodTrigger,
    TriggerResult,
)
from services.api.weather.service import WeatherService

logger = logging.getLogger(__name__)

# Hard cap on pivot alternatives returned per event
MAX_ALTERNATIVES = 5

# Prevents cascading pivots — slots that were already swapped in cannot be re-pivoted
MAX_PIVOT_DEPTH = 1


def _build_alternative_query(slot: dict[str, Any]) -> str:
    """
    Build a search query for finding pivot alternatives.

    Tries to incorporate the slot's original activity category and any
    vibe tags for a semantically meaningful Qdrant search.
    """
    category = slot.get("category") or slot.get("slotType", "activity")
    vibe_tags: list[str] = []

    activity_node = slot.get("activityNode") or {}
    raw_tags = activity_node.get("vibeTags") or []
    for tag in raw_tags:
        if isinstance(tag, dict):
            name = tag.get("name") or tag.get("slug", "")
        else:
            name = str(tag)
        if name:
            vibe_tags.append(name)

    if vibe_tags:
        return f"{category} activity with vibes: {', '.join(vibe_tags[:5])}"

    return f"indoor {category} activity"  # fallback: lean indoor to avoid re-triggering weather


class PivotDetector:
    """
    Orchestrator for pivot trigger detection and PivotEvent creation.

    Usage:
        detector = PivotDetector(db=db_pool, search_service=search, weather_service=weather)
        events = await detector.evaluate_trip(trip, slots)

    One PivotDetector instance is created per request/background job and
    shares a single weather fetch across all slots in the trip (cache handles
    the rest).
    """

    def __init__(
        self,
        db,
        search_service,
        weather_service: WeatherService,
    ) -> None:
        """
        Args:
            db:             Async database pool (asyncpg-compatible).
            search_service: ActivitySearchService instance.
            weather_service: WeatherService instance (with Redis cache).
        """
        self._db = db
        self._search = search_service
        self._weather = weather_service

        # Instantiate triggers — injected with their dependencies
        self._weather_trigger = WeatherTrigger(weather_service)
        self._closure_trigger = VenueClosureTrigger()
        self._overrun_trigger = TimeOverrunTrigger()
        self._mood_trigger = UserMoodTrigger()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def evaluate_trip(
        self,
        trip: dict[str, Any],
        slots: list[dict[str, Any]],
        user_mood_slot_id: str | None = None,
        user_id: str = "",
    ) -> list[dict[str, Any]]:
        """
        Evaluate all active slots in a trip for pivot conditions.

        Args:
            trip:               Trip record dict (id, city, timezone, ...).
            slots:              List of ItinerarySlot dicts (with activityNode nested).
            user_mood_slot_id:  If set, the UserMoodTrigger fires for this slot only.
            user_id:            Required when user_mood_slot_id is set.

        Returns:
            List of created PivotEvent dicts (may be empty if no triggers fired).
        """
        # Fetch weather once for the whole trip — WeatherCache returns in-memory
        # for the same hour; no repeated OpenWeatherMap calls.
        city = trip.get("city", "")
        weather_summary = await self._weather.get_weather(city) if city else None

        now_utc = datetime.now(timezone.utc)
        pivot_events: list[dict[str, Any]] = []

        for slot in slots:
            event = await self._evaluate_slot(
                slot=slot,
                trip=trip,
                weather_summary=weather_summary,
                now_utc=now_utc,
                user_mood_slot_id=user_mood_slot_id,
                user_id=user_id,
            )
            if event is not None:
                pivot_events.append(event)

        logger.info(
            "PivotDetector: trip=%s evaluated %d slots, %d pivot events created",
            trip.get("id"),
            len(slots),
            len(pivot_events),
        )
        return pivot_events

    async def evaluate_slot(
        self,
        slot: dict[str, Any],
        trip: dict[str, Any],
        user_mood: bool = False,
        user_id: str = "",
    ) -> dict[str, Any] | None:
        """
        Evaluate a single slot for pivot conditions.

        Convenience method for API endpoints that evaluate one slot at a time
        (e.g. user taps "not feeling it" on a specific slot).

        Returns a PivotEvent dict or None.
        """
        city = trip.get("city", "")
        weather_summary = await self._weather.get_weather(city) if city else None
        now_utc = datetime.now(timezone.utc)
        user_mood_slot_id = slot.get("id") if user_mood else None

        return await self._evaluate_slot(
            slot=slot,
            trip=trip,
            weather_summary=weather_summary,
            now_utc=now_utc,
            user_mood_slot_id=user_mood_slot_id,
            user_id=user_id,
        )

    # -------------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------------

    async def _evaluate_slot(
        self,
        slot: dict[str, Any],
        trip: dict[str, Any],
        weather_summary: dict[str, Any] | None,
        now_utc: datetime,
        user_mood_slot_id: str | None,
        user_id: str,
    ) -> dict[str, Any] | None:
        """
        Run all triggers against one slot. Creates a PivotEvent on first match.

        MAX_PIVOT_DEPTH enforcement:
          Slots with wasSwapped=True are skipped entirely — they were already
          a pivot replacement and cannot be re-pivoted.
        """
        slot_id = slot.get("id", "")
        slot_was_swapped = slot.get("wasSwapped", False)

        # Enforce MAX_PIVOT_DEPTH = 1
        if slot_was_swapped:
            logger.debug(
                "Slot %s skipped (wasSwapped=True, MAX_PIVOT_DEPTH=%d)", slot_id, MAX_PIVOT_DEPTH
            )
            return None

        # Skip already-terminal slots
        slot_status = slot.get("status", "")
        if slot_status in {"completed", "skipped", "archived"}:
            return None

        # Run triggers in priority order — first one that fires wins
        result = await self._run_triggers(
            slot=slot,
            trip=trip,
            weather_summary=weather_summary,
            now_utc=now_utc,
            user_mood_slot_id=user_mood_slot_id,
            user_id=user_id,
        )

        if result is None or not result.triggered:
            return None

        # Trigger fired — fetch alternatives and create PivotEvent
        return await self._create_pivot_event(slot, trip, result)

    async def _run_triggers(
        self,
        slot: dict[str, Any],
        trip: dict[str, Any],
        weather_summary: dict[str, Any] | None,
        now_utc: datetime,
        user_mood_slot_id: str | None,
        user_id: str,
    ) -> TriggerResult | None:
        """
        Run triggers in priority order. Returns the first firing TriggerResult, or None.

        Priority:
          1. UserMoodTrigger  (explicit user action — highest priority)
          2. WeatherTrigger   (environmental — immediate safety/comfort concern)
          3. VenueClosureTrigger (operational — venue unavailable)
          4. TimeOverrunTrigger  (time management — schedule drift)
        """
        slot_id = slot.get("id", "")

        # 1. User mood — explicit, only for the flagged slot
        if user_mood_slot_id and slot_id == user_mood_slot_id:
            result = await self._mood_trigger.evaluate(
                slot=slot,
                trip=trip,
                user_id=user_id,
                mood_signal="not_feeling_it",
            )
            if result.triggered:
                logger.info("UserMoodTrigger fired for slot=%s", slot_id)
                return result

        # 2. Weather
        result = await self._weather_trigger.evaluate(
            slot=slot,
            trip=trip,
            weather_summary=weather_summary,
        )
        if result.triggered:
            logger.info("WeatherTrigger fired for slot=%s: %s", slot_id, result.reason)
            return result

        # 3. Venue closure
        result = await self._closure_trigger.evaluate(
            slot=slot,
            trip=trip,
            now_utc=now_utc,
        )
        if result.triggered:
            logger.info("VenueClosureTrigger fired for slot=%s: %s", slot_id, result.reason)
            return result

        # 4. Time overrun
        result = await self._overrun_trigger.evaluate(
            slot=slot,
            trip=trip,
            now_utc=now_utc,
        )
        if result.triggered:
            logger.info("TimeOverrunTrigger fired for slot=%s: %s", slot_id, result.reason)
            return result

        return None

    async def _fetch_alternatives(
        self,
        slot: dict[str, Any],
        trip: dict[str, Any],
    ) -> list[str]:
        """
        Query ActivitySearchService for ranked alternative ActivityNode IDs.

        Excludes the current slot's activityNodeId from results.

        Returns:
            List of ActivityNode ID strings (up to MAX_ALTERNATIVES), ordered by score.
        """
        original_node_id = slot.get("activityNodeId")
        city = trip.get("city", "")
        query = _build_alternative_query(slot)

        # Fetch one extra in case we need to exclude the original
        fetch_limit = MAX_ALTERNATIVES + 1

        try:
            search_result = await self._search.search(
                query=query,
                city=city,
                filters=None,
                limit=fetch_limit,
            )
        except Exception:
            logger.exception(
                "ActivitySearchService failed while fetching pivot alternatives for slot=%s",
                slot.get("id"),
            )
            return []

        results = search_result.get("results", [])

        alternative_ids: list[str] = []
        for node in results:
            node_id = node.get("id")
            if not node_id:
                continue
            if node_id == original_node_id:
                continue  # Exclude the current activity
            alternative_ids.append(node_id)
            if len(alternative_ids) >= MAX_ALTERNATIVES:
                break

        if search_result.get("warning"):
            logger.warning(
                "Search warning while fetching alternatives for slot=%s: %s",
                slot.get("id"),
                search_result["warning"],
            )

        return alternative_ids

    async def _create_pivot_event(
        self,
        slot: dict[str, Any],
        trip: dict[str, Any],
        trigger_result: TriggerResult,
    ) -> dict[str, Any]:
        """
        Fetch alternatives and write a PivotEvent row to the database.

        PivotEvent fields:
          id              — new UUID
          tripId          — from trip
          slotId          — from slot
          triggerType     — from TriggerResult.trigger_type
          triggerPayload  — from TriggerResult.payload
          originalNodeId  — slot.activityNodeId
          alternativeIds  — ordered list from ActivitySearchService
          selectedNodeId  — NULL (user hasn't chosen yet)
          status          — 'proposed'
          createdAt       — now

        Returns the PivotEvent dict (not a DB row object — callers get a plain dict).
        """
        alternative_ids = await self._fetch_alternatives(slot, trip)

        pivot_event_id = str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc)

        original_node_id = slot.get("activityNodeId") or ""
        trip_id = trip.get("id", "")
        slot_id = slot.get("id", "")

        pivot_event: dict[str, Any] = {
            "id": pivot_event_id,
            "tripId": trip_id,
            "slotId": slot_id,
            "triggerType": trigger_result.trigger_type,
            "triggerPayload": trigger_result.payload,
            "originalNodeId": original_node_id,
            "alternativeIds": alternative_ids,
            "selectedNodeId": None,
            "status": "proposed",
            "resolvedAt": None,
            "responseTimeMs": None,
            "createdAt": now_utc.isoformat(),
        }

        # Write to database
        await self._persist_pivot_event(pivot_event)

        logger.info(
            "PivotEvent created: id=%s trigger=%s slot=%s alternatives=%d",
            pivot_event_id,
            trigger_result.trigger_type,
            slot_id,
            len(alternative_ids),
        )

        return pivot_event

    async def _persist_pivot_event(self, pivot_event: dict[str, Any]) -> None:
        """
        Insert a PivotEvent row into Postgres.

        Uses asyncpg-style parameter binding via $N placeholders.
        Does NOT raise — failures are logged and swallowed so the
        in-memory pivot_event dict is still returned to the caller.
        """
        import json as _json

        if self._db is None:
            logger.warning("No DB pool — PivotEvent %s not persisted", pivot_event["id"])
            return

        sql = """
            INSERT INTO pivot_events (
                id, "tripId", "slotId", "triggerType", "triggerPayload",
                "originalNodeId", "alternativeIds", "selectedNodeId",
                status, "resolvedAt", "responseTimeMs", "createdAt"
            ) VALUES (
                $1, $2, $3, $4, $5::jsonb,
                $6, $7, $8,
                $9, $10, $11, $12
            )
            ON CONFLICT (id) DO NOTHING
        """
        try:
            await self._db.execute(
                sql,
                pivot_event["id"],
                pivot_event["tripId"],
                pivot_event["slotId"],
                pivot_event["triggerType"],
                _json.dumps(pivot_event["triggerPayload"]),
                pivot_event["originalNodeId"],
                pivot_event["alternativeIds"],          # asyncpg handles str[] natively
                pivot_event["selectedNodeId"],
                pivot_event["status"],
                pivot_event["resolvedAt"],
                pivot_event["responseTimeMs"],
                datetime.fromisoformat(pivot_event["createdAt"]),
            )
        except Exception:
            logger.exception("Failed to persist PivotEvent %s to DB", pivot_event["id"])
