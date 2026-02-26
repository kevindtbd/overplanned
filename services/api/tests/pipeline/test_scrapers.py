"""
Unit tests for all scrapers: BlogRSS, AtlasObscura, ArcticShift.

Covers:
- Mock HTTP responses per scraper
- Retry on 500 → dead letter on permanent failure
- Rate limiting verification
- Correct QualitySignal output format
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from services.api.scrapers.base import (
    BaseScraper,
    DeadLetterQueue,
    RateLimiter,
    SourceRegistry,
    retry_with_backoff,
)
from services.api.scrapers.atlas_obscura import (
    AtlasObscuraScraper,
    _compute_hidden_gem_score,
    _map_category,
)
from services.api.scrapers.arctic_shift import (
    ArcticShiftScraper,
    compute_authority_score,
    compute_sentiment,
    detect_city,
    extract_venue_names,
)

from .conftest import (
    make_http_response,
    make_atlas_card_html,
)


# ===================================================================
# Rate limiter tests
# ===================================================================


class TestRateLimiter:
    def test_acquire_consumes_token(self):
        rl = RateLimiter(requests_per_minute=60)
        initial = rl.tokens
        rl.acquire()
        assert rl.tokens < initial

    def test_refill_adds_tokens_over_time(self):
        rl = RateLimiter(requests_per_minute=600)
        rl.tokens = 0
        # Simulate time passing
        rl.last_refill = time.time() - 1.0  # 1 second ago
        rl._refill()
        assert rl.tokens > 0

    def test_rate_limiter_never_exceeds_max(self):
        rl = RateLimiter(requests_per_minute=10)
        rl.last_refill = time.time() - 120  # way in the past
        rl._refill()
        assert rl.tokens <= rl.requests_per_minute


# ===================================================================
# Retry + dead letter tests
# ===================================================================


class TestRetryAndDeadLetter:
    def test_retry_with_backoff_succeeds_after_failures(self):
        call_count = 0

        @retry_with_backoff(max_attempts=3, base_delay=0.01)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "ok"

        result = flaky()
        assert result == "ok"
        assert call_count == 3

    def test_retry_exhausted_raises(self):
        @retry_with_backoff(max_attempts=2, base_delay=0.01)
        def always_fail():
            raise ConnectionError("permanent")

        with pytest.raises(ConnectionError):
            always_fail()

    def test_dead_letter_queue_add_and_read(self, tmp_path):
        dlq_path = tmp_path / "dead_letter.jsonl"
        with patch("services.api.scrapers.base.DEAD_LETTER_PATH", dlq_path):
            DeadLetterQueue.add("test_source", {"url": "http://example.com"}, "500 error")
            entries = DeadLetterQueue.read_all()
            assert len(entries) == 1
            assert entries[0]["source"] == "test_source"
            assert entries[0]["error"] == "500 error"

    def test_dead_letter_queue_clear(self, tmp_path):
        dlq_path = tmp_path / "dead_letter.jsonl"
        with patch("services.api.scrapers.base.DEAD_LETTER_PATH", dlq_path):
            DeadLetterQueue.add("src", {}, "err")
            DeadLetterQueue.clear()
            assert DeadLetterQueue.read_all() == []


# ===================================================================
# Atlas Obscura scraper tests
# ===================================================================


class TestAtlasObscuraScraper:
    def test_parse_valid_card(self):
        scraper = AtlasObscuraScraper(city="tokyo")
        raw = {
            "title": "Golden Gai",
            "slug": "golden-gai",
            "subtitle": "Tiny bars in Shinjuku",
            "detail_url": "https://www.atlasobscura.com/places/golden-gai",
            "location_text": "Shinjuku, Tokyo",
            "category": "bar",
            "visitors_count": 42,
            "been_here_count": 10,
            "want_to_visit_count": 200,
            "latitude": None,
            "longitude": None,
        }
        parsed = scraper.parse(raw)

        assert parsed is not None
        assert parsed["name"] == "Golden Gai"
        assert parsed["external_source"] == "atlas_obscura"
        assert len(parsed["quality_signals"]) == 1
        assert parsed["quality_signals"][0]["signal_type"] == "hidden_gem"

    def test_parse_empty_title_returns_none(self):
        scraper = AtlasObscuraScraper(city="tokyo")
        assert scraper.parse({"title": "", "slug": "x"}) is None

    def test_hidden_gem_score_low_visitors(self):
        score = _compute_hidden_gem_score({"visitors_count": 50, "been_here_count": 20})
        assert score >= 0.8  # low visitors + low been_here = high gem score

    def test_hidden_gem_score_high_visitors(self):
        score = _compute_hidden_gem_score({"visitors_count": 10000, "been_here_count": 5000})
        assert score < 0.6  # high visitors = less hidden

    def test_atlas_category_mapping(self):
        assert _map_category("Museum of Modern Art") == "culture"
        assert _map_category("Nature Reserve") == "nature"
        assert _map_category("SomeUnknownThing") == "attraction"


# ===================================================================
# Arctic Shift (Reddit) scraper tests
# ===================================================================


class TestArcticShiftScraper:
    def test_detect_city_austin(self):
        assert detect_city("I walked down South Congress and grabbed tacos on East Austin") == "austin"

    def test_detect_city_seattle(self):
        assert detect_city("I explored Ballard and Fremont in Seattle") == "seattle"

    def test_detect_city_none_for_unrelated(self):
        assert detect_city("I went to a conference in Las Vegas") is None

    def test_extract_venue_names_recommendation_pattern(self):
        text = "I definitely recommend Ichiran Ramen for dinner"
        names = extract_venue_names(text)
        assert any("Ichiran" in n for n in names)

    def test_extract_venue_names_bold_pattern(self):
        text = "We loved **Tsukiji Outer Market** for breakfast"
        names = extract_venue_names(text)
        assert any("Tsukiji" in n for n in names)

    def test_extract_venue_names_filters_stopwords(self):
        text = "I recommend Japan for vacation"
        names = extract_venue_names(text)
        assert not any(n.lower() == "japan" for n in names)

    def test_compute_sentiment_positive(self):
        assert compute_sentiment("This place was amazing and fantastic") == "positive"

    def test_compute_sentiment_negative(self):
        assert compute_sentiment("Terrible food, avoid this place") == "negative"

    def test_compute_sentiment_neutral(self):
        assert compute_sentiment("We went there on Tuesday") == "neutral"

    def test_compute_authority_score_high(self):
        score = compute_authority_score(score=500, subreddit="japantravel", sentiment="positive")
        assert 0.0 <= score <= 1.0
        assert score > 0.3  # high score + good sub + positive

    def test_compute_authority_score_low(self):
        score = compute_authority_score(score=1, subreddit="unknown_sub", sentiment="negative")
        assert score < 0.3

    def test_parse_extracts_mentions(self):
        scraper = ArcticShiftScraper(
            parquet_dir="/nonexistent",
            target_cities=["austin"],
        )
        raw = {
            "id": "abc123",
            "subreddit": "austinfood",
            "title": "Austin food trip report",
            "selftext": "I recommend Franklin BBQ on East Austin, it was amazing",
            "score": 50,
            "author": "traveler42",
            "created_utc": 1700000000,
            "permalink": "/r/austinfood/comments/abc123",
        }
        parsed = scraper.parse(raw)

        assert parsed is not None
        assert parsed["city"] == "austin"
        assert len(parsed["mentions"]) >= 1

    def test_store_accumulates_quality_signals(self):
        scraper = ArcticShiftScraper(
            parquet_dir="/nonexistent",
            target_cities=["austin"],
        )
        parsed = {
            "source_row": "test",
            "city": "austin",
            "subreddit": "austinfood",
            "mentions": [
                {
                    "venue_name": "Test Place",
                    "city": "austin",
                    "subreddit": "austinfood",
                    "post_id": "abc",
                    "comment_id": None,
                    "score": 10,
                    "text_excerpt": "Test excerpt",
                    "sentiment": "positive",
                    "author": "user",
                    "created_utc": 1700000000,
                    "permalink": "/r/austinfood/comments/abc",
                    "authority_score": 0.5,
                },
            ],
        }
        scraper.store(parsed)
        results = scraper.get_results()

        assert len(results["quality_signals"]) == 1
        signal = results["quality_signals"][0]
        assert signal["sourceName"] == "reddit"
        assert signal["signalType"] == "mention"
        assert signal["sentiment"] == "positive"
        assert signal["metadata"]["venue_name"] == "Test Place"
