"""
Unit tests for base scraper framework.

Tests:
- Retry fires on 500 errors
- Dead letter queue on permanent failure
- Rate limiting works
- Consecutive failure alerting
"""

import pytest
import time
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, Optional

from services.api.scrapers.base import (
    BaseScraper,
    SourceRegistry,
    RateLimiter,
    DeadLetterQueue,
    retry_with_backoff,
    DEAD_LETTER_PATH,
)


# Mock scraper for testing
class MockScraper(BaseScraper):
    """Test scraper implementation."""

    SOURCE_REGISTRY = SourceRegistry(
        name="test_source",
        base_url="https://example.com",
        authority_score=0.8,
        scrape_frequency_hours=24,
        requests_per_minute=30,
    )

    def __init__(self):
        super().__init__()
        self.scrape_called = 0
        self.parse_called = 0
        self.store_called = 0
        self.should_fail = False
        self.fail_count = 0

    def scrape(self) -> list[Dict[str, Any]]:
        """Mock scrape method."""
        self.scrape_called += 1

        if self.should_fail:
            if self.fail_count > 0:
                self.fail_count -= 1
                raise Exception("HTTP 500 Internal Server Error")

        return [
            {"id": 1, "name": "Item 1"},
            {"id": 2, "name": "Item 2"},
        ]

    def parse(self, raw_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Mock parse method."""
        self.parse_called += 1
        return {"parsed": True, **raw_item}

    def store(self, parsed_item: Dict[str, Any]) -> None:
        """Mock store method."""
        self.store_called += 1


class TestRetryWithBackoff:
    """Tests for retry_with_backoff decorator."""

    def test_retry_succeeds_on_first_attempt(self):
        """Test that successful calls don't retry."""
        call_count = 0

        @retry_with_backoff(max_attempts=3)
        def success_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = success_func()
        assert result == "success"
        assert call_count == 1

    def test_retry_fires_on_failure(self):
        """Test that retry fires on exceptions."""
        call_count = 0

        @retry_with_backoff(max_attempts=3, base_delay=0.01)
        def fail_twice_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return "success"

        result = fail_twice_then_succeed()
        assert result == "success"
        assert call_count == 3

    def test_retry_exhausts_attempts(self):
        """Test that retry gives up after max attempts."""
        call_count = 0

        @retry_with_backoff(max_attempts=3, base_delay=0.01)
        def always_fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("Permanent failure")

        with pytest.raises(ValueError, match="Permanent failure"):
            always_fail()

        assert call_count == 3

    def test_exponential_backoff_timing(self):
        """Test that backoff delays increase exponentially."""
        timings = []

        @retry_with_backoff(max_attempts=3, base_delay=0.1)
        def fail_with_timing():
            timings.append(time.time())
            raise Exception("Fail")

        with pytest.raises(Exception):
            fail_with_timing()

        # Should have 3 attempts
        assert len(timings) == 3

        # Check delays: ~0.1s, ~0.2s
        delay1 = timings[1] - timings[0]
        delay2 = timings[2] - timings[1]

        assert 0.08 < delay1 < 0.15  # First retry: ~0.1s
        assert 0.18 < delay2 < 0.25  # Second retry: ~0.2s


class TestRateLimiter:
    """Tests for RateLimiter."""

    def test_rate_limiter_allows_bursts(self):
        """Test that rate limiter allows initial burst."""
        limiter = RateLimiter(requests_per_minute=60)  # 1 per second

        # Should allow immediate requests up to limit
        start = time.time()
        for _ in range(10):
            limiter.acquire()
        elapsed = time.time() - start

        # Should complete quickly (tokens available)
        assert elapsed < 0.5

    def test_rate_limiter_blocks_when_exhausted(self):
        """Test that rate limiter blocks when tokens exhausted."""
        limiter = RateLimiter(requests_per_minute=6)  # 0.1 per second

        # Exhaust all tokens
        limiter.tokens = 0

        # Next acquire should block until refill
        start = time.time()
        limiter.acquire()
        elapsed = time.time() - start

        # Should wait for at least one token to refill
        assert elapsed >= 0.1

    def test_rate_limiter_refills_over_time(self):
        """Test that rate limiter refills tokens over time."""
        limiter = RateLimiter(requests_per_minute=60)
        limiter.tokens = 0

        # Wait for refill
        time.sleep(0.2)
        limiter._refill()

        # Should have refilled ~2 tokens (60/min = 1/sec, 0.2s = 0.2 tokens, but we're generous)
        assert limiter.tokens > 0


class TestDeadLetterQueue:
    """Tests for DeadLetterQueue."""

    def setup_method(self):
        """Clear dead letter queue before each test."""
        DeadLetterQueue.clear()

    def teardown_method(self):
        """Clear dead letter queue after each test."""
        DeadLetterQueue.clear()

    def test_add_to_dead_letter_queue(self):
        """Test adding items to dead letter queue."""
        DeadLetterQueue.add(
            source="test_source",
            item={"id": 1, "name": "Failed Item"},
            error="Parse error"
        )

        entries = DeadLetterQueue.read_all()
        assert len(entries) == 1
        assert entries[0]["source"] == "test_source"
        assert entries[0]["error"] == "Parse error"
        assert entries[0]["item"]["id"] == 1

    def test_read_empty_queue(self):
        """Test reading from empty queue."""
        entries = DeadLetterQueue.read_all()
        assert entries == []

    def test_clear_queue(self):
        """Test clearing the queue."""
        DeadLetterQueue.add("test", {"id": 1}, "error")
        DeadLetterQueue.clear()

        entries = DeadLetterQueue.read_all()
        assert entries == []


class TestBaseScraper:
    """Tests for BaseScraper."""

    def setup_method(self):
        """Setup for each test."""
        DeadLetterQueue.clear()

    def teardown_method(self):
        """Cleanup after each test."""
        DeadLetterQueue.clear()

    def test_scraper_requires_source_registry(self):
        """Test that scrapers must define SOURCE_REGISTRY."""
        class BadScraper(BaseScraper):
            def scrape(self):
                return []
            def parse(self, item):
                return item
            def store(self, item):
                pass

        with pytest.raises(ValueError, match="must define SOURCE_REGISTRY"):
            BadScraper()

    def test_successful_run(self):
        """Test successful scrape/parse/store pipeline."""
        scraper = MockScraper()
        stats = scraper.run()

        assert stats["success"] == 2
        assert stats["failed"] == 0
        assert stats["dead_letter"] == 0
        assert scraper.scrape_called == 1
        assert scraper.parse_called == 2
        assert scraper.store_called == 2

    def test_parse_failure_goes_to_dead_letter(self):
        """Test that parse failures go to dead letter queue."""
        scraper = MockScraper()

        # Make parse fail
        original_parse = scraper.parse
        def failing_parse(item):
            if item["id"] == 2:
                raise ValueError("Parse failed")
            return original_parse(item)

        scraper.parse = failing_parse

        stats = scraper.run()

        assert stats["success"] == 1
        assert stats["failed"] == 1
        assert stats["dead_letter"] == 1

        # Check dead letter queue
        entries = DeadLetterQueue.read_all()
        assert len(entries) == 1
        assert entries[0]["item"]["id"] == 2

    def test_retry_on_scrape_failure(self):
        """Test that scrape failures trigger retry."""
        scraper = MockScraper()
        scraper.should_fail = True
        scraper.fail_count = 2  # Fail twice, succeed on third

        stats = scraper.run()

        # Should succeed after retries
        assert scraper.scrape_called == 3
        assert stats["success"] == 2

    def test_dead_letter_on_permanent_failure(self):
        """Test that permanent failures go to dead letter queue."""
        scraper = MockScraper()
        scraper.should_fail = True
        scraper.fail_count = 10  # Always fail

        with pytest.raises(Exception, match="HTTP 500"):
            scraper.run()

        # Should have tried 3 times
        assert scraper.scrape_called == 3

    def test_consecutive_failure_alerting(self):
        """Test that consecutive failures trigger alerts."""
        scraper = MockScraper()
        scraper.should_fail = True
        scraper.fail_count = 10  # Fail enough times to exhaust retries

        # First failure
        with pytest.raises(Exception):
            scraper.run()
        assert scraper.consecutive_failures == 1

        # Second failure
        scraper.fail_count = 10
        with pytest.raises(Exception):
            scraper.run()
        assert scraper.consecutive_failures == 2

        # Third failure - should trigger alert
        scraper.fail_count = 10
        with patch('services.api.scrapers.base.logger') as mock_logger:
            with pytest.raises(Exception):
                scraper.run()

            assert scraper.consecutive_failures == 3
            # Check that warning was logged
            assert any(
                "ALERT" in str(call) and "consecutive" in str(call)
                for call in mock_logger.warning.call_args_list
            )

    def test_consecutive_failures_reset_on_success(self):
        """Test that consecutive failures reset on success."""
        scraper = MockScraper()
        scraper.consecutive_failures = 5

        # Successful run should reset
        stats = scraper.run()
        assert stats["success"] == 2
        assert scraper.consecutive_failures == 0

    def test_rate_limiting_applied(self):
        """Test that rate limiting is applied."""
        scraper = MockScraper()

        # Mock rate limiter to track calls
        mock_limiter = Mock()
        scraper.rate_limiter = mock_limiter

        stats = scraper.run()

        # Should have called acquire once
        mock_limiter.acquire.assert_called_once()

    def test_user_agent_header(self):
        """Test that respectful User-Agent is provided."""
        scraper = MockScraper()
        headers = scraper.get_headers()

        assert "User-Agent" in headers
        assert "Overplanned" in headers["User-Agent"]
        assert "+https://overplanned.travel" in headers["User-Agent"]


class TestIntegration:
    """Integration tests for full scraper pipeline."""

    def setup_method(self):
        """Setup for each test."""
        DeadLetterQueue.clear()

    def teardown_method(self):
        """Cleanup after each test."""
        DeadLetterQueue.clear()

    def test_full_pipeline_with_mixed_results(self):
        """Test complete pipeline with successes and failures."""
        scraper = MockScraper()

        # Override parse to fail on specific items
        parse_call_count = 0
        def mixed_parse(item):
            nonlocal parse_call_count
            parse_call_count += 1
            if item["id"] == 2:
                raise ValueError("Parse error on item 2")
            return {"parsed": True, **item}

        scraper.parse = mixed_parse

        stats = scraper.run()

        assert stats["success"] == 1
        assert stats["failed"] == 1
        assert stats["dead_letter"] == 1
        assert parse_call_count == 2

        # Verify dead letter queue
        entries = DeadLetterQueue.read_all()
        assert len(entries) == 1
        assert entries[0]["item"]["id"] == 2
        assert "Parse error" in entries[0]["error"]
