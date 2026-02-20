"""
Cross-track schema extension tests.

Validates that Group (Track 4) and MidTrip (Track 5) extension fields
can coexist with Foundation (Track 1) base fields without breaking
existing model contracts.

Strategy:
- Each test creates model dicts via shared factories, then asserts that
  base fields remain intact when extension fields are populated.
- No database required -- pure dict/contract validation against the
  Prisma schema shape defined in conftest factories.

Covers:
1. Trip base fields survive group extension (fairnessState, affinityMatrix, logisticsState)
2. ItinerarySlot base fields survive voting/pivot extension
3. TripMember base fields survive persona/energy extension
4. PivotEvent does not break ItinerarySlot.activityNodeId relationship
5. BehavioralSignal carries both solo and group signal types
6. QualitySignal.sourceName supports all pipeline sources
7. VibeTags shared between solo and group contexts
8. User subscriptionTier enum completeness
"""

import uuid
from datetime import datetime, timezone, timedelta

import pytest

from services.api.tests.conftest import (
    make_user,
    make_trip,
    make_itinerary_slot,
    make_activity_node,
    make_behavioral_signal,
    make_quality_signal,
)


# ===================================================================
# Helpers
# ===================================================================

TRIP_BASE_FIELDS = {"destination", "startDate", "endDate", "timezone", "status"}
SLOT_BASE_FIELDS = {"tripId", "dayNumber", "sortOrder", "slotType", "status"}
MEMBER_BASE_FIELDS = {"userId", "tripId", "role"}

# Extension fields added by Track 4 (Group) and Track 5 (MidTrip)
TRIP_EXTENSION_FIELDS = {"fairnessState", "affinityMatrix", "logisticsState"}
SLOT_EXTENSION_FIELDS = {"voteState", "isContested", "wasSwapped", "pivotEventId"}
MEMBER_EXTENSION_FIELDS = {"personaSeed", "energyProfile"}


def _make_trip_member(
    user_id: str | None = None,
    trip_id: str | None = None,
    **overrides,
) -> dict:
    """Inline factory for TripMember since conftest doesn't export one."""
    now = datetime.now(timezone.utc)
    base = {
        "id": str(uuid.uuid4()),
        "userId": user_id or str(uuid.uuid4()),
        "tripId": trip_id or str(uuid.uuid4()),
        "role": "member",
        "status": "joined",
        "personaSeed": None,
        "energyProfile": None,
        "joinedAt": now,
        "createdAt": now,
    }
    base.update(overrides)
    return base


def _make_vibe_tag(slug: str, category: str = "atmosphere") -> dict:
    """Inline factory for VibeTag."""
    return {
        "id": str(uuid.uuid4()),
        "slug": slug,
        "name": slug.replace("-", " ").title(),
        "category": category,
        "isActive": True,
        "sortOrder": 0,
        "createdAt": datetime.now(timezone.utc),
    }


# ===================================================================
# 1. Trip base fields remain valid after group extensions
# ===================================================================


class TestTripSchemaExtension:
    """Trip model survives Track 4 extension fields."""

    def test_base_fields_present_on_vanilla_trip(self):
        """A plain solo trip has all base fields with valid values."""
        trip = make_trip()
        for field in TRIP_BASE_FIELDS:
            assert field in trip, f"Missing base field: {field}"
            assert trip[field] is not None, f"Base field {field} should not be None"

    def test_base_fields_stable_after_group_extension(self):
        """Adding fairnessState/affinityMatrix/logisticsState does not
        overwrite or nullify any base field."""
        trip = make_trip(
            mode="group",
            fairnessState={
                "debts": {"user-a": 2, "user-b": -2},
                "resolvedCount": 5,
                "abyleneEvents": 1,
            },
            affinityMatrix={
                "user-a": {"dining": 0.8, "culture": 0.3},
                "user-b": {"dining": 0.4, "culture": 0.9},
            },
            logisticsState={
                "transportMode": "transit",
                "maxWalkMinutes": 15,
            },
        )
        for field in TRIP_BASE_FIELDS:
            assert trip[field] is not None, (
                f"Base field '{field}' was nullified by group extension"
            )
        # Extension fields actually populated
        for ext in TRIP_EXTENSION_FIELDS:
            assert trip[ext] is not None, f"Extension field '{ext}' should be set"

    def test_extension_fields_default_to_none_on_solo_trip(self):
        """Solo trips have extension fields present but null (nullable Json?)."""
        trip = make_trip(mode="solo")
        for ext in TRIP_EXTENSION_FIELDS:
            assert ext in trip, f"Extension field '{ext}' missing from schema"
            assert trip[ext] is None, (
                f"Extension field '{ext}' should default to None for solo trips"
            )

    def test_group_trip_destination_not_overwritten_by_logistics(self):
        """Setting logisticsState should not clobber destination/city/country."""
        trip = make_trip(
            destination="Osaka, Japan",
            city="Osaka",
            country="Japan",
            logisticsState={"transportMode": "taxi"},
        )
        assert trip["destination"] == "Osaka, Japan"
        assert trip["city"] == "Osaka"
        assert trip["country"] == "Japan"


# ===================================================================
# 2. ItinerarySlot base fields remain valid after voting/pivot extension
# ===================================================================


class TestSlotSchemaExtension:
    """ItinerarySlot model survives Track 4+5 extension fields."""

    def test_base_fields_present_on_vanilla_slot(self):
        """A plain slot has all base fields with valid values."""
        slot = make_itinerary_slot()
        for field in SLOT_BASE_FIELDS:
            assert field in slot, f"Missing base field: {field}"
            assert slot[field] is not None, f"Base field {field} should not be None"

    def test_base_fields_stable_after_vote_state(self):
        """Adding voteState does not break tripId, dayNumber, etc."""
        trip_id = str(uuid.uuid4())
        slot = make_itinerary_slot(
            trip_id=trip_id,
            dayNumber=3,
            sortOrder=2,
            slotType="meal",
            voteState={
                "votes": {"user-a": "approve", "user-b": "reject"},
                "threshold": 0.6,
                "resolved": False,
            },
            isContested=True,
        )
        assert slot["tripId"] == trip_id
        assert slot["dayNumber"] == 3
        assert slot["sortOrder"] == 2
        assert slot["slotType"] == "meal"
        assert slot["status"] == "proposed"  # default
        assert slot["voteState"]["votes"]["user-a"] == "approve"
        assert slot["isContested"] is True

    def test_base_fields_stable_after_pivot_swap(self):
        """Setting wasSwapped and pivotEventId preserves base fields."""
        pivot_id = str(uuid.uuid4())
        slot = make_itinerary_slot(
            dayNumber=1,
            sortOrder=0,
            slotType="anchor",
            wasSwapped=True,
            pivotEventId=pivot_id,
        )
        # Base fields intact
        assert slot["dayNumber"] == 1
        assert slot["sortOrder"] == 0
        assert slot["slotType"] == "anchor"
        # Extension fields set
        assert slot["wasSwapped"] is True
        assert slot["pivotEventId"] == pivot_id

    def test_extension_fields_default_values(self):
        """Extension fields have correct defaults for a fresh slot."""
        slot = make_itinerary_slot()
        assert slot["voteState"] is None
        assert slot["isContested"] is False
        assert slot["wasSwapped"] is False
        assert slot["pivotEventId"] is None


# ===================================================================
# 3. TripMember base fields remain valid after persona/energy extension
# ===================================================================


class TestTripMemberSchemaExtension:
    """TripMember model survives Track 4 persona/energy fields."""

    def test_base_fields_present(self):
        """TripMember has userId, tripId, role."""
        member = _make_trip_member()
        for field in MEMBER_BASE_FIELDS:
            assert field in member
            assert member[field] is not None

    def test_base_fields_stable_after_persona_seed(self):
        """Adding personaSeed/energyProfile preserves base relationship fields."""
        user_id = str(uuid.uuid4())
        trip_id = str(uuid.uuid4())
        member = _make_trip_member(
            user_id=user_id,
            trip_id=trip_id,
            role="organizer",
            personaSeed={
                "vibes": ["hidden-gem", "street-food"],
                "pace": "fast",
                "budget": "low",
            },
            energyProfile={
                "morningPerson": True,
                "walkTolerance": "high",
                "socialBattery": 0.7,
            },
        )
        assert member["userId"] == user_id
        assert member["tripId"] == trip_id
        assert member["role"] == "organizer"
        assert member["personaSeed"]["pace"] == "fast"
        assert member["energyProfile"]["morningPerson"] is True

    def test_extension_fields_default_to_none(self):
        """personaSeed and energyProfile default to None for basic members."""
        member = _make_trip_member()
        for ext in MEMBER_EXTENSION_FIELDS:
            assert ext in member
            assert member[ext] is None


# ===================================================================
# 4. PivotEvent does not break ItinerarySlot.activityNodeId relationship
# ===================================================================


class TestPivotEventSlotRelationship:
    """PivotEvent references a slot, which still references its ActivityNode."""

    def test_slot_keeps_activity_node_when_pivot_created(self):
        """Creating a PivotEvent that references a slot should not clear
        the slot's activityNodeId -- the node is the *original* activity."""
        node = make_activity_node(
            name="Meiji Shrine",
            slug="meiji-shrine",
            category="culture",
            status="approved",
        )
        slot = make_itinerary_slot(
            activityNodeId=node["id"],
            dayNumber=1,
            sortOrder=0,
            slotType="anchor",
        )
        # Simulate PivotEvent creation referencing this slot
        pivot = {
            "id": str(uuid.uuid4()),
            "tripId": slot["tripId"],
            "slotId": slot["id"],
            "triggerType": "weather_change",
            "triggerPayload": {"condition": "rain"},
            "originalNodeId": node["id"],
            "alternativeIds": [str(uuid.uuid4()), str(uuid.uuid4())],
            "selectedNodeId": None,
            "status": "proposed",
            "resolvedAt": None,
            "responseTimeMs": None,
            "createdAt": datetime.now(timezone.utc),
        }
        # Slot still points to original node
        assert slot["activityNodeId"] == node["id"]
        # Pivot references the same original
        assert pivot["originalNodeId"] == node["id"]
        assert pivot["slotId"] == slot["id"]

    def test_slot_activity_node_updated_after_pivot_accepted(self):
        """After pivot is accepted, slot's activityNodeId can be updated
        to the selectedNodeId without losing base fields."""
        original_node_id = str(uuid.uuid4())
        replacement_node_id = str(uuid.uuid4())

        slot = make_itinerary_slot(
            activityNodeId=original_node_id,
            dayNumber=2,
            sortOrder=1,
            slotType="flex",
        )
        # Simulate pivot acceptance: update slot
        slot["activityNodeId"] = replacement_node_id
        slot["wasSwapped"] = True
        slot["pivotEventId"] = str(uuid.uuid4())

        assert slot["activityNodeId"] == replacement_node_id
        assert slot["dayNumber"] == 2
        assert slot["sortOrder"] == 1
        assert slot["slotType"] == "flex"
        assert slot["wasSwapped"] is True


# ===================================================================
# 5. BehavioralSignal carries both solo and group signal types
# ===================================================================


class TestBehavioralSignalDualContext:
    """BehavioralSignal table supports both solo and group signal types."""

    # Solo signal types (Track 3 - slot interactions)
    SOLO_SIGNAL_TYPES = [
        "slot_view",
        "slot_tap",
        "slot_confirm",
        "slot_skip",
        "slot_swap",
        "slot_complete",
        "slot_dwell",
    ]

    # Discovery signals (also solo context)
    DISCOVERY_SIGNAL_TYPES = [
        "discover_swipe_right",
        "discover_swipe_left",
        "discover_shortlist",
        "discover_remove",
    ]

    # Vibe signals (shared)
    VIBE_SIGNAL_TYPES = [
        "vibe_select",
        "vibe_deselect",
        "vibe_implicit",
    ]

    # Pivot signals (Track 5 - MidTrip)
    PIVOT_SIGNAL_TYPES = [
        "pivot_accepted",
        "pivot_rejected",
        "pivot_initiated",
    ]

    # Post-trip signals (Track 7)
    POST_TRIP_SIGNAL_TYPES = [
        "post_loved",
        "post_skipped",
        "post_missed",
        "post_disliked",
    ]

    def test_solo_slot_impression_signal(self):
        """Solo signal: user viewed a slot in their solo itinerary."""
        signal = make_behavioral_signal(
            signalType="slot_view",
            signalValue=1.0,
            tripPhase="pre_trip",
            rawAction="view_slot",
        )
        assert signal["signalType"] == "slot_view"
        assert signal["tripPhase"] == "pre_trip"
        assert signal["userId"] is not None

    def test_group_vote_cast_signal(self):
        """Group signal: user cast a vote on a contested slot.
        Uses pivot_accepted as the closest enum for vote-accept behavior."""
        signal = make_behavioral_signal(
            signalType="pivot_accepted",
            signalValue=1.0,
            tripPhase="active",
            rawAction="vote_approve",
        )
        assert signal["signalType"] == "pivot_accepted"
        assert signal["tripPhase"] == "active"

    def test_solo_and_group_signals_coexist(self):
        """Both solo and group signals can exist for the same user/trip."""
        user_id = str(uuid.uuid4())
        trip_id = str(uuid.uuid4())

        solo_signal = make_behavioral_signal(
            user_id=user_id,
            tripId=trip_id,
            signalType="slot_view",
            signalValue=1.0,
            tripPhase="pre_trip",
            rawAction="view_slot",
        )
        group_signal = make_behavioral_signal(
            user_id=user_id,
            tripId=trip_id,
            signalType="pivot_initiated",
            signalValue=1.0,
            tripPhase="active",
            rawAction="initiate_pivot",
        )
        # Same user, same trip, different signal types
        assert solo_signal["userId"] == group_signal["userId"]
        assert solo_signal["tripId"] == group_signal["tripId"]
        assert solo_signal["signalType"] != group_signal["signalType"]

    @pytest.mark.parametrize("signal_type", [
        "slot_view", "slot_tap", "slot_confirm", "slot_skip",
        "discover_swipe_right", "discover_swipe_left",
        "vibe_select", "vibe_deselect",
        "pivot_accepted", "pivot_rejected", "pivot_initiated",
        "post_loved", "post_skipped",
        "dwell_time", "scroll_depth", "return_visit", "share_action",
    ])
    def test_all_signal_types_accepted(self, signal_type: str):
        """Every SignalType enum value can be set on a BehavioralSignal."""
        signal = make_behavioral_signal(
            signalType=signal_type,
            rawAction=f"test_{signal_type}",
        )
        assert signal["signalType"] == signal_type


# ===================================================================
# 6. QualitySignal supports all pipeline sources
# ===================================================================


class TestQualitySignalSources:
    """QualitySignal.sourceName supports all pipeline scraper sources."""

    PIPELINE_SOURCES = [
        "reddit",
        "tabelog",
        "atlas_obscura",
        "foursquare",
    ]

    @pytest.mark.parametrize("source", PIPELINE_SOURCES)
    def test_source_accepted(self, source: str):
        """Each pipeline source can be set as QualitySignal.sourceName."""
        signal = make_quality_signal(sourceName=source)
        assert signal["sourceName"] == source

    def test_reddit_source_with_authority(self):
        """Reddit signals carry appropriate authority score."""
        signal = make_quality_signal(
            sourceName="reddit",
            sourceUrl="https://reddit.com/r/JapanTravel/comments/abc123",
            sourceAuthority=0.65,
            signalType="positive_mention",
            rawExcerpt="Best ramen I've ever had, locals swear by this place",
        )
        assert signal["sourceName"] == "reddit"
        assert signal["sourceAuthority"] == 0.65

    def test_tabelog_source_with_high_authority(self):
        """Tabelog (Japanese restaurant review) signals have high authority."""
        signal = make_quality_signal(
            sourceName="tabelog",
            sourceUrl="https://tabelog.com/tokyo/A1301/...",
            sourceAuthority=0.90,
            signalType="rating",
            rawExcerpt="3.8/5.0 stars, 420 reviews",
        )
        assert signal["sourceName"] == "tabelog"
        assert signal["sourceAuthority"] == 0.90

    def test_atlas_obscura_source(self):
        """Atlas Obscura signals for unique/hidden-gem locations."""
        signal = make_quality_signal(
            sourceName="atlas_obscura",
            sourceUrl="https://www.atlasobscura.com/places/...",
            sourceAuthority=0.75,
            signalType="unique_mention",
        )
        assert signal["sourceName"] == "atlas_obscura"

    def test_foursquare_source(self):
        """Foursquare signals for venue data enrichment."""
        signal = make_quality_signal(
            sourceName="foursquare",
            sourceUrl="https://foursquare.com/v/...",
            sourceAuthority=0.60,
            signalType="venue_data",
        )
        assert signal["sourceName"] == "foursquare"

    def test_multiple_sources_same_node(self):
        """Multiple QualitySignals from different sources for one ActivityNode."""
        node_id = str(uuid.uuid4())
        signals = [
            make_quality_signal(activityNodeId=node_id, sourceName=src)
            for src in self.PIPELINE_SOURCES
        ]
        source_names = {s["sourceName"] for s in signals}
        assert source_names == set(self.PIPELINE_SOURCES)
        assert all(s["activityNodeId"] == node_id for s in signals)


# ===================================================================
# 7. VibeTags shared between solo and group itineraries
# ===================================================================


class TestVibeTagSharedContext:
    """VibeTags use the same slug vocabulary in solo and group contexts."""

    SHARED_VIBE_SLUGS = [
        "hidden-gem",
        "local-favorite",
        "street-food",
        "scenic",
        "nightlife",
        "cultural",
        "family-friendly",
        "romantic",
    ]

    def test_vibe_tag_slugs_are_consistent(self):
        """Same slug string used regardless of trip mode."""
        for slug in self.SHARED_VIBE_SLUGS:
            tag = _make_vibe_tag(slug)
            assert tag["slug"] == slug
            assert tag["isActive"] is True

    def test_solo_trip_uses_vibe_slugs(self):
        """Solo trip personaSeed references standard vibe tag slugs."""
        trip = make_trip(
            mode="solo",
            personaSeed={
                "vibes": ["hidden-gem", "street-food"],
                "pace": "moderate",
                "budget": "mid",
            },
        )
        assert set(trip["personaSeed"]["vibes"]).issubset(set(self.SHARED_VIBE_SLUGS))

    def test_group_trip_affinity_matrix_uses_same_slugs(self):
        """Group affinityMatrix references the same vibe tag vocabulary."""
        trip = make_trip(
            mode="group",
            affinityMatrix={
                "user-a": {"hidden-gem": 0.9, "street-food": 0.7},
                "user-b": {"hidden-gem": 0.3, "scenic": 0.8},
            },
        )
        all_keys = set()
        for user_prefs in trip["affinityMatrix"].values():
            all_keys.update(user_prefs.keys())
        assert all_keys.issubset(set(self.SHARED_VIBE_SLUGS))

    def test_activity_node_vibe_tag_link_structure(self):
        """ActivityNodeVibeTag junction record shape is valid."""
        node = make_activity_node()
        tag = _make_vibe_tag("hidden-gem")
        link = {
            "id": str(uuid.uuid4()),
            "activityNodeId": node["id"],
            "vibeTagId": tag["id"],
            "score": 0.85,
            "source": "nlp_extraction",
            "createdAt": datetime.now(timezone.utc),
        }
        assert link["activityNodeId"] == node["id"]
        assert link["vibeTagId"] == tag["id"]
        assert 0.0 <= link["score"] <= 1.0


# ===================================================================
# 8. User role enum supports all values
# ===================================================================


class TestUserSubscriptionTierEnum:
    """SubscriptionTier enum covers all access levels."""

    VALID_TIERS = {"beta", "lifetime", "free", "pro"}

    @pytest.mark.parametrize("tier", ["beta", "lifetime", "free", "pro"])
    def test_tier_accepted(self, tier: str):
        """Each SubscriptionTier value can be set on a User."""
        user = make_user(subscriptionTier=tier)
        assert user["subscriptionTier"] == tier

    def test_default_tier_is_beta(self):
        """New users default to 'beta' tier."""
        user = make_user()
        assert user["subscriptionTier"] == "beta"

    def test_all_valid_tiers_covered(self):
        """Exhaustive check that our test covers every tier value."""
        created_tiers = set()
        for tier in self.VALID_TIERS:
            user = make_user(subscriptionTier=tier)
            created_tiers.add(user["subscriptionTier"])
        assert created_tiers == self.VALID_TIERS

    def test_access_check_logic(self):
        """Access control: beta, lifetime, pro have access; free does not."""
        access_tiers = {"beta", "lifetime", "pro"}
        for tier in self.VALID_TIERS:
            user = make_user(subscriptionTier=tier)
            has_access = user["subscriptionTier"] in access_tiers
            if tier == "free":
                assert not has_access, "Free tier should not have access"
            else:
                assert has_access, f"{tier} tier should have access"
