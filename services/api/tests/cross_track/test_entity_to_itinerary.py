"""
Cross-track entity-to-itinerary flow tests.

Validates the data handoff between Pipeline (Track 2) ActivityNodes
and Solo (Track 3) itinerary generation.

Strategy:
- Tests use factory-built mock data -- no database, no Qdrant required.
- Each test verifies a specific contract at the boundary between
  pipeline entity output and generation input.

Covers:
1. convergenceScore >= 0.4 threshold for generation eligibility
2. convergenceScore < 0.4 exclusion from candidate pool
3. vibeTagSlugs used in Qdrant search query construction
4. ActivityCategory -> SlotType mapping
5. priceLevel preservation through generation
6. latitude/longitude availability for map pins and spatial queries
7. Entity resolution: same externalSourceId = same place
8. Only 'approved' status nodes enter candidate pool
"""

import uuid
from datetime import datetime, timezone

import pytest

from services.api.tests.conftest import (
    make_activity_node,
    make_itinerary_slot,
)


# ===================================================================
# Constants
# ===================================================================

CONVERGENCE_THRESHOLD = 0.4

# Mapping from ActivityCategory to SlotType used by the generation layer.
# dining -> meal, drinks -> meal, everything else -> activity/flex/anchor
CATEGORY_TO_SLOT_TYPE = {
    "dining": "meal",
    "drinks": "meal",
    "culture": "anchor",
    "outdoors": "anchor",
    "active": "anchor",
    "entertainment": "flex",
    "shopping": "flex",
    "experience": "anchor",
    "nightlife": "flex",
    "group_activity": "anchor",
    "wellness": "flex",
}

# All valid ActivityCategory enum values from the Prisma schema
ALL_CATEGORIES = [
    "dining", "drinks", "culture", "outdoors", "active",
    "entertainment", "shopping", "experience", "nightlife",
    "group_activity", "wellness",
]


# ===================================================================
# Helpers
# ===================================================================

def _build_candidate_pool(nodes: list[dict]) -> list[dict]:
    """Simulate generation's candidate filtering:
    only approved nodes with convergenceScore >= threshold."""
    return [
        n for n in nodes
        if n["status"] == "approved"
        and n.get("convergenceScore") is not None
        and n["convergenceScore"] >= CONVERGENCE_THRESHOLD
    ]


def _map_category_to_slot_type(category: str) -> str:
    """Map ActivityCategory enum to SlotType for slot creation."""
    return CATEGORY_TO_SLOT_TYPE.get(category, "flex")


def _build_qdrant_filter(vibe_tag_slugs: list[str]) -> dict:
    """Simulate the Qdrant search filter built from vibe tag slugs."""
    return {
        "must": [
            {
                "key": "vibe_tags",
                "match": {"any": vibe_tag_slugs},
            }
        ]
    }


def _extract_spatial_data(node: dict) -> dict:
    """Extract lat/lng for map pin placement and spatial queries."""
    return {
        "latitude": node["latitude"],
        "longitude": node["longitude"],
        "name": node["name"],
        "nodeId": node["id"],
    }


# ===================================================================
# 1. convergenceScore >= 0.4 is eligible
# ===================================================================


class TestConvergenceEligibility:
    """Nodes with convergenceScore >= 0.4 enter the generation candidate pool."""

    def test_score_at_threshold_is_eligible(self):
        """Exactly 0.4 should be included."""
        node = make_activity_node(
            convergenceScore=0.4,
            status="approved",
        )
        pool = _build_candidate_pool([node])
        assert len(pool) == 1
        assert pool[0]["id"] == node["id"]

    def test_score_above_threshold_is_eligible(self):
        """Score of 0.85 is well above threshold."""
        node = make_activity_node(
            convergenceScore=0.85,
            status="approved",
        )
        pool = _build_candidate_pool([node])
        assert len(pool) == 1

    def test_high_convergence_nodes_ranked_higher(self):
        """Higher convergenceScore nodes appear in pool and can be sorted."""
        nodes = [
            make_activity_node(
                name=f"Place {i}",
                slug=f"place-{i}",
                convergenceScore=score,
                status="approved",
            )
            for i, score in enumerate([0.5, 0.9, 0.4, 0.7])
        ]
        pool = _build_candidate_pool(nodes)
        assert len(pool) == 4
        # Verify sortable by convergenceScore descending
        sorted_pool = sorted(pool, key=lambda n: n["convergenceScore"], reverse=True)
        assert sorted_pool[0]["convergenceScore"] == 0.9
        assert sorted_pool[-1]["convergenceScore"] == 0.4


# ===================================================================
# 2. convergenceScore < 0.4 is excluded
# ===================================================================


class TestConvergenceExclusion:
    """Nodes with convergenceScore < 0.4 are excluded from generation."""

    def test_score_below_threshold_excluded(self):
        """Score of 0.39 is just below -- should be excluded."""
        node = make_activity_node(
            convergenceScore=0.39,
            status="approved",
        )
        pool = _build_candidate_pool([node])
        assert len(pool) == 0

    def test_score_zero_excluded(self):
        """Zero convergence means no source agreement."""
        node = make_activity_node(
            convergenceScore=0.0,
            status="approved",
        )
        pool = _build_candidate_pool([node])
        assert len(pool) == 0

    def test_score_none_excluded(self):
        """Null convergenceScore (not yet computed) is excluded."""
        node = make_activity_node(
            convergenceScore=None,
            status="approved",
        )
        pool = _build_candidate_pool([node])
        assert len(pool) == 0

    def test_mixed_pool_filters_correctly(self):
        """Pool with mixed scores only includes eligible nodes."""
        nodes = [
            make_activity_node(name="Good", slug="good", convergenceScore=0.7, status="approved"),
            make_activity_node(name="Bad", slug="bad", convergenceScore=0.2, status="approved"),
            make_activity_node(name="Edge", slug="edge", convergenceScore=0.4, status="approved"),
            make_activity_node(name="None", slug="none-score", convergenceScore=None, status="approved"),
        ]
        pool = _build_candidate_pool(nodes)
        pool_names = {n["name"] for n in pool}
        assert pool_names == {"Good", "Edge"}


# ===================================================================
# 3. vibeTagSlugs used in Qdrant search query
# ===================================================================


class TestVibeTagQdrantQuery:
    """ActivityNode vibe tag slugs are passed to Qdrant filter construction."""

    def test_single_vibe_tag_in_filter(self):
        """One vibe tag produces a valid 'match any' filter."""
        slugs = ["hidden-gem"]
        query_filter = _build_qdrant_filter(slugs)
        assert query_filter["must"][0]["key"] == "vibe_tags"
        assert query_filter["must"][0]["match"]["any"] == ["hidden-gem"]

    def test_multiple_vibe_tags_in_filter(self):
        """Multiple vibe tags produce a single 'match any' clause."""
        slugs = ["hidden-gem", "street-food", "local-favorite"]
        query_filter = _build_qdrant_filter(slugs)
        match_any = query_filter["must"][0]["match"]["any"]
        assert set(match_any) == {"hidden-gem", "street-food", "local-favorite"}

    def test_empty_vibe_tags_produces_empty_match(self):
        """No vibe tags results in empty match list (no filtering)."""
        query_filter = _build_qdrant_filter([])
        assert query_filter["must"][0]["match"]["any"] == []

    def test_vibe_tag_slugs_are_lowercase_kebab(self):
        """Vibe tag slugs follow kebab-case convention for Qdrant consistency."""
        slugs = ["hidden-gem", "street-food", "late-night", "family-friendly"]
        for slug in slugs:
            assert slug == slug.lower(), f"Slug '{slug}' should be lowercase"
            assert " " not in slug, f"Slug '{slug}' should not contain spaces"
            # Valid kebab: alphanumeric + hyphens only
            assert all(
                c.isalnum() or c == "-" for c in slug
            ), f"Slug '{slug}' should be kebab-case"


# ===================================================================
# 4. ActivityCategory -> SlotType mapping
# ===================================================================


class TestCategoryToSlotMapping:
    """ActivityNode.category maps correctly to ItinerarySlot.slotType."""

    def test_dining_maps_to_meal(self):
        node = make_activity_node(category="dining")
        slot_type = _map_category_to_slot_type(node["category"])
        assert slot_type == "meal"

    def test_drinks_maps_to_meal(self):
        node = make_activity_node(category="drinks")
        slot_type = _map_category_to_slot_type(node["category"])
        assert slot_type == "meal"

    def test_culture_maps_to_anchor(self):
        node = make_activity_node(category="culture")
        slot_type = _map_category_to_slot_type(node["category"])
        assert slot_type == "anchor"

    def test_outdoors_maps_to_anchor(self):
        node = make_activity_node(category="outdoors")
        slot_type = _map_category_to_slot_type(node["category"])
        assert slot_type == "anchor"

    def test_entertainment_maps_to_flex(self):
        node = make_activity_node(category="entertainment")
        slot_type = _map_category_to_slot_type(node["category"])
        assert slot_type == "flex"

    def test_shopping_maps_to_flex(self):
        node = make_activity_node(category="shopping")
        slot_type = _map_category_to_slot_type(node["category"])
        assert slot_type == "flex"

    @pytest.mark.parametrize("category", ALL_CATEGORIES)
    def test_all_categories_have_mapping(self, category: str):
        """Every ActivityCategory enum value produces a valid SlotType."""
        slot_type = _map_category_to_slot_type(category)
        valid_slot_types = {"anchor", "flex", "meal", "rest", "transit"}
        assert slot_type in valid_slot_types, (
            f"Category '{category}' mapped to '{slot_type}' which is not a valid SlotType"
        )

    def test_slot_created_with_mapped_type(self):
        """End-to-end: node category flows into slot slotType field."""
        node = make_activity_node(category="dining", status="approved", convergenceScore=0.8)
        slot_type = _map_category_to_slot_type(node["category"])
        slot = make_itinerary_slot(
            activityNodeId=node["id"],
            slotType=slot_type,
        )
        assert slot["slotType"] == "meal"
        assert slot["activityNodeId"] == node["id"]


# ===================================================================
# 5. priceLevel preserved through generation
# ===================================================================


class TestPriceLevelPreservation:
    """ActivityNode.priceLevel is accessible in generated slot metadata."""

    def test_price_level_available_on_node(self):
        """Node carries priceLevel from pipeline scraping."""
        node = make_activity_node(priceLevel=2)
        assert node["priceLevel"] == 2

    def test_price_level_none_for_free_venues(self):
        """Parks, shrines, etc. may have null priceLevel."""
        node = make_activity_node(category="outdoors", priceLevel=None)
        assert node["priceLevel"] is None

    def test_price_level_range(self):
        """priceLevel typically 1-4 (Foursquare/Google convention)."""
        for level in [1, 2, 3, 4]:
            node = make_activity_node(priceLevel=level)
            assert node["priceLevel"] == level

    def test_price_level_flows_to_slot_via_node_reference(self):
        """Slot references the node; priceLevel is accessible through the join."""
        node = make_activity_node(
            priceLevel=3,
            category="dining",
            status="approved",
            convergenceScore=0.6,
        )
        slot = make_itinerary_slot(activityNodeId=node["id"])
        # In production, slot.activityNode.priceLevel is the join path.
        # Here we verify the FK is set so the join is possible.
        assert slot["activityNodeId"] == node["id"]
        assert node["priceLevel"] == 3


# ===================================================================
# 6. latitude/longitude for map pins and spatial queries
# ===================================================================


class TestSpatialData:
    """ActivityNode lat/lng used for map placement and micro-stop queries."""

    def test_lat_lng_present_on_node(self):
        """Every ActivityNode has latitude and longitude (required fields)."""
        node = make_activity_node()
        assert node["latitude"] is not None
        assert node["longitude"] is not None
        assert isinstance(node["latitude"], float)
        assert isinstance(node["longitude"], float)

    def test_lat_lng_valid_ranges(self):
        """Latitude [-90, 90], Longitude [-180, 180]."""
        node = make_activity_node(latitude=35.6762, longitude=139.6503)
        assert -90 <= node["latitude"] <= 90
        assert -180 <= node["longitude"] <= 180

    def test_spatial_data_extraction_for_map_pins(self):
        """Extract lat/lng into map pin format for frontend."""
        node = make_activity_node(
            name="Tsukiji Outer Market",
            latitude=35.6654,
            longitude=139.7707,
        )
        pin = _extract_spatial_data(node)
        assert pin["latitude"] == 35.6654
        assert pin["longitude"] == 139.7707
        assert pin["name"] == "Tsukiji Outer Market"
        assert pin["nodeId"] == node["id"]

    def test_micro_stop_spatial_proximity(self):
        """Two nodes within ~200m can be identified as micro-stop candidates."""
        node_a = make_activity_node(
            name="Ramen Shop",
            slug="ramen-shop",
            latitude=35.6580,
            longitude=139.7016,
        )
        node_b = make_activity_node(
            name="Nearby Cafe",
            slug="nearby-cafe",
            # ~150m northeast
            latitude=35.6593,
            longitude=139.7028,
        )
        # Haversine approximation: 0.001 degree latitude ~ 111m
        lat_diff = abs(node_a["latitude"] - node_b["latitude"])
        lng_diff = abs(node_a["longitude"] - node_b["longitude"])
        # Both diffs < 0.002 degrees (~220m) = plausible micro-stop proximity
        assert lat_diff < 0.002
        assert lng_diff < 0.002

    def test_distant_nodes_not_micro_stop_candidates(self):
        """Nodes > 500m apart should not be micro-stop candidates."""
        node_a = make_activity_node(
            name="Shibuya Crossing",
            slug="shibuya-crossing",
            latitude=35.6595,
            longitude=139.7004,
        )
        node_b = make_activity_node(
            name="Tokyo Tower",
            slug="tokyo-tower",
            latitude=35.6586,
            longitude=139.7454,
        )
        lng_diff = abs(node_a["longitude"] - node_b["longitude"])
        # ~0.045 degrees longitude ~ 4km at this latitude
        assert lng_diff > 0.005, "These nodes should be far apart"


# ===================================================================
# 7. Entity resolution: same externalSourceId = same place
# ===================================================================


class TestEntityResolutionContract:
    """Nodes with the same external source ID represent the same place."""

    def test_same_foursquare_id_is_same_entity(self):
        """Two nodes with identical foursquareId should resolve to one."""
        fsq_id = "4b5a1e3ef964a52040e928e3"
        node_a = make_activity_node(
            name="Ichiran Shibuya",
            slug="ichiran-shibuya-a",
            foursquareId=fsq_id,
        )
        node_b = make_activity_node(
            name="Ichiran Ramen Shibuya",
            slug="ichiran-shibuya-b",
            foursquareId=fsq_id,
        )
        assert node_a["foursquareId"] == node_b["foursquareId"]
        # In production, entity resolution would merge these into one canonical node

    def test_same_google_place_id_is_same_entity(self):
        """Two nodes with identical googlePlaceId should resolve to one."""
        gp_id = "ChIJN1t_tDeuEmsRUsoyG83frY4"
        node_a = make_activity_node(
            name="Meiji Jingu",
            slug="meiji-jingu-a",
            googlePlaceId=gp_id,
        )
        node_b = make_activity_node(
            name="Meiji Shrine",
            slug="meiji-jingu-b",
            googlePlaceId=gp_id,
        )
        assert node_a["googlePlaceId"] == node_b["googlePlaceId"]

    def test_different_external_ids_are_different_entities(self):
        """Nodes with different external IDs are distinct places."""
        node_a = make_activity_node(
            foursquareId="fsq-aaa",
            googlePlaceId=None,
        )
        node_b = make_activity_node(
            foursquareId="fsq-bbb",
            googlePlaceId=None,
        )
        assert node_a["foursquareId"] != node_b["foursquareId"]

    def test_null_external_ids_are_not_matched(self):
        """Two nodes with null externalSourceIds should not auto-match."""
        node_a = make_activity_node(foursquareId=None, googlePlaceId=None)
        node_b = make_activity_node(foursquareId=None, googlePlaceId=None)
        # Both have None -- they should NOT be treated as the same entity
        # Entity resolution requires at least one non-null external ID match
        has_match = (
            (node_a["foursquareId"] is not None and node_a["foursquareId"] == node_b["foursquareId"])
            or (node_a["googlePlaceId"] is not None and node_a["googlePlaceId"] == node_b["googlePlaceId"])
        )
        assert not has_match

    def test_resolved_node_points_to_canonical(self):
        """A non-canonical (merged) node has resolvedToId pointing to the winner."""
        canonical = make_activity_node(
            name="Ichiran Shibuya",
            slug="ichiran-canonical",
            isCanonical=True,
            resolvedToId=None,
        )
        duplicate = make_activity_node(
            name="Ichiran Ramen Shibuya Branch",
            slug="ichiran-duplicate",
            isCanonical=False,
            resolvedToId=canonical["id"],
        )
        assert canonical["isCanonical"] is True
        assert duplicate["isCanonical"] is False
        assert duplicate["resolvedToId"] == canonical["id"]


# ===================================================================
# 8. Only 'approved' status nodes enter candidate pool
# ===================================================================


class TestNodeStatusGating:
    """Generation only considers ActivityNodes with status='approved'."""

    def test_approved_node_enters_pool(self):
        """Status 'approved' with valid convergence passes filtering."""
        node = make_activity_node(status="approved", convergenceScore=0.6)
        pool = _build_candidate_pool([node])
        assert len(pool) == 1

    def test_pending_node_excluded(self):
        """Status 'pending' is not ready for generation."""
        node = make_activity_node(status="pending", convergenceScore=0.8)
        pool = _build_candidate_pool([node])
        assert len(pool) == 0

    def test_flagged_node_excluded(self):
        """Status 'flagged' means content issues -- must not enter pool."""
        node = make_activity_node(
            status="flagged",
            convergenceScore=0.9,
            flagReason="inappropriate_content",
        )
        pool = _build_candidate_pool([node])
        assert len(pool) == 0

    def test_archived_node_excluded(self):
        """Status 'archived' means deprecated -- must not enter pool."""
        node = make_activity_node(status="archived", convergenceScore=0.7)
        pool = _build_candidate_pool([node])
        assert len(pool) == 0

    @pytest.mark.parametrize("status", ["pending", "flagged", "archived"])
    def test_non_approved_statuses_all_excluded(self, status: str):
        """Parametric check that every non-approved status is excluded."""
        node = make_activity_node(status=status, convergenceScore=0.75)
        pool = _build_candidate_pool([node])
        assert len(pool) == 0, f"Status '{status}' should be excluded from pool"

    def test_mixed_status_pool(self):
        """Only approved nodes survive filtering from a mixed pool."""
        nodes = [
            make_activity_node(name="Approved1", slug="a1", status="approved", convergenceScore=0.5),
            make_activity_node(name="Pending1", slug="p1", status="pending", convergenceScore=0.8),
            make_activity_node(name="Approved2", slug="a2", status="approved", convergenceScore=0.6),
            make_activity_node(name="Flagged1", slug="f1", status="flagged", convergenceScore=0.9),
            make_activity_node(name="Archived1", slug="ar1", status="archived", convergenceScore=0.7),
        ]
        pool = _build_candidate_pool(nodes)
        pool_names = {n["name"] for n in pool}
        assert pool_names == {"Approved1", "Approved2"}

    def test_approved_but_low_convergence_still_excluded(self):
        """Status approved is necessary but not sufficient --
        convergence threshold must also be met."""
        node = make_activity_node(
            status="approved",
            convergenceScore=0.2,
        )
        pool = _build_candidate_pool([node])
        assert len(pool) == 0
