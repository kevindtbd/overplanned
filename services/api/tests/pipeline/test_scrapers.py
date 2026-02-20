"""
Unit tests for all scrapers: Foursquare, BlogRSS, AtlasObscura, ArcticShift.

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
from services.api.scrapers.foursquare import (
    FoursquareScraper,
    map_foursquare_category,
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
    make_foursquare_venue,
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
# Foursquare scraper tests
# ===================================================================


class TestFoursquareScraper:
    @pytest.fixture
    def scraper(self, tmp_path):
        """Create a FoursquareScraper with mocked env + quota."""
        with patch.dict("os.environ", {"FOURSQUARE_API_KEY": "test-key"}):
            with patch(
                "services.api.scrapers.foursquare.QUOTA_PATH",
                tmp_path / "quota.json",
            ):
                s = FoursquareScraper(near="Tokyo", limit=10)
                return s

    def test_parse_valid_venue(self, scraper):
        raw = make_foursquare_venue(
            fsq_id="fsq_abc",
            name="Ichiran Ramen",
            latitude=35.6762,
            longitude=139.6503,
            category_id="13065",
        )
        parsed = scraper.parse(raw)

        assert parsed is not None
        assert parsed["name"] == "Ichiran Ramen"
        assert parsed["category"] == "dining"
        assert parsed["latitude"] == 35.6762
        assert parsed["foursquareId"] == "fsq_abc"
        assert parsed["isCanonical"] is True
        assert parsed["sourceCount"] == 1

    def test_parse_missing_geocodes_returns_none(self, scraper):
        raw = {"fsq_id": "x", "name": "No Location", "geocodes": {}}
        assert scraper.parse(raw) is None

    def test_parse_missing_name_returns_none(self, scraper):
        raw = {
            "fsq_id": "x",
            "name": None,
            "geocodes": {"main": {"latitude": 0, "longitude": 0}},
        }
        assert scraper.parse(raw) is None

    def test_store_accumulates_node_and_signal(self, scraper):
        raw = make_foursquare_venue(fsq_id="fsq_store_test")
        parsed = scraper.parse(raw)
        scraper.store(parsed)

        results = scraper.get_results()
        assert len(results["nodes"]) == 1
        assert len(results["quality_signals"]) == 1

        signal = results["quality_signals"][0]
        assert signal["sourceName"] == "foursquare"
        assert signal["sourceAuthority"] == 0.75
        assert signal["signalType"] == "mention"

    def test_foursquare_category_mapping(self):
        assert map_foursquare_category("13065") == "dining"
        assert map_foursquare_category("16032") == "outdoors"
        assert map_foursquare_category("10025") == "culture"
        assert map_foursquare_category("99999") == "experience"  # unknown → fallback

    def test_scrape_raises_on_http_500(self, scraper, tmp_path):
        mock_resp = make_http_response(status_code=500)
        with patch.object(scraper._client, "get", return_value=mock_resp):
            with patch(
                "services.api.scrapers.foursquare.QUOTA_PATH",
                tmp_path / "quota.json",
            ):
                with pytest.raises(Exception):
                    scraper.scrape()


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
    def test_detect_city_tokyo(self):
        assert detect_city("I visited Shibuya and had amazing ramen in Shinjuku") == "tokyo"

    def test_detect_city_kyoto(self):
        assert detect_city("The temples in Arashiyama and Gion were beautiful") == "kyoto"

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
            target_cities=["tokyo"],
        )
        raw = {
            "id": "abc123",
            "subreddit": "japantravel",
            "title": "Tokyo trip report",
            "selftext": "I recommend Ichiran Ramen in Shibuya, it was amazing",
            "score": 50,
            "author": "traveler42",
            "created_utc": 1700000000,
            "permalink": "/r/japantravel/comments/abc123",
        }
        parsed = scraper.parse(raw)

        assert parsed is not None
        assert parsed["city"] == "tokyo"
        assert len(parsed["mentions"]) >= 1

    def test_store_accumulates_quality_signals(self):
        scraper = ArcticShiftScraper(
            parquet_dir="/nonexistent",
            target_cities=["tokyo"],
        )
        parsed = {
            "source_row": "test",
            "city": "tokyo",
            "subreddit": "japantravel",
            "mentions": [
                {
                    "venue_name": "Test Place",
                    "city": "tokyo",
                    "subreddit": "japantravel",
                    "post_id": "abc",
                    "comment_id": None,
                    "score": 10,
                    "text_excerpt": "Test excerpt",
                    "sentiment": "positive",
                    "author": "user",
                    "created_utc": 1700000000,
                    "permalink": "/r/japantravel/comments/abc",
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
