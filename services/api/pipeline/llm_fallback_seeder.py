"""
LLM fallback seeder -- creates ActivityNodes from unlinked QualitySignals.

Production path for cities without hardcoded venue lists. Uses Claude Haiku
to extract structured venue data from scraped blog/RSS signal excerpts,
optionally geocodes via Google Places, creates ActivityNodes, and relinks
the original QualitySignals.

Pipeline steps:
  1. Fetch unlinked signals (sentinel activityNodeId)
  1a. Persist raw signals to GCS (gs://overplanned-raw/raw_places/{city}.jsonl)
  2. LLM extraction: signal excerpts -> venue name, category, neighborhood
  3. Dedup extracted venues by slug
  4. Optional Google Places geocoding (degrades gracefully)
  4a. Persist geocoded venues to GCS (gs://overplanned-raw/geocoded_venues/{city}.jsonl)
  5. ActivityNode creation (ON CONFLICT DO NOTHING for idempotency)
  6. Signal relinking (transactional: update activityNodeId from sentinel -> real)
  7. ModelRegistry audit log

Usage:
    pool = await asyncpg.create_pool(DATABASE_URL)
    stats = await run_llm_fallback(pool, city_slug="bend", api_key=api_key)

CLI:
    python3 -m services.api.pipeline.llm_fallback_seeder bend
"""

import asyncio
import hashlib
import json
import logging
import math
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg
import httpx

from services.api.pipeline.city_configs import (
    get_city_config,
    get_all_stopwords,
    CityConfig,
    CITY_CONFIGS,
)
from services.api.pipeline.gcs_raw_store import (
    write_raw_signals_to_gcs,
    write_geocoded_venues_to_gcs,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SENTINEL_NODE_ID = "00000000-0000-0000-0000-000000000000"

MODEL_NAME = "claude-haiku-4-5-20251001"
PROMPT_VERSION = "fallback-extract-v1"
BATCH_SIZE = 5  # signals per LLM call (excerpts can be long)
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0

# Haiku pricing (per 1M tokens, Feb 2026)
INPUT_COST_PER_1M = 0.80
OUTPUT_COST_PER_1M = 4.00

# Valid ActivityCategory enum values from Prisma schema
VALID_CATEGORIES = frozenset({
    "dining", "drinks", "culture", "outdoors", "active",
    "entertainment", "shopping", "experience", "nightlife",
    "group_activity", "wellness",
})

# Non-retryable error patterns -- abort entire run immediately
_NON_RETRYABLE_PATTERNS = frozenset({
    "credit balance is too low",
    "invalid x-api-key",
    "invalid api key",
    "account has been disabled",
    "permission denied",
})


class NonRetryableAPIError(Exception):
    """Raised when the API returns an error that won't resolve with retries."""
    pass


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ExtractedVenue:
    """A single venue extracted from a QualitySignal by the LLM."""
    name: str
    category: str  # must be a valid ActivityCategory
    neighborhood: Optional[str] = None
    description: Optional[str] = None
    price_level: Optional[int] = None  # 1-4
    # Set after geocoding
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: Optional[str] = None
    google_place_id: Optional[str] = None


@dataclass
class SignalVenueLink:
    """Maps a QualitySignal to an extracted venue (by slug)."""
    signal_id: str
    venue_slug: str


@dataclass
class FallbackStats:
    """Aggregated stats for a fallback seeder run."""
    signals_fetched: int = 0
    signals_processed: int = 0
    venues_extracted: int = 0
    venues_created: int = 0
    venues_existing: int = 0
    signals_relinked: int = 0
    geocode_success: int = 0
    geocode_skipped: int = 0
    gcs_raw_written: int = 0
    gcs_geocoded_written: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    latency_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


@dataclass
class GeocodeBackfillStats:
    """Aggregated stats for a geocode backfill run."""
    nodes_found: int = 0
    nodes_geocoded: int = 0
    nodes_failed: int = 0
    nodes_skipped: int = 0
    latency_seconds: float = 0.0


@dataclass
class BusinessStatusStats:
    """Aggregated stats for a business status check run."""
    nodes_checked: int = 0
    nodes_closed: int = 0
    nodes_temp_closed: int = 0
    nodes_not_found: int = 0
    nodes_operational: int = 0
    nodes_failed: int = 0
    latency_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Geocode result validation
# ---------------------------------------------------------------------------

def _validate_geocode_result(
    lat: Any, lng: Any, place_id: Any, address: Any,
) -> bool:
    """Validate geocode response fields before storing in DB."""
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return False
    if math.isnan(lat) or math.isnan(lng) or math.isinf(lat) or math.isinf(lng):
        return False
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return False
    if place_id is not None and (not isinstance(place_id, str) or len(place_id) > 200):
        return False
    if address is not None and len(str(address)) > 500:
        return False
    return True


def _compute_content_hash(name: str, lat: float, lng: float, category: str) -> str:
    """SHA-256 hash matching entity_resolution.compute_content_hash."""
    normalized = re.sub(r"\s+", " ", name.lower().strip())
    payload = f"{normalized}|{lat:.4f}|{lng:.4f}|{category}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------

def make_slug(name: str, city: str) -> str:
    """Generate a URL-safe slug from venue name and city."""
    raw = f"{name}-{city}".lower()
    # Replace non-alphanumeric (except hyphens) with hyphens
    slug = re.sub(r"[^a-z0-9-]", "-", raw)
    # Collapse multiple hyphens
    slug = re.sub(r"-+", "-", slug)
    # Strip leading/trailing hyphens
    return slug.strip("-")


# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a venue extraction system for a travel planning app.
You receive raw text excerpts from blog posts and Reddit about a specific city.
Your job is to extract INDIVIDUAL VENUES that a traveler could physically visit.

RULES:
- Extract only specific, named venues (restaurants, bars, parks, museums, shops, etc.)
- A venue MUST be a place someone can go to — a physical location with a name
- Do NOT extract: people, events, organizations, schools, government agencies, neighborhoods, or chain restaurants
- Do NOT extract if the text is general city discussion, news, politics, or personal stories without venue recommendations
- For each venue, provide: name, category, neighborhood (if mentioned), short description
- Category must be one of: dining, drinks, culture, outdoors, active, entertainment, shopping, experience, nightlife, group_activity, wellness
- Price level (1-4): 1=budget, 2=moderate, 3=upscale, 4=luxury. Omit if unclear.
- Output ONLY a JSON object with a "venues" array -- no prose, no markdown
- If no specific venues can be extracted, return {"venues": []}
- When in doubt, return fewer venues. Quality over quantity.

Example output:
{"venues": [
  {"name": "Pine Tavern", "category": "dining", "neighborhood": "Downtown Bend", "description": "Riverside dining with a tree growing through the floor", "price_level": 2},
  {"name": "Deschutes Brewery", "category": "drinks", "neighborhood": "Downtown Bend", "description": "Flagship brewpub of the iconic Oregon craft brewery", "price_level": 2}
]}"""


def _build_user_prompt(city_name: str, excerpts: list[dict[str, str]]) -> str:
    """Build user message for a batch of signal excerpts from one city."""
    parts = [f"City: {city_name}", "", "Extract venues from these excerpts:", ""]

    for i, exc in enumerate(excerpts, 1):
        source = exc.get("source_name", "unknown")
        text = exc.get("raw_excerpt", "")
        # Truncate long excerpts to control token usage
        if len(text) > 1500:
            text = text[:1497] + "..."
        parts.append(f"--- Excerpt {i} (source: {source}) ---")
        parts.append(text)
        parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------

async def _call_haiku_extract(
    client: httpx.AsyncClient,
    api_key: str,
    city_name: str,
    excerpts: list[dict[str, str]],
) -> tuple[list[dict], int, int]:
    """
    Call Haiku to extract venues from signal excerpts.

    Returns (venue_dicts, input_tokens, output_tokens).
    """
    user_prompt = _build_user_prompt(city_name, excerpts)

    payload = {
        "model": MODEL_NAME,
        "max_tokens": 1024,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    resp = await client.post(
        "https://api.anthropic.com/v1/messages",
        json=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    body = resp.json()

    input_tokens = body.get("usage", {}).get("input_tokens", 0)
    output_tokens = body.get("usage", {}).get("output_tokens", 0)

    # Extract text
    text = ""
    for block in body.get("content", []):
        if block.get("type") == "text":
            text += block["text"]

    venues = _parse_extraction_response(text)
    return venues, input_tokens, output_tokens


def _parse_extraction_response(text: str) -> list[dict]:
    """
    Parse LLM response text into a list of venue dicts.

    Returns [] on parse failure. Tolerates markdown code fences.
    """
    text = text.strip()

    def _extract(data: Any) -> list[dict]:
        if isinstance(data, dict):
            venues = data.get("venues", [])
            if isinstance(venues, list):
                return venues
        if isinstance(data, list):
            return data
        return []

    # Direct JSON parse
    try:
        return _extract(json.loads(text))
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code blocks
    if "```" in text:
        for block in text.split("```"):
            block = block.strip()
            if block.startswith("json"):
                block = block[4:].strip()
            try:
                return _extract(json.loads(block))
            except json.JSONDecodeError:
                continue

    logger.error("Failed to parse LLM extraction response: %s", text[:200])
    return []


# ---------------------------------------------------------------------------
# Venue validation + dedup
# ---------------------------------------------------------------------------

def _validate_venue(raw: dict, stopwords: set[str]) -> Optional[ExtractedVenue]:
    """Validate and coerce a raw venue dict from LLM into ExtractedVenue."""
    name = (raw.get("name") or "").strip()
    if not name:
        return None

    # Stopword check
    if name.lower() in stopwords:
        logger.debug("Filtered stopword venue: %s", name)
        return None

    # Category validation
    category = (raw.get("category") or "").strip().lower()
    if category not in VALID_CATEGORIES:
        # Attempt common mappings
        cat_map = {
            "food": "dining",
            "restaurant": "dining",
            "bar": "drinks",
            "pub": "drinks",
            "brewery": "drinks",
            "museum": "culture",
            "art": "culture",
            "gallery": "culture",
            "park": "outdoors",
            "hiking": "outdoors",
            "nature": "outdoors",
            "sport": "active",
            "sports": "active",
            "fitness": "active",
            "theater": "entertainment",
            "theatre": "entertainment",
            "cinema": "entertainment",
            "music": "entertainment",
            "shop": "shopping",
            "market": "shopping",
            "store": "shopping",
            "spa": "wellness",
            "yoga": "wellness",
            "club": "nightlife",
            "lounge": "nightlife",
            "tour": "experience",
            "activity": "group_activity",
        }
        category = cat_map.get(category, "")
        if category not in VALID_CATEGORIES:
            logger.debug("Invalid category for venue %s: %s", name, raw.get("category"))
            return None

    # Price level
    price_level = raw.get("price_level")
    if price_level is not None:
        try:
            price_level = max(1, min(4, int(price_level)))
        except (ValueError, TypeError):
            price_level = None

    neighborhood = (raw.get("neighborhood") or "").strip() or None
    description = (raw.get("description") or "").strip() or None

    return ExtractedVenue(
        name=name,
        category=category,
        neighborhood=neighborhood,
        description=description,
        price_level=price_level,
    )


def _dedup_venues(
    venues: list[ExtractedVenue],
    city_slug: str,
) -> dict[str, ExtractedVenue]:
    """
    Deduplicate extracted venues by slug.

    Returns slug -> ExtractedVenue mapping. Later extractions with more
    data (description, neighborhood) win over earlier sparse ones.
    """
    seen: dict[str, ExtractedVenue] = {}
    for v in venues:
        slug = make_slug(v.name, city_slug)
        existing = seen.get(slug)
        if existing is None:
            seen[slug] = v
        else:
            # Merge: keep the richer entry
            if v.description and not existing.description:
                existing.description = v.description
            if v.neighborhood and not existing.neighborhood:
                existing.neighborhood = v.neighborhood
            if v.price_level and not existing.price_level:
                existing.price_level = v.price_level
    return seen


# ---------------------------------------------------------------------------
# Google Places geocoding (optional)
# ---------------------------------------------------------------------------

async def _geocode_venues(
    client: httpx.AsyncClient,
    venues: dict[str, ExtractedVenue],
    city_name: str,
    api_key: Optional[str],
    stats: FallbackStats,
) -> None:
    """
    Geocode venues via Google Places Text Search. Modifies venues in-place.

    Degrades gracefully: if no API key, skips all geocoding.
    """
    if not api_key:
        stats.geocode_skipped = len(venues)
        logger.info("No Google Places API key -- skipping geocoding for %d venues", len(venues))
        return

    for slug, venue in venues.items():
        try:
            query = f"{venue.name}, {city_name}"
            resp = await client.post(
                "https://places.googleapis.com/v1/places:searchText",
                headers={
                    "X-Goog-Api-Key": api_key,
                    "X-Goog-FieldMask": "places.id,places.location,places.formattedAddress",
                    "Content-Type": "application/json",
                },
                json={"textQuery": query},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            places = data.get("places", [])

            if places:
                place = places[0]
                loc = place.get("location", {})
                venue.latitude = loc.get("latitude")
                venue.longitude = loc.get("longitude")
                venue.address = place.get("formattedAddress")
                venue.google_place_id = place.get("id")
                stats.geocode_success += 1
            else:
                stats.geocode_skipped += 1

        except Exception as exc:
            stats.geocode_skipped += 1
            logger.debug("Geocode failed for %s: %s", venue.name, exc)


# ---------------------------------------------------------------------------
# Geocode backfill (post-creation, updates existing nodes)
# ---------------------------------------------------------------------------

GEOCODE_RETRY_MAX = 3
GEOCODE_RETRY_BACKOFF = 2.0
GEOCODE_INTER_REQUEST_DELAY = 0.15  # ~6.6 QPS


async def geocode_backfill(
    pool: asyncpg.Pool,
    city_slug: str,
    *,
    google_places_key: Optional[str] = None,  # production reads from env var
    limit: int = 100,
) -> GeocodeBackfillStats:
    """
    Geocode ActivityNodes stuck at city bbox center coordinates.

    Finds nodes within 200m of the city's bbox center that have no
    googlePlaceId, calls Google Places Text Search for real lat/lng,
    and updates the nodes in-place (including contentHash recomputation).

    Args:
        pool: asyncpg connection pool
        city_slug: City slug matching CITY_CONFIGS key
        google_places_key: Google Places API key (falls back to
            GOOGLE_PLACES_API_KEY env var)
        limit: max nodes to geocode per run (cost control)

    Returns:
        GeocodeBackfillStats with run metrics
    """
    t0 = time.monotonic()
    google_places_key = google_places_key or os.environ.get("GOOGLE_PLACES_API_KEY")
    stats = GeocodeBackfillStats()

    city_config = get_city_config(city_slug)
    center_lat = (city_config.bbox.lat_min + city_config.bbox.lat_max) / 2
    center_lng = (city_config.bbox.lng_min + city_config.bbox.lng_max) / 2

    if not google_places_key:
        # Count how many nodes would need geocoding
        count = await pool.fetchval(
            """
            SELECT COUNT(*) FROM activity_nodes
            WHERE city = $1
              AND "googlePlaceId" IS NULL
              AND ST_Distance(
                  ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography,
                  ST_SetSRID(ST_MakePoint($2, $3), 4326)::geography
              ) < 200
            """,
            city_config.name, center_lng, center_lat,
        )
        stats.nodes_found = count or 0
        stats.nodes_skipped = stats.nodes_found
        logger.info(
            "No Google Places API key -- skipping geocode backfill for %d nodes in %s",
            stats.nodes_found, city_slug,
        )
        stats.latency_seconds = round(time.monotonic() - t0, 2)
        return stats

    # Find nodes at bbox center needing geocoding
    nodes = await pool.fetch(
        """
        SELECT id, name, "canonicalName", category, latitude, longitude
        FROM activity_nodes
        WHERE city = $1
          AND "googlePlaceId" IS NULL
          AND ST_Distance(
              ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography,
              ST_SetSRID(ST_MakePoint($2, $3), 4326)::geography
          ) < 200
        ORDER BY name
        LIMIT $4
        """,
        city_config.name, center_lng, center_lat, limit,
    )

    stats.nodes_found = len(nodes)
    if not nodes:
        logger.info("No ungeocoded nodes at bbox center for %s", city_slug)
        stats.latency_seconds = round(time.monotonic() - t0, 2)
        return stats

    logger.info("Found %d nodes at bbox center for %s, geocoding...", len(nodes), city_slug)

    async with httpx.AsyncClient() as client:
        for node in nodes:
            node_id = node["id"]
            node_name = node["name"]
            category = node["category"]

            try:
                lat, lng, address, place_id = await _geocode_single_node(
                    client, google_places_key, node_name, city_config,
                )

                if lat is not None:
                    # Recompute content hash with new coordinates
                    canonical = node["canonicalName"] or node_name.lower()
                    content_hash = _compute_content_hash(canonical, lat, lng, category)

                    await pool.execute(
                        """
                        UPDATE activity_nodes
                        SET latitude = $1, longitude = $2, address = $3,
                            "googlePlaceId" = $4, "contentHash" = $5,
                            "updatedAt" = $6
                        WHERE id = $7
                        """,
                        lat, lng, address, place_id, content_hash,
                        datetime.now(timezone.utc).replace(tzinfo=None),
                        node_id,
                    )
                    stats.nodes_geocoded += 1
                    logger.debug("Geocoded %s -> (%.4f, %.4f)", node_name, lat, lng)
                else:
                    stats.nodes_skipped += 1

            except Exception as exc:
                stats.nodes_failed += 1
                logger.warning("Geocode failed for %s: %s", node_name, exc)

            # Rate limit: ~6.6 QPS
            await asyncio.sleep(GEOCODE_INTER_REQUEST_DELAY)

    stats.latency_seconds = round(time.monotonic() - t0, 2)
    logger.info(
        "Geocode backfill %s: found=%d geocoded=%d skipped=%d failed=%d (%.1fs)",
        city_slug, stats.nodes_found, stats.nodes_geocoded,
        stats.nodes_skipped, stats.nodes_failed, stats.latency_seconds,
    )
    return stats


# ---------------------------------------------------------------------------
# Business status check
# ---------------------------------------------------------------------------

BUSINESS_STATUS_DELAY = 0.15  # ~6.6 QPS (Place Details is cheaper but same rate)
BUSINESS_STATUS_LIMIT = 200
BUSINESS_STATUS_STALE_DAYS = 30


async def check_business_status(
    pool: asyncpg.Pool,
    city_slug: str,
    *,
    google_places_key: Optional[str] = None,
    limit: int = BUSINESS_STATUS_LIMIT,
) -> BusinessStatusStats:
    """
    Check Google Places business status for geocoded ActivityNodes.

    Queries nodes with a googlePlaceId that haven't been validated recently
    (or ever), calls the Place Details API for businessStatus, and flags
    permanently closed venues.

    Args:
        pool: asyncpg connection pool
        city_slug: City slug matching CITY_CONFIGS key
        google_places_key: Google Places API key (falls back to env var)
        limit: max nodes to check per run (cost control)

    Returns:
        BusinessStatusStats with run metrics
    """
    t0 = time.monotonic()
    google_places_key = google_places_key or os.environ.get("GOOGLE_PLACES_API_KEY")
    stats = BusinessStatusStats()

    city_config = get_city_config(city_slug)

    if not google_places_key:
        logger.info(
            "No Google Places API key -- skipping business status check for %s",
            city_slug,
        )
        stats.latency_seconds = round(time.monotonic() - t0, 2)
        return stats

    # Find nodes with googlePlaceId that need validation
    # Check all non-flagged nodes: stale (>30 days) or never validated
    nodes = await pool.fetch(
        """
        SELECT id, name, "googlePlaceId"
        FROM activity_nodes
        WHERE city = $1
          AND "googlePlaceId" IS NOT NULL
          AND status != 'flagged'
          AND (
            "lastValidatedAt" IS NULL
            OR "lastValidatedAt" < NOW() - INTERVAL '30 days'
          )
        ORDER BY "lastValidatedAt" NULLS FIRST
        LIMIT $2
        """,
        city_config.name, limit,
    )

    if not nodes:
        logger.info("No nodes need business status check for %s", city_slug)
        stats.latency_seconds = round(time.monotonic() - t0, 2)
        return stats

    logger.info(
        "Checking business status for %d nodes in %s...", len(nodes), city_slug,
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    async with httpx.AsyncClient() as client:
        for node in nodes:
            node_id = node["id"]
            node_name = node["name"]
            place_id = node["googlePlaceId"]
            stats.nodes_checked += 1

            try:
                resp = await client.get(
                    f"https://places.googleapis.com/v1/places/{place_id}",
                    headers={
                        "X-Goog-Api-Key": google_places_key,
                        "X-Goog-FieldMask": "id,businessStatus",
                    },
                    timeout=10.0,
                )

                if resp.status_code == 404:
                    # Place no longer exists in Google's database
                    await pool.execute(
                        """
                        UPDATE activity_nodes
                        SET status = 'flagged',
                            "flagReason" = 'place_not_found',
                            "lastValidatedAt" = $1,
                            "updatedAt" = $1
                        WHERE id = $2
                        """,
                        now, node_id,
                    )
                    stats.nodes_not_found += 1
                    logger.info("Place not found: %s (%s)", node_name, place_id)

                elif resp.status_code >= 400:
                    # Unexpected error — don't flag, just count
                    stats.nodes_failed += 1
                    logger.warning(
                        "API error %d for %s (%s)",
                        resp.status_code, node_name, place_id,
                    )

                else:
                    data = resp.json()
                    business_status = data.get("businessStatus", "OPERATIONAL")

                    if business_status == "CLOSED_PERMANENTLY":
                        await pool.execute(
                            """
                            UPDATE activity_nodes
                            SET status = 'flagged',
                                "flagReason" = 'permanently_closed',
                                "lastValidatedAt" = $1,
                                "updatedAt" = $1
                            WHERE id = $2
                            """,
                            now, node_id,
                        )
                        stats.nodes_closed += 1
                        logger.info(
                            "Permanently closed: %s (%s)", node_name, place_id,
                        )

                    elif business_status == "CLOSED_TEMPORARILY":
                        await pool.execute(
                            """
                            UPDATE activity_nodes
                            SET "lastValidatedAt" = $1,
                                "updatedAt" = $1
                            WHERE id = $2
                            """,
                            now, node_id,
                        )
                        stats.nodes_temp_closed += 1
                        logger.debug(
                            "Temporarily closed: %s (%s)", node_name, place_id,
                        )

                    else:
                        # OPERATIONAL or unknown status — just stamp
                        await pool.execute(
                            """
                            UPDATE activity_nodes
                            SET "lastValidatedAt" = $1,
                                "updatedAt" = $1
                            WHERE id = $2
                            """,
                            now, node_id,
                        )
                        stats.nodes_operational += 1

            except Exception as exc:
                stats.nodes_failed += 1
                logger.warning(
                    "Business status check failed for %s: %s", node_name, exc,
                )

            # Rate limit
            await asyncio.sleep(BUSINESS_STATUS_DELAY)

    stats.latency_seconds = round(time.monotonic() - t0, 2)
    logger.info(
        "Business status %s: checked=%d operational=%d closed=%d "
        "temp_closed=%d not_found=%d failed=%d (%.1fs)",
        city_slug, stats.nodes_checked, stats.nodes_operational,
        stats.nodes_closed, stats.nodes_temp_closed,
        stats.nodes_not_found, stats.nodes_failed, stats.latency_seconds,
    )
    return stats


async def _geocode_single_node(
    client: httpx.AsyncClient,
    api_key: str,
    venue_name: str,
    city_config: CityConfig,
) -> tuple[Optional[float], Optional[float], Optional[str], Optional[str]]:
    """
    Geocode a single venue via Google Places Text Search.

    Returns (lat, lng, address, place_id) or (None, None, None, None) on failure.
    Includes bbox validation and response sanitization.
    """
    query = f"{venue_name}, {city_config.name}"

    for attempt in range(GEOCODE_RETRY_MAX):
        try:
            resp = await client.post(
                "https://places.googleapis.com/v1/places:searchText",
                headers={
                    "X-Goog-Api-Key": api_key,
                    "X-Goog-FieldMask": "places.id,places.location,places.formattedAddress",
                    "Content-Type": "application/json",
                },
                json={"textQuery": query},
                timeout=10.0,
            )

            if resp.status_code == 429 or resp.status_code >= 500:
                wait = GEOCODE_RETRY_BACKOFF ** (attempt + 1)
                logger.warning(
                    "Google Places %d for %s, retry %d/%d in %.1fs",
                    resp.status_code, venue_name, attempt + 1, GEOCODE_RETRY_MAX, wait,
                )
                await asyncio.sleep(wait)
                continue

            resp.raise_for_status()
            data = resp.json()
            places = data.get("places", [])

            if not places:
                logger.debug("No Places result for %s", venue_name)
                return None, None, None, None

            place = places[0]
            loc = place.get("location", {})
            lat = loc.get("latitude")
            lng = loc.get("longitude")
            place_id = place.get("id")
            address = place.get("formattedAddress")

            # Validate response data
            if not _validate_geocode_result(lat, lng, place_id, address):
                logger.warning("Invalid geocode data for %s: lat=%s lng=%s", venue_name, lat, lng)
                return None, None, None, None

            # Bbox validation: reject results outside city bounds
            if not city_config.bbox.contains(lat, lng):
                logger.info(
                    "Geocode result outside bbox for %s (%.4f, %.4f) -- keeping fallback coords",
                    venue_name, lat, lng,
                )
                return None, None, None, None

            # Truncate address if needed
            if address and len(address) > 500:
                address = address[:500]

            return lat, lng, address, place_id

        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500 and exc.response.status_code != 429:
                # 4xx (non-429): skip immediately, don't retry
                logger.debug("Google Places %d for %s, skipping", exc.response.status_code, venue_name)
                return None, None, None, None
            if attempt < GEOCODE_RETRY_MAX - 1:
                wait = GEOCODE_RETRY_BACKOFF ** (attempt + 1)
                await asyncio.sleep(wait)
                continue
            return None, None, None, None

        except Exception as exc:
            if attempt < GEOCODE_RETRY_MAX - 1:
                wait = GEOCODE_RETRY_BACKOFF ** (attempt + 1)
                logger.debug("Geocode error for %s, retry %d: %s", venue_name, attempt + 1, exc)
                await asyncio.sleep(wait)
                continue
            return None, None, None, None

    return None, None, None, None


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------

async def _fetch_unlinked_signals(
    pool: asyncpg.Pool,
    city_name: str,
    limit: int = 200,
) -> list[dict]:
    """
    Fetch QualitySignals with sentinel activityNodeId for a given city.

    Returns list of dicts with signal metadata.
    """
    rows = await pool.fetch(
        """
        SELECT qs.id, qs."sourceName", qs."sourceUrl", qs."sourceAuthority",
               qs."signalType", qs."rawExcerpt", qs."extractedAt"
        FROM quality_signals qs
        LEFT JOIN activity_nodes an ON qs."activityNodeId" = an.id
        WHERE qs."activityNodeId" = $1
          AND qs."rawExcerpt" IS NOT NULL
          AND (
            -- Match signals whose source content mentions this city
            qs."rawExcerpt" ILIKE '%' || $3 || '%'
            OR qs."sourceName" ILIKE '%' || $3 || '%'
          )
        ORDER BY qs."sourceAuthority" DESC, qs."extractedAt" DESC
        LIMIT $2
        """,
        SENTINEL_NODE_ID,
        limit,
        city_name,
    )

    signals = []
    for row in rows:
        signals.append({
            "id": row["id"],
            "source_name": row["sourceName"],
            "source_url": row["sourceUrl"],
            "source_authority": row["sourceAuthority"],
            "signal_type": row["signalType"],
            "raw_excerpt": row["rawExcerpt"],
        })
    return signals


async def _create_activity_nodes(
    pool: asyncpg.Pool,
    venues: dict[str, ExtractedVenue],
    city_config: CityConfig,
    stats: FallbackStats,
) -> dict[str, str]:
    """
    Create ActivityNodes from extracted venues. Idempotent via ON CONFLICT.

    Returns slug -> node_id mapping (includes both new and existing nodes).
    """
    slug_to_id: dict[str, str] = {}
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    async with pool.acquire() as conn:
        for slug, venue in venues.items():
            node_id = str(uuid.uuid4())

            # Use city bbox center as fallback when ungeocoded.
            # Entity resolution skips geocode_proximity for nodes at
            # exact city center to prevent over-merging.
            lat = venue.latitude
            lng = venue.longitude
            if lat is None or lng is None:
                lat = (city_config.bbox.lat_min + city_config.bbox.lat_max) / 2
                lng = (city_config.bbox.lng_min + city_config.bbox.lng_max) / 2

            result = await conn.execute(
                """
                INSERT INTO activity_nodes (
                    "id", "name", "slug", "canonicalName",
                    "city", "country", "neighborhood",
                    "latitude", "longitude",
                    "category", "priceLevel",
                    "sourceCount", "convergenceScore", "authorityScore",
                    "descriptionShort",
                    "googlePlaceId", "address",
                    "status", "isCanonical",
                    "lastScrapedAt",
                    "createdAt", "updatedAt"
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                    $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $21
                )
                ON CONFLICT ("slug") DO NOTHING
                """,
                node_id,
                venue.name,
                slug,
                venue.name.lower(),
                city_config.slug,
                city_config.country,
                venue.neighborhood,
                lat,
                lng,
                venue.category,
                venue.price_level,
                1,   # sourceCount
                0.0,  # convergenceScore (scored later)
                0.0,  # authorityScore (scored later)
                venue.description,
                venue.google_place_id,
                venue.address,
                "pending",
                True,
                now,
                now,
            )

            if result == "INSERT 0 1":
                slug_to_id[slug] = node_id
                stats.venues_created += 1
            else:
                # Node already exists -- fetch its ID for relinking
                existing = await conn.fetchval(
                    'SELECT id FROM activity_nodes WHERE "slug" = $1',
                    slug,
                )
                if existing:
                    slug_to_id[slug] = existing
                stats.venues_existing += 1

    return slug_to_id


async def _relink_signals(
    pool: asyncpg.Pool,
    links: list[SignalVenueLink],
    slug_to_id: dict[str, str],
    stats: FallbackStats,
) -> None:
    """
    Update QualitySignals to point to real ActivityNode IDs.

    Transactional: all relinks succeed or none do.
    """
    relink_pairs: list[tuple[str, str]] = []  # (signal_id, node_id)

    for link in links:
        node_id = slug_to_id.get(link.venue_slug)
        if node_id:
            relink_pairs.append((link.signal_id, node_id))

    if not relink_pairs:
        return

    async with pool.acquire() as conn:
        async with conn.transaction():
            for signal_id, node_id in relink_pairs:
                result = await conn.execute(
                    """
                    UPDATE quality_signals
                    SET "activityNodeId" = $1
                    WHERE id = $2
                      AND "activityNodeId" = $3
                    """,
                    node_id,
                    signal_id,
                    SENTINEL_NODE_ID,
                )
                # result is "UPDATE N" — only count actual updates
                if result and result.endswith("1"):
                    stats.signals_relinked += 1


async def _log_to_model_registry(
    pool: asyncpg.Pool,
    stats: FallbackStats,
    city_slug: str,
) -> str:
    """Log fallback extraction batch to ModelRegistry. Returns entry ID."""
    entry_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    await pool.execute(
        """
        INSERT INTO model_registry (
            id, "modelName", "modelVersion", stage, "modelType",
            description, "configSnapshot", metrics, "evaluatedAt",
            "createdAt", "updatedAt"
        ) VALUES ($1, $2, $3, 'production', 'llm_fallback_extraction',
                  $4, $5, $6, $7, $8, $8)
        ON CONFLICT ("modelName", "modelVersion") DO UPDATE
          SET metrics = EXCLUDED.metrics,
              description = EXCLUDED.description,
              "evaluatedAt" = EXCLUDED."evaluatedAt",
              "updatedAt" = EXCLUDED."updatedAt"
        """,
        entry_id,
        MODEL_NAME,
        PROMPT_VERSION,
        f"Fallback extraction for {city_slug}: {stats.venues_created} nodes created, "
        f"{stats.signals_relinked} signals relinked",
        json.dumps({
            "model": MODEL_NAME,
            "prompt_version": PROMPT_VERSION,
            "city": city_slug,
            "batch_size": BATCH_SIZE,
        }),
        json.dumps({
            "signals_fetched": stats.signals_fetched,
            "signals_processed": stats.signals_processed,
            "venues_extracted": stats.venues_extracted,
            "venues_created": stats.venues_created,
            "venues_existing": stats.venues_existing,
            "signals_relinked": stats.signals_relinked,
            "geocode_success": stats.geocode_success,
            "geocode_skipped": stats.geocode_skipped,
            "gcs_raw_written": stats.gcs_raw_written,
            "gcs_geocoded_written": stats.gcs_geocoded_written,
            "total_input_tokens": stats.total_input_tokens,
            "total_output_tokens": stats.total_output_tokens,
            "estimated_cost_usd": round(stats.estimated_cost_usd, 6),
            "latency_seconds": round(stats.latency_seconds, 2),
            "errors": stats.errors[:20],
        }),
        now,
        now,
    )
    return entry_id


# ---------------------------------------------------------------------------
# Core extraction pipeline
# ---------------------------------------------------------------------------

async def _extract_batch(
    client: httpx.AsyncClient,
    api_key: str,
    city_name: str,
    signals: list[dict],
    stopwords: set[str],
    city_slug: str,
    stats: FallbackStats,
) -> tuple[list[ExtractedVenue], list[SignalVenueLink]]:
    """
    Send a batch of signals to Haiku for venue extraction.

    Returns (extracted_venues, signal_venue_links).
    """
    excerpts = [
        {"source_name": s["source_name"], "raw_excerpt": s["raw_excerpt"]}
        for s in signals
    ]

    for attempt in range(MAX_RETRIES):
        try:
            raw_venues, in_tok, out_tok = await _call_haiku_extract(
                client, api_key, city_name, excerpts,
            )
            stats.total_input_tokens += in_tok
            stats.total_output_tokens += out_tok
            stats.signals_processed += len(signals)
            break
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            # Check non-retryable
            body_lower = exc.response.text.lower()
            if any(p in body_lower for p in _NON_RETRYABLE_PATTERNS):
                msg = f"Non-retryable API error: {exc.response.text[:200]}"
                logger.error(msg)
                raise NonRetryableAPIError(msg) from exc

            if status == 429 or status >= 500:
                wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                logger.warning(
                    "Haiku API %d, retry %d/%d in %.1fs",
                    status, attempt + 1, MAX_RETRIES, wait,
                )
                await asyncio.sleep(wait)
                continue

            msg = f"HTTP {status}: {exc.response.text[:200]}"
            stats.errors.append(msg)
            logger.error(msg)
            return [], []

        except Exception as exc:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                logger.warning("Extraction error, retry %d/%d: %s", attempt + 1, MAX_RETRIES, exc)
                await asyncio.sleep(wait)
                continue
            msg = f"Failed after {MAX_RETRIES} retries: {exc}"
            stats.errors.append(msg)
            logger.error(msg)
            return [], []
    else:
        return [], []

    # Validate extracted venues
    all_venues: list[ExtractedVenue] = []
    for raw in raw_venues:
        venue = _validate_venue(raw, stopwords)
        if venue:
            all_venues.append(venue)

    # Build signal-to-venue links
    # Each signal in the batch gets linked to ALL venues extracted from the batch.
    # This is a simplification -- in practice, entity resolution downstream
    # will refine these links.
    links: list[SignalVenueLink] = []
    for signal in signals:
        for venue in all_venues:
            slug = make_slug(venue.name, city_slug)
            # Only link if the venue name appears in the signal excerpt
            if venue.name.lower() in signal["raw_excerpt"].lower():
                links.append(SignalVenueLink(
                    signal_id=signal["id"],
                    venue_slug=slug,
                ))

    stats.venues_extracted += len(all_venues)
    return all_venues, links


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_llm_fallback(
    pool: asyncpg.Pool,
    city_slug: str,
    *,
    api_key: Optional[str] = None,
    google_places_key: Optional[str] = None,
    gcs_bucket: str = "overplanned-raw",
    limit: int = 200,
    skip_geocode: bool = False,
) -> FallbackStats:
    """
    Main entry point: extract venues from unlinked signals and create nodes.

    Args:
        pool: asyncpg connection pool
        city_slug: City slug matching CITY_CONFIGS key (e.g. "bend")
        api_key: Anthropic API key (falls back to ANTHROPIC_API_KEY env)
        google_places_key: Google Places API key (optional, falls back to
            GOOGLE_PLACES_API_KEY env)
        gcs_bucket: GCS bucket for raw data persistence (default "overplanned-raw")
        limit: max unlinked signals to process
        skip_geocode: Skip inline geocoding (city_seeder passes True since
            it runs the dedicated geocode_backfill step instead)

    Returns:
        FallbackStats with full run metrics
    """
    t0 = time.monotonic()
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    google_places_key = google_places_key or os.environ.get("GOOGLE_PLACES_API_KEY")

    if not api_key:
        raise ValueError("No Anthropic API key provided (set ANTHROPIC_API_KEY)")

    city_config = get_city_config(city_slug)
    stopwords = get_all_stopwords()
    stats = FallbackStats()

    logger.info("=== LLM fallback seeder: %s ===", city_slug)

    # 1. Fetch unlinked signals
    signals = await _fetch_unlinked_signals(pool, city_config.name, limit=limit)
    stats.signals_fetched = len(signals)

    if not signals:
        logger.info("No unlinked signals found for %s -- nothing to do", city_slug)
        stats.latency_seconds = round(time.monotonic() - t0, 2)
        return stats

    logger.info("Found %d unlinked signals for %s", len(signals), city_slug)

    # 1a. Persist raw signal data to GCS for future graduation pipeline.
    # Must run BEFORE LLM extraction so the graduation pipeline always has
    # the original scraped excerpts regardless of extraction outcome.
    # Wrapped in try/except: GCS failure must never abort the seeder.
    try:
        stats.gcs_raw_written = await write_raw_signals_to_gcs(
            city_slug, signals, bucket_name=gcs_bucket,
        )
    except Exception as gcs_exc:
        logger.warning(
            "GCS raw signal write failed for %s (non-fatal): %s",
            city_slug, gcs_exc,
        )
    logger.info(
        "Persisted %d raw signals to GCS for %s",
        stats.gcs_raw_written, city_slug,
    )

    # 2. LLM extraction in batches
    all_venues: list[ExtractedVenue] = []
    all_links: list[SignalVenueLink] = []

    async with httpx.AsyncClient() as client:
        for i in range(0, len(signals), BATCH_SIZE):
            batch = signals[i:i + BATCH_SIZE]
            logger.info(
                "Processing batch %d/%d (%d signals)",
                (i // BATCH_SIZE) + 1,
                (len(signals) + BATCH_SIZE - 1) // BATCH_SIZE,
                len(batch),
            )

            try:
                venues, links = await _extract_batch(
                    client, api_key, city_config.name, batch,
                    stopwords, city_slug, stats,
                )
                all_venues.extend(venues)
                all_links.extend(links)
            except NonRetryableAPIError as exc:
                stats.errors.append(str(exc))
                logger.error("Aborting: non-retryable API error")
                break

        # 3. Dedup extracted venues
        deduped = _dedup_venues(all_venues, city_slug)
        logger.info("Extracted %d unique venues from %d total", len(deduped), len(all_venues))

        if not deduped:
            logger.info("No venues extracted -- nothing to create")
            stats.latency_seconds = round(time.monotonic() - t0, 2)
            return stats

        # 4. Optional geocoding (skipped when city_seeder runs dedicated backfill step)
        if skip_geocode:
            stats.geocode_skipped = len(deduped)
            logger.info("Skipping inline geocoding (skip_geocode=True, %d venues)", len(deduped))
        else:
            await _geocode_venues(client, deduped, city_config.name, google_places_key, stats)

        # 4a. Persist geocoded venue data to GCS.
        # Written inside the httpx client context so it follows geocoding
        # but runs before any DB writes, preserving the raw geocode output.
        # Wrapped in try/except: GCS failure must never abort the seeder.
        try:
            stats.gcs_geocoded_written = await write_geocoded_venues_to_gcs(
                city_slug, deduped, bucket_name=gcs_bucket,
            )
        except Exception as gcs_exc:
            logger.warning(
                "GCS geocoded venue write failed for %s (non-fatal): %s",
                city_slug, gcs_exc,
            )
        logger.info(
            "Persisted %d geocoded venues to GCS for %s",
            stats.gcs_geocoded_written, city_slug,
        )

    # 5. Create ActivityNodes
    slug_to_id = await _create_activity_nodes(pool, deduped, city_config, stats)
    logger.info(
        "Nodes: %d created, %d already existed",
        stats.venues_created, stats.venues_existing,
    )

    # 6. Relink signals
    await _relink_signals(pool, all_links, slug_to_id, stats)
    logger.info("Relinked %d signals", stats.signals_relinked)

    # 7. Cost + timing
    stats.estimated_cost_usd = (
        (stats.total_input_tokens / 1_000_000) * INPUT_COST_PER_1M
        + (stats.total_output_tokens / 1_000_000) * OUTPUT_COST_PER_1M
    )
    stats.latency_seconds = round(time.monotonic() - t0, 2)

    # 8. Audit log
    try:
        registry_id = await _log_to_model_registry(pool, stats, city_slug)
        logger.info("ModelRegistry entry: %s", registry_id)
    except Exception as exc:
        logger.warning("Failed to log to ModelRegistry (non-fatal): %s", exc)

    logger.info(
        "=== Fallback seeder %s: extracted=%d created=%d relinked=%d cost=$%.4f %.1fs ===",
        city_slug,
        stats.venues_extracted,
        stats.venues_created,
        stats.signals_relinked,
        stats.estimated_cost_usd,
        stats.latency_seconds,
    )

    return stats


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    """CLI entry point for LLM fallback seeder."""
    import argparse
    import sys

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        description="LLM fallback seeder: create ActivityNodes from unlinked signals"
    )
    parser.add_argument("city", help="City slug (e.g. bend, austin, portland)")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--limit", type=int, default=200, help="Max signals to process")
    parser.add_argument("--geocode-backfill", action="store_true",
                        help="Run geocode backfill only (no LLM extraction)")
    parser.add_argument("--geocode-limit", type=int, default=100,
                        help="Max nodes to geocode (default 100)")
    parser.add_argument("--check-status", action="store_true",
                        help="Run business status check only (flags closed venues)")
    parser.add_argument("--status-limit", type=int, default=200,
                        help="Max nodes to check (default 200)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not args.database_url:
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    pool = await asyncpg.create_pool(args.database_url)
    try:
        if args.check_status:
            status_stats = await check_business_status(
                pool, args.city, limit=args.status_limit,
            )
            logger.info("Business status check: %s", status_stats)
        elif args.geocode_backfill:
            geo_stats = await geocode_backfill(pool, args.city, limit=args.geocode_limit)
            logger.info("Geocode backfill: %s", geo_stats)
        else:
            stats = await run_llm_fallback(pool, args.city, limit=args.limit)
            if stats.errors:
                logger.warning("Completed with %d errors: %s", len(stats.errors), stats.errors)
            else:
                logger.info("Completed successfully: %s", stats)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
