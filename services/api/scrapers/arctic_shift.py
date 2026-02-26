"""
Arctic Shift Reddit archive loader for travel venue recommendations.

Reads historical Parquet dumps from Arctic Shift (not live Reddit API).
Extracts venue mentions, location context, and sentiment from travel
subreddits, weighted by score/upvotes for authority signals.

Target subs: city-specific subreddits driven by city_configs.py.
General subs: r/solotravel, r/travel, r/foodtravel, etc.

Output: QualitySignal rows linked to venue names + city context.

Dynamic city support: import get_target_cities_dict() and
get_all_subreddit_weights() from pipeline.city_configs to drive
TARGET_CITIES and SUBREDDIT_WEIGHTS. Japan configs preserved as
fallback for backward compatibility when city_configs is unavailable.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .base import BaseScraper, SourceRegistry, DeadLetterQueue

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dynamic city/subreddit config from city_configs.py
# ---------------------------------------------------------------------------

def _load_city_configs():
    """
    Load TARGET_CITIES and SUBREDDIT_WEIGHTS from city_configs.py.

    Returns (target_cities_dict, subreddit_weights_dict).
    Falls back to Japan-only hardcoded values if import fails
    (e.g. running arctic_shift in isolation without full package).
    """
    try:
        from services.api.pipeline.city_configs import (
            get_target_cities_dict,
            get_all_subreddit_weights,
        )
        return get_target_cities_dict(), get_all_subreddit_weights()
    except ImportError:
        logger.warning(
            "Could not import city_configs — falling back to Japan-only hardcoded config. "
            "Install or wire services.api.pipeline.city_configs to enable dynamic city support."
        )
        _fallback_cities: Dict[str, List[str]] = {
            "tokyo": [
                "tokyo", "shinjuku", "shibuya", "harajuku", "akihabara",
                "ginza", "roppongi", "asakusa", "ueno", "ikebukuro",
                "tsukiji", "odaiba", "shimokitazawa", "nakameguro",
                "yanaka", "koenji", "kichijoji", "ebisu",
            ],
            "kyoto": [
                "kyoto", "gion", "arashiyama", "fushimi", "higashiyama",
                "nishiki", "pontocho", "kiyomizu", "nara",
            ],
            "osaka": [
                "osaka", "dotonbori", "namba", "umeda", "shinsekai",
                "amerikamura", "tennoji", "kuromon",
            ],
        }
        _fallback_weights: Dict[str, float] = {
            "japantravel": 1.0,
            "solotravel": 0.85,
            "travel": 0.7,
            "foodtravel": 0.9,
            "tokyo": 0.95,
            "kyoto": 0.95,
            "osaka": 0.95,
            "japanlife": 0.8,
            "movingtojapan": 0.6,
        }
        return _fallback_cities, _fallback_weights


# Build module-level dicts — populated once on import.
TARGET_CITIES, SUBREDDIT_WEIGHTS = _load_city_configs()

# Flatten term -> city_slug for quick lookup
ALL_CITY_TERMS: Set[str] = set()
TERM_TO_CITY: Dict[str, str] = {}
for _city_slug, _terms in TARGET_CITIES.items():
    for _term in _terms:
        ALL_CITY_TERMS.add(_term)
        TERM_TO_CITY[_term] = _city_slug


# ---------------------------------------------------------------------------
# Quality filter thresholds (playbook requirement)
# ---------------------------------------------------------------------------

# Minimum score (upvotes) to consider a post/comment worth processing.
# For Bend canary: still apply threshold, but log how many are filtered.
MIN_SCORE_THRESHOLD = 3

# Playbook quality gate: applied at ingest time on top of MIN_SCORE_THRESHOLD.
QUALITY_FILTER_MIN_SCORE = 10
QUALITY_FILTER_MIN_UPVOTE_RATIO = 0.70


# ---------------------------------------------------------------------------
# is_local detection patterns
# ---------------------------------------------------------------------------

# Patterns indicating the author is a local resident.
# Matched case-insensitively against post body/title.
LOCAL_INDICATOR_PATTERNS = [
    re.compile(r"\bi\s+live\s+here\b", re.IGNORECASE),
    re.compile(r"\bas\s+a\s+local\b", re.IGNORECASE),
    re.compile(r"\bgrew\s+up\s+here\b", re.IGNORECASE),
    re.compile(r"\bbeen\s+here\s+\d+\s+years?\b", re.IGNORECASE),
    re.compile(r"\bmoved\s+here\b", re.IGNORECASE),
    re.compile(r"\blocal\s+here\b", re.IGNORECASE),
]


def detect_is_local(text: str) -> bool:
    """
    Detect if the post author self-identifies as a local resident.

    Checks for patterns like 'I live here', 'as a local', 'grew up here',
    'been here X years', 'moved here', 'local here'.

    Returns True if any pattern matches.
    """
    for pattern in LOCAL_INDICATOR_PATTERNS:
        if pattern.search(text):
            return True
    return False


# ---------------------------------------------------------------------------
# Venue hint patterns
# ---------------------------------------------------------------------------

VENUE_HINT_PATTERNS = [
    # "I recommend X" / "definitely try X" / "check out X"
    re.compile(
        r"(?:recommend|try|check out|visit|loved|enjoyed|go to|stop by|hit up)"
        r"\s+([A-Z][A-Za-z\u3000-\u9fff\uff00-\uffef'&. -]{2,40})",
        re.IGNORECASE,
    ),
    # "X is amazing/great/worth it"
    re.compile(
        r"([A-Z][A-Za-z\u3000-\u9fff\uff00-\uffef'&. -]{2,40})"
        r"\s+(?:is|was|were)\s+(?:amazing|great|incredible|worth|fantastic|excellent"
        r"|awesome|perfect|must-visit|underrated|overrated|a must|the best)",
        re.IGNORECASE,
    ),
    # "at X" or "to X" when preceded by dining/visiting verbs
    re.compile(
        r"(?:ate|dined|stayed|stopped|drank|shopped|visited|went)"
        r"\s+(?:at|to)\s+([A-Z][A-Za-z\u3000-\u9fff\uff00-\uffef'&. -]{2,40})",
        re.IGNORECASE,
    ),
    # Bold or quoted venue names: **X** or "X"
    re.compile(
        r'\*\*([A-Za-z\u3000-\u9fff\uff00-\uffef\'&. -]{2,40})\*\*',
    ),
    re.compile(
        r'"([A-Za-z\u3000-\u9fff\uff00-\uffef\'&. -]{2,40})"',
    ),
]

# Words that look like venue names but aren't.
VENUE_STOPWORDS: Set[str] = {
    "japan", "tokyo", "kyoto", "osaka", "the", "this", "that", "there",
    "here", "where", "which", "what", "when", "they", "their", "them",
    "airport", "station", "hotel", "hostel", "airbnb", "google maps",
    "tripadvisor", "reddit", "subreddit", "japan rail", "jr pass",
    "shinkansen", "subway", "bus", "taxi", "uber", "train",
    "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday", "january", "february", "march", "april",
    "may", "june", "july", "august", "september", "october",
    "november", "december", "edit", "update", "tldr",
    # US generic terms
    "bend", "portland", "seattle", "austin", "new orleans",
    "downtown", "uptown", "midtown", "westside", "eastside",
    "united states", "oregon", "washington",
}

# Sentiment keywords (simple lexicon-based approach).
POSITIVE_WORDS: Set[str] = {
    "amazing", "incredible", "fantastic", "excellent", "awesome",
    "perfect", "delicious", "beautiful", "wonderful", "loved",
    "best", "great", "recommend", "must-visit", "must-try",
    "favorite", "favourite", "heaven", "gem", "hidden gem",
    "underrated", "worth", "outstanding", "superb", "top-notch",
}
NEGATIVE_WORDS: Set[str] = {
    "terrible", "awful", "horrible", "worst", "avoid",
    "overpriced", "overrated", "disappointing", "mediocre",
    "rude", "dirty", "crowded", "tourist trap", "skip",
    "waste", "meh", "bad", "underwhelming",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class VenueMention:
    """A single venue mention extracted from a Reddit post/comment."""
    venue_name: str
    city: str
    subreddit: str
    post_id: str
    comment_id: Optional[str]
    score: int
    text_excerpt: str  # surrounding context (max 500 chars)
    sentiment: str  # positive | negative | neutral
    author: str
    created_utc: int
    permalink: str
    is_local: bool = False


@dataclass
class ArcticShiftConfig:
    """Configuration for an Arctic Shift batch load."""
    parquet_dir: str = "data/arctic_shift"
    subreddits: List[str] = field(default_factory=lambda: list(SUBREDDIT_WEIGHTS.keys()))
    min_score: int = MIN_SCORE_THRESHOLD
    target_cities: List[str] = field(default_factory=lambda: list(TARGET_CITIES.keys()))
    max_rows_per_file: int = 0  # 0 = no limit
    # Quality filter thresholds (playbook requirement)
    quality_min_score: int = QUALITY_FILTER_MIN_SCORE
    quality_min_upvote_ratio: float = QUALITY_FILTER_MIN_UPVOTE_RATIO


# ---------------------------------------------------------------------------
# Core extraction logic
# ---------------------------------------------------------------------------

def detect_city(text: str) -> Optional[str]:
    """
    Detect which target city a text is about.

    Returns the city slug (e.g. 'tokyo', 'bend') or None.
    Uses the dynamically built TERM_TO_CITY map from city_configs.
    """
    text_lower = text.lower()
    # Score each city by how many of its terms appear
    city_scores: Dict[str, int] = {}
    for term in ALL_CITY_TERMS:
        if term in text_lower:
            city = TERM_TO_CITY[term]
            city_scores[city] = city_scores.get(city, 0) + 1

    if not city_scores:
        return None
    return max(city_scores, key=city_scores.get)


def extract_venue_names(text: str) -> List[str]:
    """
    Extract candidate venue names from text using regex patterns.

    Returns deduplicated list of candidate names (may include false positives).
    """
    candidates: List[str] = []

    for pattern in VENUE_HINT_PATTERNS:
        for match in pattern.finditer(text):
            name = match.group(1).strip().rstrip(".")
            # Skip stopwords and too-short names
            if name.lower() in VENUE_STOPWORDS:
                continue
            if len(name) < 3:
                continue
            # Skip if it's all lowercase (likely not a proper noun)
            if name == name.lower() and not any(
                "\u3000" <= c <= "\u9fff" for c in name
            ):
                continue
            candidates.append(name)

    # Deduplicate preserving order, case-insensitive
    seen: Set[str] = set()
    unique: List[str] = []
    for c in candidates:
        key = c.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


def compute_sentiment(text: str) -> str:
    """
    Simple lexicon-based sentiment for a text excerpt.

    Returns: 'positive', 'negative', or 'neutral'.
    """
    text_lower = text.lower()
    pos_count = sum(1 for w in POSITIVE_WORDS if w in text_lower)
    neg_count = sum(1 for w in NEGATIVE_WORDS if w in text_lower)

    if pos_count > neg_count:
        return "positive"
    elif neg_count > pos_count:
        return "negative"
    return "neutral"


def compute_authority_score(
    score: int,
    subreddit: str,
    sentiment: str,
    is_local: bool = False,
) -> float:
    """
    Compute a 0.0-1.0 authority score for a venue mention.

    Factors:
    - Reddit score (log-scaled, capped)
    - Subreddit weight
    - Sentiment bonus (positive mentions slightly more authoritative)
    - Local author bonus: local posts get a 3x weight via signalType downstream,
      but we also apply a small authority bump here for ranking within the scraper.
    """
    import math

    # Log-scale the score: log2(score+1) / log2(1001) -> 0..1
    score_factor = min(math.log2(max(score, 1) + 1) / math.log2(1001), 1.0)

    # Subreddit weight — check dynamic SUBREDDIT_WEIGHTS first
    sub_weight = SUBREDDIT_WEIGHTS.get(subreddit.lower(), 0.5)

    # Sentiment modifier
    sentiment_mod = {"positive": 1.05, "negative": 0.9, "neutral": 1.0}.get(
        sentiment, 1.0
    )

    # Local author bonus: 10% bump for self-identified locals.
    # The full 3x weighting happens downstream via signalType="local_recommendation".
    local_mod = 1.10 if is_local else 1.0

    raw = score_factor * sub_weight * sentiment_mod * local_mod
    return round(min(max(raw, 0.0), 1.0), 4)


def extract_text_excerpt(text: str, venue_name: str, max_len: int = 500) -> str:
    """
    Extract a text excerpt centered around the venue mention.
    """
    idx = text.lower().find(venue_name.lower())
    if idx == -1:
        # Venue name not found literally, return start of text
        return text[:max_len]

    # Center a window around the mention
    half = max_len // 2
    start = max(0, idx - half)
    end = min(len(text), idx + len(venue_name) + half)
    excerpt = text[start:end].strip()

    if start > 0:
        excerpt = "..." + excerpt
    if end < len(text):
        excerpt = excerpt + "..."

    return excerpt


def passes_quality_filter(
    row: Dict[str, Any],
    min_score: int = QUALITY_FILTER_MIN_SCORE,
    min_upvote_ratio: float = QUALITY_FILTER_MIN_UPVOTE_RATIO,
) -> bool:
    """
    Apply playbook quality gate: score > min_score AND upvote_ratio > min_upvote_ratio.

    Returns True if the row passes, False if it should be filtered out.
    Rows missing upvote_ratio are treated as passing (ratio unknown = not penalized).
    Small-corpus cities like Bend depend on this being lenient when data is sparse.
    """
    score = row.get("score", 0) or 0
    if isinstance(score, str):
        try:
            score = int(score)
        except ValueError:
            score = 0

    if score <= min_score:
        return False

    # upvote_ratio is present in post dumps, absent in comment dumps.
    upvote_ratio = row.get("upvote_ratio")
    if upvote_ratio is not None:
        try:
            ratio = float(upvote_ratio)
        except (ValueError, TypeError):
            ratio = 1.0  # unknown — don't penalize
        if ratio < min_upvote_ratio:
            return False

    return True


# ---------------------------------------------------------------------------
# Parquet processing
# ---------------------------------------------------------------------------

def _load_parquet_lazy(path: Path):
    """
    Load a Parquet file. Returns a list of dicts (rows).

    Uses pyarrow for reading. Lazy import to avoid hard dependency
    at module level.
    """
    try:
        import pyarrow.parquet as pq
    except ImportError:
        raise ImportError(
            "pyarrow is required for Arctic Shift Parquet processing. "
            "Install with: pip install pyarrow"
        )

    table = pq.read_table(str(path))
    return table.to_pydict()


def _rows_from_parquet(parquet_dict: Dict[str, list]) -> List[Dict[str, Any]]:
    """Convert columnar pyarrow dict to list of row dicts."""
    if not parquet_dict:
        return []
    keys = list(parquet_dict.keys())
    num_rows = len(parquet_dict[keys[0]])
    return [
        {k: parquet_dict[k][i] for k in keys}
        for i in range(num_rows)
    ]


def _is_relevant_post(row: Dict[str, Any], subreddits: Set[str], min_score: int) -> bool:
    """Check if a row is from a target subreddit with sufficient score."""
    sub = (row.get("subreddit") or "").lower()
    if sub not in subreddits:
        return False
    score = row.get("score", 0) or 0
    if isinstance(score, str):
        try:
            score = int(score)
        except ValueError:
            return False
    return score >= min_score


# ---------------------------------------------------------------------------
# ArcticShiftScraper
# ---------------------------------------------------------------------------

class ArcticShiftScraper(BaseScraper):
    """
    Batch loader for Arctic Shift Reddit Parquet archives.

    NOT a live scraper. Reads pre-downloaded Parquet dumps of Reddit
    posts and comments, extracts venue mentions with location context
    and sentiment, and produces QualitySignal-shaped rows.

    Supports any city configured in city_configs.py. Use target_city
    to scope to a single city (e.g. for the Bend canary run).

    Quality filtering: upvote_ratio > 0.70 AND score > 10 applied at
    ingest time. Counts logged for debugging small-corpus cities.

    is_local detection: posts matching local-indicator patterns set
    signalType="local_recommendation" for 3x downstream weighting.

    Usage:
        # Full multi-city run
        scraper = ArcticShiftScraper(parquet_dir="data/arctic_shift")
        stats = scraper.run()

        # Canary single-city run (Bend)
        scraper = ArcticShiftScraper(
            parquet_dir="data/arctic_shift",
            target_city="bend",
        )
        stats = scraper.run()
        results = scraper.get_results()
    """

    SOURCE_REGISTRY = SourceRegistry(
        name="arctic_shift_reddit",
        base_url="https://arctic-shift.photon-reddit.com",
        authority_score=0.65,  # community-sourced, lower than curated APIs
        scrape_frequency_hours=720,  # monthly re-process (archive is static)
        requests_per_minute=9999,  # local file reads, no rate limit needed
    )

    def __init__(
        self,
        *,
        parquet_dir: str = "data/arctic_shift",
        subreddits: Optional[List[str]] = None,
        min_score: int = MIN_SCORE_THRESHOLD,
        target_cities: Optional[List[str]] = None,
        target_city: Optional[str] = None,
        max_rows_per_file: int = 0,
        quality_min_score: int = QUALITY_FILTER_MIN_SCORE,
        quality_min_upvote_ratio: float = QUALITY_FILTER_MIN_UPVOTE_RATIO,
    ):
        """
        Args:
            parquet_dir: Directory containing Arctic Shift Parquet files.
            subreddits: Subreddits to process (defaults to all from city_configs).
            min_score: Minimum post/comment score for initial pass.
            target_cities: City slugs to extract venues for.
                Defaults to all cities in city_configs.
            target_city: Convenience arg to scope to a single city slug
                (e.g. "bend" for the canary run). Overrides target_cities
                when provided.
            max_rows_per_file: Limit rows per Parquet file (0 = no limit).
            quality_min_score: Playbook quality gate — score threshold.
            quality_min_upvote_ratio: Playbook quality gate — upvote ratio threshold.
        """
        super().__init__()

        # Resolve target city list: target_city overrides target_cities
        if target_city is not None:
            resolved_cities = [target_city]
        elif target_cities is not None:
            resolved_cities = list(target_cities)
        else:
            resolved_cities = list(TARGET_CITIES.keys())

        # Resolve subreddits: if target_city is set, prefer city-specific subs
        if subreddits is not None:
            resolved_subreddits = list(subreddits)
        elif target_city is not None:
            resolved_subreddits = self._subreddits_for_city(target_city)
        else:
            resolved_subreddits = list(SUBREDDIT_WEIGHTS.keys())

        self.config = ArcticShiftConfig(
            parquet_dir=parquet_dir,
            subreddits=resolved_subreddits,
            min_score=min_score,
            target_cities=resolved_cities,
            max_rows_per_file=max_rows_per_file,
            quality_min_score=quality_min_score,
            quality_min_upvote_ratio=quality_min_upvote_ratio,
        )
        self._parquet_path = Path(parquet_dir)
        self._target_subs: Set[str] = {s.lower() for s in self.config.subreddits}

        # Accumulated results
        self._mentions: List[VenueMention] = []
        self._quality_signals: List[Dict[str, Any]] = []

        # Stats
        self._files_processed = 0
        self._rows_scanned = 0
        self._rows_relevant = 0
        self._rows_quality_filtered = 0  # rows dropped by quality gate
        self._local_posts_detected = 0

    @staticmethod
    def _subreddits_for_city(city_slug: str) -> List[str]:
        """
        Return subreddits relevant to a specific city slug.

        Includes the city's own subreddits from city_configs plus
        general travel subs (solotravel, travel, foodtravel).
        Falls back to all SUBREDDIT_WEIGHTS keys if city not found.
        """
        try:
            from services.api.pipeline.city_configs import get_city_config
            config = get_city_config(city_slug)
            city_subs = list(config.subreddits.keys())
        except (ImportError, KeyError):
            city_subs = []

        general_subs = [s for s in SUBREDDIT_WEIGHTS.keys() if s not in city_subs]
        return city_subs + general_subs

    # -- BaseScraper interface ------------------------------------------------

    def scrape(self) -> List[Dict[str, Any]]:
        """
        Read all Parquet files from the configured directory.

        Applies two-stage filtering:
        1. Subreddit membership + basic score threshold (fast, pre-quality)
        2. Playbook quality gate: score > 10 AND upvote_ratio > 0.70

        Returns relevant rows that pass both stages. Logs filtered counts
        for small-corpus city debugging (Bend canary).
        """
        if not self._parquet_path.exists():
            raise FileNotFoundError(
                f"Arctic Shift parquet directory not found: {self._parquet_path}"
            )

        parquet_files = sorted(self._parquet_path.glob("*.parquet"))
        if not parquet_files:
            logger.warning(f"No .parquet files found in {self._parquet_path}")
            return []

        logger.info(
            f"Found {len(parquet_files)} Parquet files in {self._parquet_path}"
        )

        relevant_rows: List[Dict[str, Any]] = []
        pre_quality_count = 0
        post_quality_count = 0

        for pf in parquet_files:
            try:
                parquet_dict = _load_parquet_lazy(pf)
                rows = _rows_from_parquet(parquet_dict)

                if self.config.max_rows_per_file > 0:
                    rows = rows[: self.config.max_rows_per_file]

                self._rows_scanned += len(rows)
                self._files_processed += 1

                file_pre = 0
                file_post = 0
                for row in rows:
                    if not _is_relevant_post(row, self._target_subs, self.config.min_score):
                        continue

                    file_pre += 1
                    pre_quality_count += 1

                    # Apply playbook quality gate
                    if not passes_quality_filter(
                        row,
                        min_score=self.config.quality_min_score,
                        min_upvote_ratio=self.config.quality_min_upvote_ratio,
                    ):
                        self._rows_quality_filtered += 1
                        continue

                    file_post += 1
                    post_quality_count += 1
                    relevant_rows.append(row)
                    self._rows_relevant += 1

                logger.info(
                    f"Processed {pf.name}: {len(rows)} rows scanned, "
                    f"{file_pre} passed subreddit/score filter, "
                    f"{file_post} passed quality gate "
                    f"(filtered {file_pre - file_post})"
                )

            except Exception as e:
                logger.error(f"Failed to process {pf.name}: {e}")
                DeadLetterQueue.add(
                    "arctic_shift_reddit",
                    {"file": str(pf), "error": str(e)},
                    str(e),
                )

        logger.info(
            f"Arctic Shift scan complete: {self._files_processed} files, "
            f"{self._rows_scanned} rows scanned, "
            f"{pre_quality_count} passed subreddit/score, "
            f"{self._rows_quality_filtered} dropped by quality gate "
            f"(score>{self.config.quality_min_score} AND "
            f"ratio>{self.config.quality_min_upvote_ratio}), "
            f"{self._rows_relevant} final relevant rows"
        )
        return relevant_rows

    def parse(self, raw_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse a Reddit post/comment into venue mention(s).

        A single post can mention multiple venues. Returns a dict
        with a 'mentions' list, or None if no venues detected.

        Detects is_local patterns and sets signalType accordingly:
        - Local authors -> signalType="local_recommendation" (3x downstream weight)
        - Others -> signalType="recommendation" or "mention"
        """
        # Get text content (posts have 'selftext', comments have 'body')
        text = raw_item.get("selftext") or raw_item.get("body") or ""
        title = raw_item.get("title") or ""
        full_text = f"{title}\n{text}" if title else text

        if not full_text.strip():
            return None

        # Detect city context
        city = detect_city(full_text)
        if city is None or city not in self.config.target_cities:
            return None

        # Extract venue names
        venues = extract_venue_names(full_text)
        if not venues:
            return None

        subreddit = (raw_item.get("subreddit") or "").lower()
        score = raw_item.get("score", 0) or 0
        if isinstance(score, str):
            try:
                score = int(score)
            except ValueError:
                score = 0
        author = raw_item.get("author") or "[deleted]"
        created_utc = raw_item.get("created_utc", 0) or 0
        if isinstance(created_utc, str):
            try:
                created_utc = int(float(created_utc))
            except ValueError:
                created_utc = 0

        # Build permalink
        post_id = raw_item.get("id") or raw_item.get("link_id", "").replace("t3_", "")
        comment_id = None
        if raw_item.get("body") is not None:
            # This is a comment
            comment_id = raw_item.get("id")
            post_id = (raw_item.get("link_id") or "").replace("t3_", "")

        permalink = raw_item.get("permalink") or ""
        if not permalink and post_id:
            permalink = f"/r/{subreddit}/comments/{post_id}"

        # Detect is_local for the whole post (applies to all venue mentions within it)
        is_local = detect_is_local(full_text)
        if is_local:
            self._local_posts_detected += 1
            logger.debug(
                f"Local author detected in post {post_id} "
                f"(subreddit={subreddit}, city={city})"
            )

        mentions: List[Dict[str, Any]] = []
        for venue_name in venues:
            sentiment = compute_sentiment(
                extract_text_excerpt(full_text, venue_name, max_len=300)
            )
            authority = compute_authority_score(score, subreddit, sentiment, is_local=is_local)
            excerpt = extract_text_excerpt(full_text, venue_name)

            # signalType: local authors get "local_recommendation" for 3x weighting.
            # Non-locals get "recommendation" (strong intent words present) or "mention".
            if is_local:
                signal_type = "local_recommendation"
            elif sentiment == "positive":
                signal_type = "recommendation"
            else:
                signal_type = "mention"

            mention = {
                "venue_name": venue_name,
                "city": city,
                "subreddit": subreddit,
                "post_id": post_id,
                "comment_id": comment_id,
                "score": score,
                "text_excerpt": excerpt,
                "sentiment": sentiment,
                "author": author,
                "created_utc": created_utc,
                "permalink": permalink,
                "authority_score": authority,
                "is_local": is_local,
                "signal_type": signal_type,
            }
            mentions.append(mention)

        if not mentions:
            return None

        return {
            "source_row": raw_item.get("id", ""),
            "city": city,
            "subreddit": subreddit,
            "is_local": is_local,
            "mentions": mentions,
        }

    def store(self, parsed_item: Dict[str, Any]) -> None:
        """
        Accumulate parsed venue mentions as QualitySignal-shaped rows.

        Actual DB persistence is handled by the pipeline orchestrator.
        """
        for mention in parsed_item.get("mentions", []):
            # Build a VenueMention for internal tracking
            vm = VenueMention(
                venue_name=mention["venue_name"],
                city=mention["city"],
                subreddit=mention["subreddit"],
                post_id=mention["post_id"],
                comment_id=mention.get("comment_id"),
                score=mention["score"],
                text_excerpt=mention["text_excerpt"],
                sentiment=mention["sentiment"],
                author=mention["author"],
                created_utc=mention["created_utc"],
                permalink=mention["permalink"],
                is_local=mention.get("is_local", False),
            )
            self._mentions.append(vm)

            # Build QualitySignal-shaped dict
            signal = {
                "activityNodeId": None,  # linked after entity resolution
                "sourceName": "reddit",
                "sourceUrl": f"https://reddit.com{mention['permalink']}"
                    if mention["permalink"]
                    else None,
                "sourceAuthority": mention["authority_score"],
                "signalType": mention.get("signal_type", "mention"),
                "sentiment": mention["sentiment"],
                "rawExcerpt": mention["text_excerpt"],
                "extractedAt": datetime.utcnow().isoformat(),
                "metadata": {
                    "venue_name": mention["venue_name"],
                    "city": mention["city"],
                    "subreddit": mention["subreddit"],
                    "reddit_score": mention["score"],
                    "author": mention["author"],
                    "created_utc": mention["created_utc"],
                    "post_id": mention["post_id"],
                    "comment_id": mention.get("comment_id"),
                    "is_local": mention.get("is_local", False),
                },
            }
            self._quality_signals.append(signal)

    # -- Public helpers -------------------------------------------------------

    def get_results(self) -> Dict[str, Any]:
        """
        Return collected QualitySignal rows and processing stats.

        Returns:
            {
                "quality_signals": List of QualitySignal-shaped dicts,
                "mentions": List of VenueMention dicts (for debugging/review),
                "stats": processing statistics,
            }
        """
        return {
            "quality_signals": list(self._quality_signals),
            "mentions": [
                {
                    "venue_name": m.venue_name,
                    "city": m.city,
                    "subreddit": m.subreddit,
                    "score": m.score,
                    "sentiment": m.sentiment,
                    "permalink": m.permalink,
                    "is_local": m.is_local,
                }
                for m in self._mentions
            ],
            "stats": {
                "files_processed": self._files_processed,
                "rows_scanned": self._rows_scanned,
                "rows_relevant": self._rows_relevant,
                "rows_quality_filtered": self._rows_quality_filtered,
                "local_posts_detected": self._local_posts_detected,
                "venues_extracted": len(self._mentions),
                "quality_signals": len(self._quality_signals),
                "by_city": self._count_by_city(),
                "by_subreddit": self._count_by_subreddit(),
            },
        }

    def get_signals_for_city(self, city: str) -> List[Dict[str, Any]]:
        """Filter quality signals for a specific city."""
        return [
            s for s in self._quality_signals
            if s.get("metadata", {}).get("city") == city
        ]

    def get_local_signals(self) -> List[Dict[str, Any]]:
        """Return only signals from self-identified local authors."""
        return [
            s for s in self._quality_signals
            if s.get("metadata", {}).get("is_local") is True
        ]

    def _count_by_city(self) -> Dict[str, int]:
        """Count mentions per city."""
        counts: Dict[str, int] = {}
        for m in self._mentions:
            counts[m.city] = counts.get(m.city, 0) + 1
        return counts

    def _count_by_subreddit(self) -> Dict[str, int]:
        """Count mentions per subreddit."""
        counts: Dict[str, int] = {}
        for m in self._mentions:
            counts[m.subreddit] = counts.get(m.subreddit, 0) + 1
        return counts

    def load_subreddit_archive(
        self,
        subreddit: str,
        *,
        target_cities: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Convenience method: load a single subreddit's archive.

        Looks for files matching the subreddit name in the parquet dir.

        Args:
            subreddit: Subreddit name (without r/ prefix).
            target_cities: Override target cities for this load.

        Returns:
            Dict with quality_signals, mentions, and stats.
        """
        sub_lower = subreddit.lower()

        # Override config for this run
        original_subs = self._target_subs
        original_cities = self.config.target_cities
        self._target_subs = {sub_lower}
        if target_cities:
            self.config.target_cities = target_cities

        # Reset accumulators
        self._mentions = []
        self._quality_signals = []
        self._files_processed = 0
        self._rows_scanned = 0
        self._rows_relevant = 0
        self._rows_quality_filtered = 0
        self._local_posts_detected = 0

        try:
            stats = self.run()
            results = self.get_results()
            results["stats"].update(stats)
            return results
        finally:
            # Restore original config
            self._target_subs = original_subs
            self.config.target_cities = original_cities
