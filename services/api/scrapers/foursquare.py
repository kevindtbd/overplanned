"""
Foursquare Places API v3 client for structured venue data.

Searches venues by city + category, maps Foursquare categories to our
11 coarse ActivityCategory enum, and produces ActivityNode + QualitySignal rows.
"""

import os
import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx

from .base import BaseScraper, SourceRegistry, DeadLetterQueue

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Daily quota tracking (950 free calls/day)
# ---------------------------------------------------------------------------
DAILY_QUOTA = 950
QUOTA_PATH = Path("data/foursquare_quota.json")
QUOTA_PATH.parent.mkdir(parents=True, exist_ok=True)


def _read_quota() -> Dict[str, Any]:
    """Read today's quota state from disk."""
    if QUOTA_PATH.exists():
        with open(QUOTA_PATH, "r") as f:
            data = json.load(f)
        if data.get("date") == str(date.today()):
            return data
    return {"date": str(date.today()), "calls": 0}


def _write_quota(state: Dict[str, Any]) -> None:
    """Persist quota state to disk."""
    with open(QUOTA_PATH, "w") as f:
        json.dump(state, f)


def _increment_quota(count: int = 1) -> int:
    """Increment and return updated call count. Raises if over quota."""
    state = _read_quota()
    if state["calls"] + count > DAILY_QUOTA:
        raise RuntimeError(
            f"Foursquare daily quota would be exceeded: "
            f"{state['calls']}/{DAILY_QUOTA} used, requested {count} more"
        )
    state["calls"] += count
    _write_quota(state)
    return state["calls"]


# ---------------------------------------------------------------------------
# Foursquare category → ActivityCategory mapping
# ---------------------------------------------------------------------------
# Our 11 coarse categories:
#   dining, drinks, culture, outdoors, active, entertainment,
#   shopping, experience, nightlife, group_activity, wellness

# Foursquare v3 top-level category IDs (from their taxonomy):
# https://docs.foursquare.com/data-products/docs/categories
FOURSQUARE_CATEGORY_MAP: Dict[str, str] = {
    # Dining
    "13000": "dining",       # Dining and Drinking (top-level)
    "13065": "dining",       # Restaurant
    "13003": "dining",       # Bakery
    "13028": "dining",       # Café, Coffee, and Tea House
    "13029": "dining",       # Coffee Shop
    "13031": "dining",       # Dessert Shop
    "13034": "dining",       # Fast Food Restaurant
    "13040": "dining",       # Food Court
    "13064": "dining",       # Pizzeria
    "13145": "dining",       # Noodle House
    "13236": "dining",       # Food Truck
    "13377": "dining",       # Seafood Restaurant
    "13383": "dining",       # Steakhouse

    # Drinks
    "13002": "drinks",       # Bar
    "13025": "drinks",       # Brewery
    "13050": "drinks",       # Juice Bar
    "13063": "drinks",       # Winery

    # Culture
    "10000": "culture",      # Arts and Entertainment (top-level, default)
    "10002": "culture",      # Amphitheater
    "10025": "culture",      # Museum
    "10027": "culture",      # Art Gallery
    "10028": "culture",      # Historic and Protected Site
    "10029": "culture",      # Library
    "10032": "culture",      # Monument
    "10044": "culture",      # Temple
    "10051": "culture",      # Cultural Center

    # Outdoors
    "16000": "outdoors",     # Outdoors and Recreation (top-level)
    "16009": "outdoors",     # Beach
    "16015": "outdoors",     # Garden
    "16019": "outdoors",     # Lake
    "16025": "outdoors",     # National Park
    "16032": "outdoors",     # Park
    "16039": "outdoors",     # Scenic Lookout
    "16043": "outdoors",     # Trail
    "16046": "outdoors",     # Waterfall

    # Active
    "18000": "active",       # Sports and Recreation (top-level)
    "18008": "active",       # Climbing Gym
    "18021": "active",       # Gym / Fitness Center
    "18036": "active",       # Bike Rental / Bike Share
    "18037": "active",       # Skate Park
    "18060": "active",       # Surf Spot
    "18067": "active",       # Swimming Pool

    # Entertainment
    "10003": "entertainment",  # Arcade
    "10004": "entertainment",  # Aquarium
    "10024": "entertainment",  # Movie Theater
    "10047": "entertainment",  # Theme Park
    "10056": "entertainment",  # Zoo
    "10014": "entertainment",  # Comedy Club
    "10042": "entertainment",  # Performing Arts Venue

    # Shopping
    "17000": "shopping",     # Retail (top-level)
    "17003": "shopping",     # Bookstore
    "17018": "shopping",     # Clothing Store
    "17069": "shopping",     # Shopping Mall
    "17114": "shopping",     # Market
    "17116": "shopping",     # Flea Market

    # Experience
    "12000": "experience",   # Community and Government (repurpose)
    "12063": "experience",   # Spiritual Center
    "12104": "experience",   # Convention Center
    "13235": "experience",   # Food Stand (street food = experience)

    # Nightlife
    "10032": "nightlife",    # (override) Nightclub mapped separately below
    "10043": "nightlife",    # Nightclub
    "13026": "nightlife",    # Cocktail Bar
    "10015": "nightlife",    # Concert Hall
    "10019": "nightlife",    # Jazz Club
    "10021": "nightlife",    # Karaoke

    # Group activity
    "18012": "group_activity",  # Bowling Alley
    "18013": "group_activity",  # Go Kart Track
    "18019": "group_activity",  # Laser Tag
    "18061": "group_activity",  # Escape Room
    "18009": "group_activity",  # Mini Golf

    # Wellness
    "11000": "wellness",     # Health and Medicine (top-level, default)
    "11049": "wellness",     # Spa
    "11051": "wellness",     # Yoga Studio
    "11047": "wellness",     # Massage Studio
    "18075": "wellness",     # Hot Spring
}

# For quick prefix matching: map 2-digit top-level prefixes as fallbacks
_TOP_LEVEL_FALLBACK: Dict[str, str] = {
    "10": "culture",         # Arts and Entertainment
    "11": "wellness",        # Health and Medicine
    "12": "experience",      # Community and Government
    "13": "dining",          # Dining and Drinking
    "14": "entertainment",   # Events
    "15": "experience",      # Business and Professional
    "16": "outdoors",        # Outdoors and Recreation
    "17": "shopping",        # Retail
    "18": "active",          # Sports and Recreation
    "19": "experience",      # Travel and Transportation
}


def map_foursquare_category(fsq_category_id: str) -> str:
    """
    Map a Foursquare category ID to one of our 11 ActivityCategory values.

    Resolution order:
    1. Exact match in FOURSQUARE_CATEGORY_MAP
    2. Top-level prefix fallback (first 2 digits)
    3. Default to 'experience'
    """
    if fsq_category_id in FOURSQUARE_CATEGORY_MAP:
        return FOURSQUARE_CATEGORY_MAP[fsq_category_id]

    prefix = fsq_category_id[:2] if len(fsq_category_id) >= 2 else ""
    if prefix in _TOP_LEVEL_FALLBACK:
        return _TOP_LEVEL_FALLBACK[prefix]

    return "experience"


# ---------------------------------------------------------------------------
# Foursquare Places API client
# ---------------------------------------------------------------------------
FOURSQUARE_API_BASE = "https://api.foursquare.com/v3/places"


class FoursquareScraper(BaseScraper):
    """
    Foursquare Places API v3 scraper.

    Searches venues by city (near=) and optional category, then maps
    results to ActivityNode-shaped dicts with Foursquare IDs and our
    coarse ActivityCategory enum values.
    """

    SOURCE_REGISTRY = SourceRegistry(
        name="foursquare",
        base_url=FOURSQUARE_API_BASE,
        authority_score=0.75,
        scrape_frequency_hours=168,  # weekly refresh
        requests_per_minute=30,
    )

    def __init__(
        self,
        *,
        near: str = "Austin, TX",
        categories: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 50,
    ):
        """
        Args:
            near: City/location string for Foursquare 'near' param.
            categories: Comma-separated Foursquare category IDs to filter.
            query: Free-text search term (e.g. "restaurants").
            limit: Max results per request (Foursquare max 50).
        """
        super().__init__()
        self.near = near
        self.categories = categories
        self.query = query
        self.limit = min(limit, 50)

        self.api_key = os.environ.get("FOURSQUARE_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "FOURSQUARE_API_KEY environment variable is required"
            )

        self._client = httpx.Client(timeout=30.0)
        self._stored_nodes: List[Dict[str, Any]] = []
        self._stored_signals: List[Dict[str, Any]] = []

    # -- BaseScraper interface -----------------------------------------------

    def scrape(self) -> List[Dict[str, Any]]:
        """
        Search Foursquare Places API and return raw venue results.

        Tracks daily quota and raises RuntimeError if exceeded.
        """
        _increment_quota(1)

        params: Dict[str, Any] = {
            "near": self.near,
            "limit": self.limit,
            "fields": ",".join([
                "fsq_id", "name", "geocodes", "location", "categories",
                "hours", "price", "tel", "website", "description", "photos",
            ]),
        }
        if self.query:
            params["query"] = self.query
        if self.categories:
            params["categories"] = self.categories

        url = f"{FOURSQUARE_API_BASE}/search?{urlencode(params)}"
        headers = {
            **self.get_headers(),
            "Authorization": self.api_key,
            "Accept": "application/json",
        }

        response = self._client.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()
        results = data.get("results", [])

        logger.info(
            f"Foursquare returned {len(results)} venues for "
            f"near={self.near!r} query={self.query!r}"
        )
        return results

    def parse(self, raw_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse a Foursquare venue into an ActivityNode-shaped dict.

        Returns None if critical fields (name, geocodes) are missing.
        """
        fsq_id = raw_item.get("fsq_id")
        name = raw_item.get("name")
        geocodes = raw_item.get("geocodes", {}).get("main", {})

        if not name or not geocodes:
            logger.warning(f"Skipping venue with missing name/geocodes: {fsq_id}")
            return None

        latitude = geocodes.get("latitude")
        longitude = geocodes.get("longitude")
        if latitude is None or longitude is None:
            logger.warning(f"Skipping venue with null lat/lng: {fsq_id}")
            return None

        # Category mapping — use first category, fall back to 'experience'
        fsq_categories = raw_item.get("categories", [])
        mapped_category = "experience"
        fsq_subcategory = None
        if fsq_categories:
            primary = fsq_categories[0]
            mapped_category = map_foursquare_category(str(primary.get("id", "")))
            fsq_subcategory = primary.get("name")

        # Location fields
        location = raw_item.get("location", {})
        city = location.get("locality") or location.get("region") or ""
        country = location.get("country", "")
        neighborhood = location.get("neighborhood")
        if isinstance(neighborhood, list):
            neighborhood = neighborhood[0] if neighborhood else None
        address = location.get("formatted_address")

        # Price level: Foursquare returns 1-4
        price = raw_item.get("price")
        price_level = None
        if price is not None:
            price_level = price if isinstance(price, int) else None

        # Hours
        hours_raw = raw_item.get("hours")
        hours_json = None
        if hours_raw:
            hours_json = hours_raw

        # Phone
        phone = raw_item.get("tel")

        # Website
        website = raw_item.get("website")

        # Description
        description = raw_item.get("description")

        # Primary photo
        primary_image_url = None
        photos = raw_item.get("photos", [])
        if photos:
            p = photos[0]
            prefix = p.get("prefix", "")
            suffix = p.get("suffix", "")
            if prefix and suffix:
                primary_image_url = f"{prefix}original{suffix}"

        # Canonical name for entity resolution
        canonical_name = name.strip().lower()

        # Slug
        slug_base = (
            canonical_name
            .replace(" ", "-")
            .replace("'", "")
            .replace('"', "")
            .replace("&", "and")
        )
        slug = f"{slug_base}-{fsq_id}" if fsq_id else slug_base

        node = {
            "name": name,
            "slug": slug,
            "canonicalName": canonical_name,
            "city": city,
            "country": country,
            "neighborhood": neighborhood,
            "latitude": latitude,
            "longitude": longitude,
            "category": mapped_category,
            "subcategory": fsq_subcategory,
            "priceLevel": price_level,
            "hours": hours_json,
            "address": address,
            "phoneNumber": phone,
            "websiteUrl": website,
            "foursquareId": fsq_id,
            "primaryImageUrl": primary_image_url,
            "imageSource": "foursquare" if primary_image_url else None,
            "descriptionShort": description[:200] if description else None,
            "descriptionLong": description,
            "sourceCount": 1,
            "status": "pending",
            "isCanonical": True,
            "lastScrapedAt": datetime.utcnow().isoformat(),
        }

        return node

    def store(self, parsed_item: Dict[str, Any]) -> None:
        """
        Accumulate parsed ActivityNode + QualitySignal for batch insert.

        Actual DB writes happen via get_results() — this class is a data
        producer, not a DB writer. The pipeline orchestrator handles persistence.
        """
        self._stored_nodes.append(parsed_item)

        # Create corresponding QualitySignal
        signal = {
            "activityNodeId": None,  # linked after DB insert by orchestrator
            "foursquareId": parsed_item.get("foursquareId"),
            "sourceName": "foursquare",
            "sourceUrl": (
                f"https://foursquare.com/v/{parsed_item['foursquareId']}"
                if parsed_item.get("foursquareId")
                else None
            ),
            "sourceAuthority": self.SOURCE_REGISTRY.authority_score,
            "signalType": "mention",
            "rawExcerpt": parsed_item.get("descriptionShort"),
            "extractedAt": datetime.utcnow().isoformat(),
        }
        self._stored_signals.append(signal)

    # -- Public helpers ------------------------------------------------------

    def get_results(self) -> Dict[str, Any]:
        """
        Return collected ActivityNode rows and QualitySignals.

        Returns:
            {
                "nodes": List of ActivityNode-shaped dicts,
                "quality_signals": List of QualitySignal-shaped dicts,
                "stats": run() stats dict
            }
        """
        return {
            "nodes": list(self._stored_nodes),
            "quality_signals": list(self._stored_signals),
        }

    def search_city(
        self,
        city: str,
        query: Optional[str] = None,
        categories: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Convenience method: search a city and return structured results.

        Args:
            city: City name (e.g. "Austin, TX")
            query: Optional search term (e.g. "restaurants")
            categories: Optional Foursquare category IDs

        Returns:
            Dict with nodes, quality_signals, and stats.
        """
        self.near = city
        if query is not None:
            self.query = query
        if categories is not None:
            self.categories = categories

        # Reset accumulators
        self._stored_nodes = []
        self._stored_signals = []

        stats = self.run()

        results = self.get_results()
        results["stats"] = stats
        return results
