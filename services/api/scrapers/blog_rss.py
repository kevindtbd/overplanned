"""
Blog RSS scraper — first concrete scraper using the BaseScraper framework.

Parses RSS feeds from curated travel blog sources (The Infatuation, Eater, etc.)
and produces QualitySignal rows with per-source authority scores.

Authority scores come from docs/overplanned-blog-sources.md and are hardcoded
per source in FEED_REGISTRY. They're reviewed quarterly.
"""

import hashlib
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from html import unescape
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

import feedparser

from services.api.scrapers.base import BaseScraper, SourceRegistry

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")


# ---------------------------------------------------------------------------
# Feed registry — curated from docs/overplanned-blog-sources.md
# authority_score values are from the Authority Score Model.
# ---------------------------------------------------------------------------

@dataclass
class FeedSource:
    """A single RSS feed with metadata."""
    name: str
    feed_url: str
    base_url: str
    authority_score: float
    city: Optional[str] = None  # None = multi-city
    category: str = "dining"    # dining | travel | culture


# Seed list — The Infatuation first (primary deliverable), then others.
# RSS URLs follow standard patterns; verified feeds only.
FEED_REGISTRY: list[FeedSource] = [
    # --- US Food & Dining ---
    FeedSource(
        name="The Infatuation",
        feed_url="https://www.theinfatuation.com/rss",
        base_url="https://www.theinfatuation.com",
        authority_score=0.91,
        category="dining",
    ),
    FeedSource(
        name="Eater",
        feed_url="https://www.eater.com/rss/index.xml",
        base_url="https://www.eater.com",
        authority_score=0.82,
        category="dining",
    ),
    FeedSource(
        name="Grub Street",
        feed_url="https://www.grubstreet.com/feed/rss",
        base_url="https://www.grubstreet.com",
        authority_score=0.88,
        city="New York",
        category="dining",
    ),
    FeedSource(
        name="Bon Appetit Travel",
        feed_url="https://www.bonappetit.com/feed/rss",
        base_url="https://www.bonappetit.com",
        authority_score=0.74,
        category="dining",
    ),

    # --- Global / Culture ---
    FeedSource(
        name="Atlas Obscura",
        feed_url="https://www.atlasobscura.com/feeds/latest",
        base_url="https://www.atlasobscura.com",
        authority_score=0.80,
        category="culture",
    ),
    FeedSource(
        name="Hidden Europe",
        feed_url="https://hiddeneurope.co.uk/feed",
        base_url="https://hiddeneurope.co.uk",
        authority_score=0.89,
        category="travel",
    ),
    FeedSource(
        name="Messy Nessy Chic",
        feed_url="https://www.messynessychic.com/feed/",
        base_url="https://www.messynessychic.com",
        authority_score=0.84,
        city="Paris",
        category="culture",
    ),

    # --- Japan ---
    FeedSource(
        name="Tokyo Cheapo",
        feed_url="https://tokyocheapo.com/feed/",
        base_url="https://tokyocheapo.com",
        authority_score=0.82,
        city="Tokyo",
        category="travel",
    ),
    FeedSource(
        name="Deep Kyoto",
        feed_url="https://www.deepkyoto.com/feed/",
        base_url="https://www.deepkyoto.com",
        authority_score=0.85,
        city="Kyoto",
        category="culture",
    ),

    # --- Southeast Asia ---
    FeedSource(
        name="Migrationology",
        feed_url="https://migrationology.com/feed/",
        base_url="https://migrationology.com",
        authority_score=0.83,
        category="dining",
    ),

    # --- Bend, Oregon (canary city) ---
    # Source Weekly: Bend's alt-weekly. Best local editorial signal for Central OR.
    # Zero affiliate model, resident staff, covers food/culture/nightlife.
    # Modeled after The Stranger (Seattle) — same alt-weekly profile.
    FeedSource(
        name="Source Weekly",
        feed_url="https://www.sourceweekly.com/CivicAlerts.aspx?AID=1&format=rss",
        base_url="https://www.sourceweekly.com",
        authority_score=0.81,
        city="Bend",
        category="culture",
    ),
    # Bend Bulletin: local newspaper of record for Central Oregon.
    # Authority score reflects local editorial depth; some wire content mixed in.
    FeedSource(
        name="Bend Bulletin",
        feed_url="https://www.bendbulletin.com/feeds/latest/",
        base_url="https://www.bendbulletin.com",
        authority_score=0.72,
        city="Bend",
        category="travel",
    ),
    # Visit Bend: official tourism board. High coverage, lower authenticity signal.
    # Use for structural data (events, seasonal timing) not vibe signal.
    # Authority capped at 0.55 — tourism board content is tourist-facing by definition.
    FeedSource(
        name="Visit Bend",
        feed_url="https://www.visitbend.com/feed/",
        base_url="https://www.visitbend.com",
        authority_score=0.55,
        city="Bend",
        category="travel",
    ),
    # Sunset Magazine: covers PNW and Central Oregon with genuine regional knowledge.
    # Applies to Bend for outdoor/lifestyle content; not Bend-exclusive.
    FeedSource(
        name="Sunset Magazine",
        feed_url="https://www.sunset.com/feed",
        base_url="https://www.sunset.com",
        authority_score=0.73,
        city=None,  # multi-city PNW coverage
        category="travel",
    ),
    # OregonLive — Bend/Central Oregon section (no dedicated RSS as of Feb 2026).
    # The main OregonLive feed covers statewide news; Bend content is mixed in.
    # TODO: When OregonLive adds a Central Oregon RSS endpoint, update feed_url.
    #   Workaround: use full feed + filter by city="Bend" in parse() downstream.
    FeedSource(
        name="OregonLive",
        feed_url="https://www.oregonlive.com/arc/outboundfeeds/rss/?rss=home",
        base_url="https://www.oregonlive.com",
        authority_score=0.67,
        city=None,  # statewide; Bend content filtered by keyword downstream
        category="travel",
    ),
]


def _strip_html(html: str) -> str:
    """Remove HTML tags and decode entities. Returns plain text."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    # Collapse whitespace
    return re.sub(r"\s+", " ", text).strip()


def _content_hash(text: str) -> str:
    """SHA-256 of content for dedup / skip-on-unchanged."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _classify_signal_type(title: str, summary: str) -> str:
    """
    Lightweight rule-based classifier for QualitySignal.signalType.

    Returns one of: mention | recommendation | overrated_flag | hidden_gem | negative
    """
    combined = (title + " " + summary).lower()

    overrated_patterns = [
        "overrated", "skip it", "don't bother", "not worth",
        "tourist trap", "overhyped",
    ]
    hidden_gem_patterns = [
        "hidden gem", "under the radar", "locals only",
        "best kept secret", "off the beaten",
    ]
    negative_patterns = [
        "worst", "avoid", "closed permanently", "disappointing",
        "terrible", "never again",
    ]
    recommendation_patterns = [
        "best", "favorite", "must visit", "don't miss",
        "top pick", "highly recommend", "where to eat",
    ]

    for pat in overrated_patterns:
        if pat in combined:
            return "overrated_flag"

    for pat in hidden_gem_patterns:
        if pat in combined:
            return "hidden_gem"

    for pat in negative_patterns:
        if pat in combined:
            return "negative"

    for pat in recommendation_patterns:
        if pat in combined:
            return "recommendation"

    return "mention"


# ---------------------------------------------------------------------------
# BlogRssScraper — the main class
# ---------------------------------------------------------------------------

class BlogRssScraper(BaseScraper):
    """
    RSS feed scraper for curated travel blog sources.

    Scrapes all feeds in FEED_REGISTRY (or a filtered subset), parses entries,
    and stores QualitySignal rows via raw SQL (asyncpg-compatible).

    Usage:
        scraper = BlogRssScraper(db_pool=app.state.db)
        stats = scraper.run()

        # Single feed:
        scraper = BlogRssScraper(db_pool=app.state.db, feed_filter="The Infatuation")
        stats = scraper.run()
    """

    SOURCE_REGISTRY = SourceRegistry(
        name="blog_rss",
        base_url="https://www.theinfatuation.com",
        authority_score=0.91,
        scrape_frequency_hours=168,  # weekly
        requests_per_minute=10,      # conservative — many different hosts
    )

    # Max excerpt length stored in rawExcerpt (chars)
    MAX_EXCERPT_LENGTH = 2000

    def __init__(
        self,
        db_pool: Any,
        feed_filter: Optional[str] = None,
        feeds: Optional[list[FeedSource]] = None,
    ):
        """
        Args:
            db_pool: asyncpg-compatible pool (or mock with execute/fetch).
            feed_filter: If set, only scrape feeds whose name contains this string.
            feeds: Override FEED_REGISTRY with a custom list (useful for tests).
        """
        super().__init__()
        self.db_pool = db_pool
        self.feed_filter = feed_filter
        self._feeds = feeds if feeds is not None else FEED_REGISTRY

    def _active_feeds(self) -> list[FeedSource]:
        """Return feeds to scrape, applying filter if set."""
        if self.feed_filter:
            return [
                f for f in self._feeds
                if self.feed_filter.lower() in f.name.lower()
            ]
        return list(self._feeds)

    # ----- BaseScraper interface -----

    def scrape(self) -> list[Dict[str, Any]]:
        """
        Fetch and parse all active RSS feeds.

        Returns list of raw items: one dict per RSS entry, tagged with source metadata.
        """
        raw_items: list[Dict[str, Any]] = []
        feeds = self._active_feeds()

        if not feeds:
            logger.warning("No feeds matched filter: %s", self.feed_filter)
            return raw_items

        for feed_source in feeds:
            try:
                self.rate_limiter.acquire()
                parsed_feed = feedparser.parse(
                    feed_source.feed_url,
                    agent=self.USER_AGENT,
                )

                if parsed_feed.bozo and not parsed_feed.entries:
                    # Feed is malformed AND has no entries — log and skip
                    logger.warning(
                        "Malformed feed with no entries: %s (%s)",
                        feed_source.name, parsed_feed.bozo_exception,
                    )
                    continue

                if parsed_feed.bozo and parsed_feed.entries:
                    # Malformed but has entries — log warning, continue
                    logger.info(
                        "Feed %s has parse warnings but %d entries — proceeding: %s",
                        feed_source.name, len(parsed_feed.entries),
                        parsed_feed.bozo_exception,
                    )

                for entry in parsed_feed.entries:
                    raw_items.append({
                        "_source": feed_source,
                        "_entry": entry,
                    })

                logger.info(
                    "Fetched %d entries from %s",
                    len(parsed_feed.entries), feed_source.name,
                )

            except Exception as e:
                logger.error("Failed to fetch feed %s: %s", feed_source.name, e)
                # Don't abort the whole run — continue with other feeds

        return raw_items

    def parse(self, raw_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse a single RSS entry into a QualitySignal-shaped dict.

        Returns None if the entry lacks required fields (title + link).
        """
        source: FeedSource = raw_item["_source"]
        entry = raw_item["_entry"]

        title = getattr(entry, "title", None)
        link = getattr(entry, "link", None)

        if not title or not link:
            return None

        # Extract summary text (prefer content, fall back to summary)
        summary_html = ""
        if hasattr(entry, "content") and entry.content:
            summary_html = entry.content[0].get("value", "")
        elif hasattr(entry, "summary"):
            summary_html = entry.summary or ""

        summary_text = _strip_html(summary_html)

        # Build excerpt: title + truncated summary
        excerpt = f"{title}\n\n{summary_text}"
        if len(excerpt) > self.MAX_EXCERPT_LENGTH:
            excerpt = excerpt[: self.MAX_EXCERPT_LENGTH - 3] + "..."

        # Parse published date
        published_at = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass

        if hasattr(entry, "updated_parsed") and entry.updated_parsed and not published_at:
            try:
                published_at = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass

        content_hash = _content_hash(excerpt)
        signal_type = _classify_signal_type(title, summary_text)

        return {
            "source_name": source.name,
            "source_url": link,
            "source_authority": source.authority_score,
            "signal_type": signal_type,
            "raw_excerpt": excerpt,
            "content_hash": content_hash,
            "published_at": published_at,
            "title": title,
            "city": source.city,
            "category": source.category,
        }

    def store(self, parsed_item: Dict[str, Any]) -> None:
        """
        Store a parsed item as a QualitySignal row.

        Uses a placeholder activityNodeId (entity resolution happens downstream
        in M-005). Skips duplicate content via content_hash check.

        This is a sync wrapper — for the MVP pipeline, scraping runs as a
        batch job, not inside the async request cycle.
        """
        import asyncio

        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        if loop and loop.is_running():
            # We're inside an async context — schedule as task
            loop.create_task(self._store_async(parsed_item))
        else:
            # Sync context — run directly
            asyncio.run(self._store_async(parsed_item))

    async def _store_async(self, parsed_item: Dict[str, Any]) -> None:
        """Async implementation of store — inserts QualitySignal row."""
        content_hash = parsed_item["content_hash"]

        # Dedup: skip if we already have this exact content from this source
        existing = await self.db_pool.fetchrow(
            """
            SELECT id FROM quality_signals
            WHERE "sourceName" = $1
              AND "rawExcerpt" IS NOT NULL
              AND md5("rawExcerpt") = md5($2)
            LIMIT 1
            """,
            parsed_item["source_name"],
            parsed_item["raw_excerpt"],
        )

        if existing:
            logger.debug(
                "Skipping duplicate: %s from %s",
                parsed_item["title"], parsed_item["source_name"],
            )
            return

        # For now, use a sentinel activityNodeId. Entity resolution (M-005)
        # will link these to real ActivityNode rows later. We store with a
        # well-known "unresolved" UUID so downstream can find unlinked signals.
        unresolved_node_id = "00000000-0000-0000-0000-000000000000"

        signal_id = str(uuid.uuid4())
        # Strip timezone — Prisma DateTime maps to timestamp without time zone
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        await self.db_pool.execute(
            """
            INSERT INTO quality_signals (
                id, "activityNodeId", "sourceName", "sourceUrl",
                "sourceAuthority", "signalType", "rawExcerpt",
                "extractedAt", "createdAt"
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT DO NOTHING
            """,
            signal_id,
            unresolved_node_id,
            parsed_item["source_name"],
            parsed_item["source_url"],
            parsed_item["source_authority"],
            parsed_item["signal_type"],
            parsed_item["raw_excerpt"],
            now,
            now,
        )

        logger.info(
            "Stored QualitySignal: %s [%s] auth=%.2f type=%s",
            parsed_item["title"],
            parsed_item["source_name"],
            parsed_item["source_authority"],
            parsed_item["signal_type"],
        )

    # ----- Convenience entry points -----

    @classmethod
    def scrape_infatuation(cls, db_pool: Any) -> Dict[str, Any]:
        """Scrape only The Infatuation feed. Primary deliverable for M-001."""
        scraper = cls(db_pool=db_pool, feed_filter="The Infatuation")
        return scraper.run()

    @classmethod
    def scrape_all(cls, db_pool: Any) -> Dict[str, Any]:
        """Scrape all registered feeds."""
        scraper = cls(db_pool=db_pool)
        return scraper.run()
