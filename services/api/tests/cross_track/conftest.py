"""
Cross-track integration test fixtures.

Provides a fully seeded state covering ALL 7 SOC tracks:
  Track 1 (Foundation): User, Session, Account
  Track 2 (Pipeline):   ActivityNodes, VibeTags, QualitySignals
  Track 3 (Solo):       Solo trip, ItinerarySlots, BehavioralSignals during generation
  Track 4 (Admin):      ModelRegistry (referenced by signals)
  Track 5 (Group):      Group trip, TripMembers, InviteToken, SharedTripToken, voteState
  Track 6 (Mid-trip):   PivotEvent, pivot signals, RawEvents
  Track 7 (Post-trip):  Post-trip signals, IntentionSignals

All IDs are deterministic via uuid5 so fixtures are stable across runs.
No real database -- everything is dict-based for unit-level speed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.api.tests.conftest import (
    make_user,
    make_session,
    make_trip,
    make_activity_node,
    make_itinerary_slot,
    make_behavioral_signal,
    make_intention_signal,
    make_raw_event,
    make_quality_signal,
)


# ---------------------------------------------------------------------------
# Deterministic ID generation (uuid5 with a fixed namespace)
# ---------------------------------------------------------------------------

_NS = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def _did(label: str) -> str:
    """Deterministic UUID from a human-readable label."""
    return str(uuid.uuid5(_NS, label))


# Freeze a reference "now" so all fixtures share the same timeline.
_NOW = datetime(2026, 2, 15, 12, 0, 0, tzinfo=timezone.utc)


# ============================================================================
# Track 1 -- Foundation: User + Session
# ============================================================================

@pytest.fixture
def cross_user() -> dict:
    """Google OAuth beta user -- the protagonist of every cross-track test."""
    return make_user(
        id=_did("cross-user"),
        email="cross-track@example.com",
        name="Cross Track Tester",
        googleId="google-cross-track-001",
        subscriptionTier="beta",
        emailVerified=_NOW - timedelta(days=60),
        onboardingComplete=True,
        createdAt=_NOW - timedelta(days=60),
        updatedAt=_NOW,
        lastActiveAt=_NOW - timedelta(hours=1),
    )


@pytest.fixture
def cross_session(cross_user: dict) -> dict:
    """Active session for cross_user."""
    return make_session(
        user_id=cross_user["id"],
        id=_did("cross-session"),
        sessionToken="cross-sess-token-001",
        expires=_NOW + timedelta(days=30),
        createdAt=_NOW - timedelta(hours=2),
    )


@pytest.fixture
def cross_second_user() -> dict:
    """Second user for group trip membership."""
    return make_user(
        id=_did("cross-user-2"),
        email="cross-track-2@example.com",
        name="Second Traveler",
        googleId="google-cross-track-002",
        subscriptionTier="beta",
        emailVerified=_NOW - timedelta(days=30),
        onboardingComplete=True,
        createdAt=_NOW - timedelta(days=30),
        updatedAt=_NOW,
    )


# ============================================================================
# Track 2 -- Pipeline: ActivityNodes, VibeTags, QualitySignals
# ============================================================================

@pytest.fixture
def cross_vibe_tags() -> list[dict]:
    """Three canonical vibe tags used across activities."""
    return [
        {
            "id": _did("vibe-hidden-gem"),
            "slug": "hidden-gem",
            "name": "Hidden Gem",
            "category": "discovery",
            "isActive": True,
            "sortOrder": 0,
            "createdAt": _NOW - timedelta(days=90),
        },
        {
            "id": _did("vibe-local-favorite"),
            "slug": "local-favorite",
            "name": "Local Favorite",
            "category": "social-proof",
            "isActive": True,
            "sortOrder": 1,
            "createdAt": _NOW - timedelta(days=90),
        },
        {
            "id": _did("vibe-street-food"),
            "slug": "street-food",
            "name": "Street Food",
            "category": "dining-style",
            "isActive": True,
            "sortOrder": 2,
            "createdAt": _NOW - timedelta(days=90),
        },
    ]


@pytest.fixture
def cross_activity_nodes(cross_vibe_tags: list[dict]) -> list[dict]:
    """Three ActivityNodes: morning activity, lunch spot, afternoon activity."""
    return [
        make_activity_node(
            id=_did("node-morning"),
            name="Senso-ji Temple",
            slug="sensoji-temple",
            canonicalName="Senso-ji Temple",
            city="Tokyo",
            country="Japan",
            category="culture",
            convergenceScore=0.87,
            authorityScore=0.91,
            latitude=35.7148,
            longitude=139.7967,
            status="approved",
            sourceCount=5,
        ),
        make_activity_node(
            id=_did("node-lunch"),
            name="Tsukiji Outer Market",
            slug="tsukiji-outer-market",
            canonicalName="Tsukiji Outer Market",
            city="Tokyo",
            country="Japan",
            category="dining",
            convergenceScore=0.92,
            authorityScore=0.88,
            latitude=35.6654,
            longitude=139.7707,
            status="approved",
            sourceCount=8,
        ),
        make_activity_node(
            id=_did("node-afternoon"),
            name="TeamLab Borderless",
            slug="teamlab-borderless",
            canonicalName="TeamLab Borderless",
            city="Tokyo",
            country="Japan",
            category="experience",
            convergenceScore=0.78,
            authorityScore=0.82,
            latitude=35.6256,
            longitude=139.7839,
            status="approved",
            sourceCount=4,
        ),
    ]


@pytest.fixture
def cross_activity_node_vibe_tags(
    cross_activity_nodes: list[dict],
    cross_vibe_tags: list[dict],
) -> list[dict]:
    """Join records linking nodes to vibe tags."""
    links = []
    # Morning node -> hidden-gem, local-favorite
    for i, vt_idx in enumerate([0, 1]):
        links.append({
            "id": _did(f"anvt-morning-{i}"),
            "activityNodeId": cross_activity_nodes[0]["id"],
            "vibeTagId": cross_vibe_tags[vt_idx]["id"],
            "score": 0.85 - (i * 0.1),
            "source": "reddit",
            "createdAt": _NOW - timedelta(days=30),
        })
    # Lunch node -> street-food, local-favorite
    for i, vt_idx in enumerate([2, 1]):
        links.append({
            "id": _did(f"anvt-lunch-{i}"),
            "activityNodeId": cross_activity_nodes[1]["id"],
            "vibeTagId": cross_vibe_tags[vt_idx]["id"],
            "score": 0.90 - (i * 0.05),
            "source": "reddit",
            "createdAt": _NOW - timedelta(days=30),
        })
    # Afternoon node -> hidden-gem
    links.append({
        "id": _did("anvt-afternoon-0"),
        "activityNodeId": cross_activity_nodes[2]["id"],
        "vibeTagId": cross_vibe_tags[0]["id"],
        "score": 0.72,
        "source": "blog",
        "createdAt": _NOW - timedelta(days=30),
    })
    return links


@pytest.fixture
def cross_quality_signals(cross_activity_nodes: list[dict]) -> list[dict]:
    """QualitySignals for each activity node (pipeline-sourced)."""
    return [
        make_quality_signal(
            activity_node_id=cross_activity_nodes[0]["id"],
            id=_did("qs-morning"),
            sourceName="reddit",
            sourceUrl="https://reddit.com/r/JapanTravel/abc123",
            sourceAuthority=0.82,
            signalType="positive_mention",
            rawExcerpt="Senso-ji at sunrise is something else entirely",
            extractedAt=_NOW - timedelta(days=45),
        ),
        make_quality_signal(
            activity_node_id=cross_activity_nodes[1]["id"],
            id=_did("qs-lunch"),
            sourceName="reddit",
            sourceUrl="https://reddit.com/r/JapanTravel/def456",
            sourceAuthority=0.79,
            signalType="positive_mention",
            rawExcerpt="Tsukiji outer market is still legit for street food",
            extractedAt=_NOW - timedelta(days=40),
        ),
        make_quality_signal(
            activity_node_id=cross_activity_nodes[2]["id"],
            id=_did("qs-afternoon"),
            sourceName="blog",
            sourceUrl="https://tokyocheapo.com/teamlab",
            sourceAuthority=0.65,
            signalType="recommendation",
            rawExcerpt="TeamLab Borderless moved but the new space is worth it",
            extractedAt=_NOW - timedelta(days=35),
        ),
    ]


# ============================================================================
# Track 3 -- Solo: completed trip + slots + generation-time signals
# ============================================================================

@pytest.fixture
def cross_solo_trip(cross_user: dict) -> dict:
    """Completed solo trip to Tokyo with timezone and date range."""
    return make_trip(
        user_id=cross_user["id"],
        id=_did("solo-trip"),
        mode="solo",
        status="completed",
        destination="Tokyo, Japan",
        city="Tokyo",
        country="Japan",
        timezone="Asia/Tokyo",
        startDate=_NOW - timedelta(days=8),
        endDate=_NOW - timedelta(days=1),
        activatedAt=_NOW - timedelta(days=8),
        completedAt=_NOW - timedelta(hours=6),
        personaSeed={
            "vibes": ["hidden-gem", "local-favorite", "street-food"],
            "pace": "moderate",
            "budget": "mid",
        },
    )


@pytest.fixture
def cross_solo_slots(
    cross_solo_trip: dict,
    cross_activity_nodes: list[dict],
) -> list[dict]:
    """Three day-1 slots: morning activity, lunch meal, afternoon activity."""
    trip_id = cross_solo_trip["id"]
    base_date = cross_solo_trip["startDate"]
    return [
        make_itinerary_slot(
            trip_id=trip_id,
            id=_did("slot-morning"),
            activityNodeId=cross_activity_nodes[0]["id"],
            dayNumber=1,
            sortOrder=0,
            slotType="anchor",
            status="completed",
            startTime=base_date.replace(hour=9, minute=0),
            endTime=base_date.replace(hour=11, minute=0),
            durationMinutes=120,
        ),
        make_itinerary_slot(
            trip_id=trip_id,
            id=_did("slot-lunch"),
            activityNodeId=cross_activity_nodes[1]["id"],
            dayNumber=1,
            sortOrder=1,
            slotType="meal",
            status="completed",
            startTime=base_date.replace(hour=12, minute=0),
            endTime=base_date.replace(hour=13, minute=30),
            durationMinutes=90,
        ),
        make_itinerary_slot(
            trip_id=trip_id,
            id=_did("slot-afternoon"),
            activityNodeId=cross_activity_nodes[2]["id"],
            dayNumber=1,
            sortOrder=2,
            slotType="anchor",
            status="completed",
            startTime=base_date.replace(hour=14, minute=0),
            endTime=base_date.replace(hour=16, minute=30),
            durationMinutes=150,
        ),
    ]


@pytest.fixture
def cross_solo_behavioral_signals(
    cross_user: dict,
    cross_solo_trip: dict,
    cross_solo_slots: list[dict],
    cross_activity_nodes: list[dict],
) -> list[dict]:
    """BehavioralSignals written during solo trip generation + active phase.

    Covers three trip phases: pre_trip (generation), active (during trip),
    post_trip (reflection). Each slot gets at least one signal.
    """
    user_id = cross_user["id"]
    trip_id = cross_solo_trip["id"]
    signals = []

    # --- pre_trip: slot impressions from generation ---
    for i, slot in enumerate(cross_solo_slots):
        signals.append(make_behavioral_signal(
            user_id=user_id,
            id=_did(f"bs-pretrip-impression-{i}"),
            tripId=trip_id,
            slotId=slot["id"],
            activityNodeId=cross_activity_nodes[i]["id"],
            signalType="slot_view",
            signalValue=1.0,
            tripPhase="pre_trip",
            rawAction="generation_slot_impression",
            createdAt=_NOW - timedelta(days=10),
        ))

    # --- active: slot interactions during trip ---
    for i, slot in enumerate(cross_solo_slots):
        signals.append(make_behavioral_signal(
            user_id=user_id,
            id=_did(f"bs-active-confirm-{i}"),
            tripId=trip_id,
            slotId=slot["id"],
            activityNodeId=cross_activity_nodes[i]["id"],
            signalType="slot_confirm",
            signalValue=1.0,
            tripPhase="active",
            rawAction="slot_confirmed_by_user",
            createdAt=_NOW - timedelta(days=8) + timedelta(hours=i * 3),
        ))

    # --- post_trip: reflection signals ---
    # loved the morning temple
    signals.append(make_behavioral_signal(
        user_id=user_id,
        id=_did("bs-posttrip-loved-morning"),
        tripId=trip_id,
        slotId=cross_solo_slots[0]["id"],
        activityNodeId=cross_activity_nodes[0]["id"],
        signalType="post_loved",
        signalValue=1.0,
        tripPhase="post_trip",
        rawAction="post_loved",
        createdAt=_NOW - timedelta(hours=4),
    ))
    # skipped the afternoon (retrospective skip)
    signals.append(make_behavioral_signal(
        user_id=user_id,
        id=_did("bs-posttrip-skipped-afternoon"),
        tripId=trip_id,
        slotId=cross_solo_slots[2]["id"],
        activityNodeId=cross_activity_nodes[2]["id"],
        signalType="post_skipped",
        signalValue=-1.0,
        tripPhase="post_trip",
        rawAction="post_skipped",
        createdAt=_NOW - timedelta(hours=3),
    ))

    return signals


# ============================================================================
# Track 6 -- Mid-trip: RawEvents, PivotEvent, pivot signals
# ============================================================================

@pytest.fixture
def cross_raw_events(
    cross_user: dict,
    cross_session: dict,
    cross_solo_trip: dict,
    cross_solo_slots: list[dict],
    cross_activity_nodes: list[dict],
) -> list[dict]:
    """RawEvents spanning generation through post-trip.

    - slot_view events per slot (generation phase)
    - itinerary_generated event (system event)
    - pivot_resolved event (mid-trip)
    """
    user_id = cross_user["id"]
    session_id = cross_session["id"]
    trip_id = cross_solo_trip["id"]
    events = []

    # slot_view per slot
    for i, slot in enumerate(cross_solo_slots):
        events.append(make_raw_event(
            user_id=user_id,
            session_id=session_id,
            id=_did(f"re-slot-view-{i}"),
            tripId=trip_id,
            activityNodeId=cross_activity_nodes[i]["id"],
            clientEventId=f"gen-slot-view-{i}",
            eventType="slot_view",
            intentClass="implicit",
            surface="mobile",
            payload={"slotId": slot["id"], "dayNumber": 1, "sortOrder": i},
            platform="ios",
            createdAt=_NOW - timedelta(days=10, hours=-i),
        ))

    # itinerary_generated
    events.append(make_raw_event(
        user_id=user_id,
        session_id=session_id,
        id=_did("re-itinerary-generated"),
        tripId=trip_id,
        clientEventId="gen-itinerary-complete",
        eventType="itinerary_generated",
        intentClass="contextual",
        surface="mobile",
        payload={
            "tripId": trip_id,
            "slotCount": len(cross_solo_slots),
            "generationMs": 2340,
        },
        platform="ios",
        createdAt=_NOW - timedelta(days=10),
    ))

    # pivot_resolved
    events.append(make_raw_event(
        user_id=user_id,
        session_id=session_id,
        id=_did("re-pivot-resolved"),
        tripId=trip_id,
        activityNodeId=cross_activity_nodes[2]["id"],
        clientEventId="pivot-resolved-001",
        eventType="pivot_resolved",
        intentClass="explicit",
        surface="mobile",
        payload={
            "pivotEventId": _did("pivot-weather"),
            "decision": "accepted",
            "responseTimeMs": 4200,
        },
        platform="ios",
        createdAt=_NOW - timedelta(days=5),
    ))

    return events


@pytest.fixture
def cross_pivot_event(
    cross_solo_trip: dict,
    cross_solo_slots: list[dict],
    cross_activity_nodes: list[dict],
) -> dict:
    """PivotEvent: weather change forced alternative for afternoon slot."""
    return {
        "id": _did("pivot-weather"),
        "tripId": cross_solo_trip["id"],
        "slotId": cross_solo_slots[2]["id"],
        "triggerType": "weather_change",
        "triggerPayload": {
            "condition": "heavy_rain",
            "forecastSource": "openweathermap",
            "temp": 14.0,
        },
        "originalNodeId": cross_activity_nodes[2]["id"],
        "alternativeIds": [_did("node-alt-indoor-1"), _did("node-alt-indoor-2")],
        "selectedNodeId": _did("node-alt-indoor-1"),
        "status": "accepted",
        "resolvedAt": _NOW - timedelta(days=5),
        "responseTimeMs": 4200,
        "createdAt": _NOW - timedelta(days=5, hours=1),
    }


@pytest.fixture
def cross_pivot_behavioral_signals(
    cross_user: dict,
    cross_solo_trip: dict,
    cross_solo_slots: list[dict],
    cross_activity_nodes: list[dict],
) -> list[dict]:
    """Pivot-related behavioral signals (accepted + original node implicit skip)."""
    user_id = cross_user["id"]
    trip_id = cross_solo_trip["id"]
    return [
        make_behavioral_signal(
            user_id=user_id,
            id=_did("bs-pivot-accepted"),
            tripId=trip_id,
            slotId=cross_solo_slots[2]["id"],
            activityNodeId=_did("node-alt-indoor-1"),
            signalType="pivot_accepted",
            signalValue=1.0,
            tripPhase="active",
            rawAction="pivot_accept",
            weatherContext='{"condition": "heavy_rain", "temp": 14.0}',
            createdAt=_NOW - timedelta(days=5),
        ),
        make_behavioral_signal(
            user_id=user_id,
            id=_did("bs-pivot-original-skip"),
            tripId=trip_id,
            slotId=cross_solo_slots[2]["id"],
            activityNodeId=cross_activity_nodes[2]["id"],
            signalType="slot_skip",
            signalValue=-0.5,
            tripPhase="active",
            rawAction="pivot_displaced_original",
            weatherContext='{"condition": "heavy_rain", "temp": 14.0}',
            createdAt=_NOW - timedelta(days=5),
        ),
    ]


# ============================================================================
# Track 7 -- Post-trip: IntentionSignals for disambiguation
# ============================================================================

@pytest.fixture
def cross_intention_signals(
    cross_user: dict,
    cross_solo_behavioral_signals: list[dict],
) -> list[dict]:
    """IntentionSignals for post-trip disambiguation.

    - user_explicit preference for the loved morning activity
    - user_explicit skip reason for the afternoon skip
    """
    user_id = cross_user["id"]
    # Find the post_loved and post_skipped signals
    loved_signal = next(
        s for s in cross_solo_behavioral_signals
        if s["signalType"] == "post_loved"
    )
    skipped_signal = next(
        s for s in cross_solo_behavioral_signals
        if s["signalType"] == "post_skipped"
    )
    return [
        make_intention_signal(
            behavioral_signal_id=loved_signal["id"],
            user_id=user_id,
            id=_did("is-loved-preference"),
            intentionType="preference",
            confidence=1.0,
            source="user_explicit",
            userProvided=True,
            createdAt=_NOW - timedelta(hours=4),
        ),
        make_intention_signal(
            behavioral_signal_id=skipped_signal["id"],
            user_id=user_id,
            id=_did("is-skip-reason"),
            intentionType="not_interested",
            confidence=0.95,
            source="user_explicit",
            userProvided=True,
            rawEventId=None,
            createdAt=_NOW - timedelta(hours=3),
        ),
    ]


# ============================================================================
# Track 5 -- Group: group trip, members, tokens, voting
# ============================================================================

@pytest.fixture
def cross_group_trip(cross_user: dict) -> dict:
    """Group trip to Kyoto with 2 members."""
    return make_trip(
        user_id=cross_user["id"],
        id=_did("group-trip"),
        mode="group",
        status="active",
        destination="Kyoto, Japan",
        city="Kyoto",
        country="Japan",
        timezone="Asia/Tokyo",
        startDate=_NOW + timedelta(days=14),
        endDate=_NOW + timedelta(days=21),
        groupId=_did("group-id"),
        memberCount=2,
        planningProgress=0.6,
        fairnessState={
            "debts": {},
            "resolvedCount": 0,
            "abileneEvents": 0,
        },
        activatedAt=_NOW - timedelta(days=2),
    )


@pytest.fixture
def cross_trip_members(
    cross_user: dict,
    cross_second_user: dict,
    cross_group_trip: dict,
) -> list[dict]:
    """Two TripMembers: organizer + member."""
    trip_id = cross_group_trip["id"]
    return [
        {
            "id": _did("member-organizer"),
            "tripId": trip_id,
            "userId": cross_user["id"],
            "role": "organizer",
            "status": "joined",
            "personaSeed": {"vibes": ["hidden-gem"], "pace": "moderate", "budget": "mid"},
            "energyProfile": {"morning": 0.8, "afternoon": 0.6, "evening": 0.4},
            "joinedAt": _NOW - timedelta(days=5),
            "createdAt": _NOW - timedelta(days=5),
        },
        {
            "id": _did("member-participant"),
            "tripId": trip_id,
            "userId": cross_second_user["id"],
            "role": "member",
            "status": "joined",
            "personaSeed": {"vibes": ["street-food", "nightlife"], "pace": "fast", "budget": "low"},
            "energyProfile": {"morning": 0.3, "afternoon": 0.7, "evening": 0.9},
            "joinedAt": _NOW - timedelta(days=3),
            "createdAt": _NOW - timedelta(days=3),
        },
    ]


@pytest.fixture
def cross_group_slots(
    cross_group_trip: dict,
    cross_activity_nodes: list[dict],
) -> list[dict]:
    """Group trip slots with voteState."""
    trip_id = cross_group_trip["id"]
    base_date = cross_group_trip["startDate"]
    return [
        make_itinerary_slot(
            trip_id=trip_id,
            id=_did("group-slot-0"),
            activityNodeId=cross_activity_nodes[0]["id"],
            dayNumber=1,
            sortOrder=0,
            slotType="anchor",
            status="voted",
            startTime=base_date.replace(hour=10, minute=0),
            endTime=base_date.replace(hour=12, minute=0),
            durationMinutes=120,
            voteState={
                "votes": {
                    _did("cross-user"): "approve",
                    _did("cross-user-2"): "approve",
                },
                "threshold": 0.6,
                "resolved": True,
            },
        ),
        make_itinerary_slot(
            trip_id=trip_id,
            id=_did("group-slot-1"),
            activityNodeId=cross_activity_nodes[1]["id"],
            dayNumber=1,
            sortOrder=1,
            slotType="meal",
            status="proposed",
            startTime=base_date.replace(hour=12, minute=30),
            endTime=base_date.replace(hour=14, minute=0),
            durationMinutes=90,
            voteState={
                "votes": {
                    _did("cross-user"): "approve",
                    _did("cross-user-2"): "reject",
                },
                "threshold": 0.6,
                "resolved": False,
            },
            isContested=True,
        ),
    ]


@pytest.fixture
def cross_invite_token(cross_group_trip: dict, cross_user: dict) -> dict:
    """Active InviteToken for the group trip."""
    return {
        "id": _did("invite-token"),
        "tripId": cross_group_trip["id"],
        "token": "inv-" + _did("invite-token")[:24],
        "createdBy": cross_user["id"],
        "maxUses": 5,
        "usedCount": 1,
        "role": "member",
        "expiresAt": _NOW + timedelta(days=7),
        "revokedAt": None,
        "createdAt": _NOW - timedelta(days=2),
    }


@pytest.fixture
def cross_shared_trip_token(cross_group_trip: dict, cross_user: dict) -> dict:
    """SharedTripToken for read-only trip sharing."""
    return {
        "id": _did("shared-token"),
        "tripId": cross_group_trip["id"],
        "token": "shr-" + _did("shared-token")[:24],
        "createdBy": cross_user["id"],
        "expiresAt": _NOW + timedelta(days=14),
        "revokedAt": None,
        "viewCount": 3,
        "importCount": 0,
        "createdAt": _NOW - timedelta(days=1),
    }


# ============================================================================
# Aggregate fixture: everything at once
# ============================================================================

@pytest.fixture
def cross_track_seed(
    cross_user,
    cross_session,
    cross_second_user,
    cross_vibe_tags,
    cross_activity_nodes,
    cross_activity_node_vibe_tags,
    cross_quality_signals,
    cross_solo_trip,
    cross_solo_slots,
    cross_solo_behavioral_signals,
    cross_raw_events,
    cross_pivot_event,
    cross_pivot_behavioral_signals,
    cross_intention_signals,
    cross_group_trip,
    cross_trip_members,
    cross_group_slots,
    cross_invite_token,
    cross_shared_trip_token,
) -> dict:
    """Complete cross-track seed state as a single dict for convenience.

    Keys mirror model names so tests can do:
        seed = cross_track_seed
        user = seed["user"]
        trip = seed["solo_trip"]
    """
    return {
        "user": cross_user,
        "session": cross_session,
        "second_user": cross_second_user,
        "vibe_tags": cross_vibe_tags,
        "activity_nodes": cross_activity_nodes,
        "activity_node_vibe_tags": cross_activity_node_vibe_tags,
        "quality_signals": cross_quality_signals,
        "solo_trip": cross_solo_trip,
        "solo_slots": cross_solo_slots,
        "behavioral_signals": cross_solo_behavioral_signals,
        "raw_events": cross_raw_events,
        "pivot_event": cross_pivot_event,
        "pivot_behavioral_signals": cross_pivot_behavioral_signals,
        "intention_signals": cross_intention_signals,
        "group_trip": cross_group_trip,
        "trip_members": cross_trip_members,
        "group_slots": cross_group_slots,
        "invite_token": cross_invite_token,
        "shared_trip_token": cross_shared_trip_token,
    }
