"""
Atlas Obscura scraper for hidden gem activity nodes.

Scrapes Atlas Obscura city pages to extract unusual/hidden-gem places,
producing ActivityNode rows with hidden_gem QualitySignals.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from .base import BaseScraper, DeadLetterQueue, SourceRegistry, retry_with_backoff

logger = logging.getLogger(__name__)

# Atlas Obscura city listing URL pattern
_CITY_URL_TEMPLATE = "https://www.atlasobscura.com/things-to-do/{city}/places"
_BASE_URL = "https://www.atlasobscura.com"

# Max pages to paginate through per city
_MAX_PAGES = 10


class AtlasObscuraScraper(BaseScraper):
    """
    Scrapes Atlas Obscura for hidden-gem places in a given city.

    Produces ActivityNode-shaped dicts with attached QualitySignal
    metadata for the hidden_gem signal type.
    """

    SOURCE_REGISTRY = SourceRegistry(
        name="atlas_obscura",
        base_url=_BASE_URL,
        authority_score=0.75,
        scrape_frequency_hours=168,  # weekly
        requests_per_minute=10,  # respectful rate
    )

    def __init__(self, city: str):
        """
        Args:
            city: URL-slug for the city (e.g. "tokyo", "new-york", "paris").
        """
        super().__init__()
        self.city = city.lower().strip()
        self._client = httpx.Client(
            headers=self.get_headers(),
            timeout=30.0,
            follow_redirects=True,
        )

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------------
    # BaseScraper interface
    # ------------------------------------------------------------------

    def scrape(self) -> List[Dict[str, Any]]:
        """Fetch raw place cards from Atlas Obscura city pages."""
        raw_items: List[Dict[str, Any]] = []
        url = _CITY_URL_TEMPLATE.format(city=self.city)

        for page in range(1, _MAX_PAGES + 1):
            page_url = url if page == 1 else f"{url}?page={page}"
            self.rate_limiter.acquire()

            resp = self._client.get(page_url)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("div.content-card, a.content-card")

            if not cards:
                break  # no more results

            for card in cards:
                raw = self._extract_card(card, page_url)
                if raw:
                    raw_items.append(raw)

            # Stop if there's no next-page link
            if not soup.select_one("a.next, a[rel='next']"):
                break

        logger.info(
            f"Atlas Obscura: scraped {len(raw_items)} places for city={self.city}"
        )
        return raw_items

    def parse(self, raw_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse a raw card dict into an ActivityNode-shaped row
        with hidden_gem QualitySignal attached.
        """
        title = raw_item.get("title", "").strip()
        if not title:
            return None

        # Build ActivityNode row
        activity_node: Dict[str, Any] = {
            "external_source": "atlas_obscura",
            "external_id": raw_item.get("slug") or _slugify(title),
            "name": title,
            "description": raw_item.get("subtitle", ""),
            "category": _map_category(raw_item.get("category", "")),
            "latitude": raw_item.get("latitude"),
            "longitude": raw_item.get("longitude"),
            "address": raw_item.get("location_text", ""),
            "city": self.city,
            "source_url": raw_item.get("detail_url", ""),
            "scraped_at": datetime.utcnow().isoformat(),
        }

        # QualitySignal: hidden_gem
        quality_signal: Dict[str, Any] = {
            "source": "atlas_obscura",
            "signal_type": "hidden_gem",
            "score": _compute_hidden_gem_score(raw_item),
            "evidence": {
                "visitors_count": raw_item.get("visitors_count"),
                "been_here_count": raw_item.get("been_here_count"),
                "want_to_visit_count": raw_item.get("want_to_visit_count"),
                "subtitle": raw_item.get("subtitle", ""),
            },
            "observed_at": datetime.utcnow().isoformat(),
        }

        activity_node["quality_signals"] = [quality_signal]
        return activity_node

    def store(self, parsed_item: Dict[str, Any]) -> None:
        """
        Store a parsed ActivityNode.

        Currently writes to a staging list; actual DB insertion is handled
        by the pipeline orchestrator that calls collect_results().
        """
        self._staged.append(parsed_item)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def _staged(self) -> List[Dict[str, Any]]:
        if not hasattr(self, "__staged"):
            self.__staged: List[Dict[str, Any]] = []
        return self.__staged

    def collect_results(self) -> List[Dict[str, Any]]:
        """Return all staged ActivityNode rows and clear the buffer."""
        results = list(self._staged)
        self._staged.clear()
        return results

    # ------------------------------------------------------------------
    # Detail page enrichment (optional second pass)
    # ------------------------------------------------------------------

    @retry_with_backoff(max_attempts=2, base_delay=2.0)
    def enrich_from_detail(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fetch the detail page to extract coordinates and extended description.

        Args:
            item: A raw item dict with a detail_url key.

        Returns:
            The item dict enriched with lat/lng and full description.
        """
        detail_url = item.get("detail_url")
        if not detail_url:
            return item

        self.rate_limiter.acquire()
        resp = self._client.get(detail_url)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Coordinates from meta or JSON-LD
        lat, lng = _extract_coordinates(soup)
        if lat is not None:
            item["latitude"] = lat
            item["longitude"] = lng

        # Extended description
        desc_el = soup.select_one("div.DDP__body-copy, div.item-body")
        if desc_el:
            item["full_description"] = desc_el.get_text(separator=" ", strip=True)

        # Engagement counts from detail page
        for selector, key in [
            ("div.item-been-here-count, span.been-here-count", "been_here_count"),
            ("div.item-want-to-visit-count, span.want-to-visit-count", "want_to_visit_count"),
        ]:
            el = soup.select_one(selector)
            if el:
                count = _parse_int(el.get_text())
                if count is not None:
                    item[key] = count

        return item

    # ------------------------------------------------------------------
    # Internal extraction
    # ------------------------------------------------------------------

    def _extract_card(self, card: Tag, page_url: str) -> Optional[Dict[str, Any]]:
        """Pull structured fields from a single place card element."""
        title_el = card.select_one(
            "h3, .content-card-title, span.title, .js-title-content"
        )
        if not title_el:
            return None

        title = title_el.get_text(strip=True)

        # Detail URL
        link_el = card if card.name == "a" else card.select_one("a")
        href = link_el.get("href", "") if link_el else ""
        detail_url = urljoin(_BASE_URL, href) if href else ""

        # Slug from URL
        slug = href.strip("/").split("/")[-1] if href else ""

        # Subtitle / short description
        subtitle_el = card.select_one(
            ".content-card-subtitle, p.subtitle, span.subtitle"
        )
        subtitle = subtitle_el.get_text(strip=True) if subtitle_el else ""

        # Location text
        loc_el = card.select_one(
            ".content-card-place, .place-card-location, span.place"
        )
        location_text = loc_el.get_text(strip=True) if loc_el else ""

        # Category badge
        cat_el = card.select_one(".content-card-badge, span.badge, span.category")
        category = cat_el.get_text(strip=True) if cat_el else ""

        # Engagement counts (sometimes on cards)
        visitors_count = _parse_int_from_el(
            card, ".content-card-visitors, .visitors-count"
        )
        been_here_count = _parse_int_from_el(
            card, ".been-here, .been-here-count"
        )
        want_to_visit_count = _parse_int_from_el(
            card, ".want-to-visit, .want-to-visit-count"
        )

        return {
            "title": title,
            "slug": slug,
            "subtitle": subtitle,
            "detail_url": detail_url,
            "location_text": location_text,
            "category": category,
            "visitors_count": visitors_count,
            "been_here_count": been_here_count,
            "want_to_visit_count": want_to_visit_count,
            "latitude": None,
            "longitude": None,
        }


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _parse_int(text: str) -> Optional[int]:
    """Extract first integer from text like '1,234 people'."""
    if not text:
        return None
    cleaned = re.sub(r"[^\d]", "", text)
    return int(cleaned) if cleaned else None


def _parse_int_from_el(parent: Tag, selector: str) -> Optional[int]:
    """Select an element and parse its text as an integer."""
    el = parent.select_one(selector)
    return _parse_int(el.get_text()) if el else None


def _extract_coordinates(soup: BeautifulSoup) -> tuple[Optional[float], Optional[float]]:
    """Extract lat/lng from meta tags or JSON-LD in a detail page."""
    # Try meta tags first
    lat_meta = soup.select_one('meta[property="place:location:latitude"]')
    lng_meta = soup.select_one('meta[property="place:location:longitude"]')
    if lat_meta and lng_meta:
        try:
            return float(lat_meta["content"]), float(lng_meta["content"])
        except (ValueError, KeyError):
            pass

    # Try data attributes on map element
    map_el = soup.select_one("[data-lat][data-lng], [data-latitude][data-longitude]")
    if map_el:
        try:
            lat = float(map_el.get("data-lat") or map_el.get("data-latitude", ""))
            lng = float(map_el.get("data-lng") or map_el.get("data-longitude", ""))
            return lat, lng
        except (ValueError, TypeError):
            pass

    return None, None


def _slugify(text: str) -> str:
    """Basic slugify for fallback external_id generation."""
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _map_category(raw_category: str) -> str:
    """Map Atlas Obscura category badges to our internal categories."""
    mapping = {
        "museum": "culture",
        "nature": "nature",
        "food": "food_drink",
        "architecture": "culture",
        "art": "culture",
        "religion": "culture",
        "historical": "culture",
        "ruins": "culture",
        "park": "nature",
        "garden": "nature",
        "market": "shopping",
        "bar": "food_drink",
        "restaurant": "food_drink",
        "cafe": "food_drink",
    }
    key = raw_category.lower().strip()
    for keyword, category in mapping.items():
        if keyword in key:
            return category
    return "attraction"  # default


def _compute_hidden_gem_score(raw_item: Dict[str, Any]) -> float:
    """
    Compute a hidden_gem quality score (0.0-1.0).

    Heuristic: Atlas Obscura places are inherently hidden-gem-ish.
    Score is boosted by low visitor counts (less mainstream = more hidden)
    and presence on the platform at all.

    Baseline score is 0.6 (being on Atlas Obscura is already a signal).
    """
    base_score = 0.6

    visitors = raw_item.get("visitors_count")
    been_here = raw_item.get("been_here_count")

    # Low visitor count = more hidden gem-like
    if visitors is not None:
        if visitors < 100:
            base_score += 0.2
        elif visitors < 500:
            base_score += 0.1
        elif visitors > 5000:
            base_score -= 0.1

    # Low "been here" count also boosts
    if been_here is not None:
        if been_here < 50:
            base_score += 0.1
        elif been_here < 200:
            base_score += 0.05

    return max(0.0, min(1.0, round(base_score, 2)))
