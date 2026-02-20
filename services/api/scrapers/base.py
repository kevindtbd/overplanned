"""
Base scraper framework with retry, backoff, dead letter queue, and alerting.
All scrapers inherit from BaseScraper.
"""

import time
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar, Dict
from functools import wraps
import asyncio

logger = logging.getLogger(__name__)

# Dead letter queue path
DEAD_LETTER_PATH = Path("data/dead_letter.jsonl")
DEAD_LETTER_PATH.parent.mkdir(parents=True, exist_ok=True)

T = TypeVar('T')


@dataclass
class SourceRegistry:
    """Source registration metadata."""
    name: str
    base_url: str
    authority_score: float  # 0.0-1.0
    scrape_frequency_hours: int
    requests_per_minute: int = 30


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, requests_per_minute: int):
        self.requests_per_minute = requests_per_minute
        self.tokens = requests_per_minute
        self.last_refill = time.time()
        self.lock = asyncio.Lock() if asyncio.iscoroutinefunction else None

    def acquire(self) -> None:
        """Block until a token is available."""
        self._refill()
        while self.tokens < 1:
            time.sleep(0.1)
            self._refill()
        self.tokens -= 1

    async def acquire_async(self) -> None:
        """Async version of acquire."""
        self._refill()
        while self.tokens < 1:
            await asyncio.sleep(0.1)
            self._refill()
        self.tokens -= 1

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        tokens_to_add = elapsed * (self.requests_per_minute / 60.0)
        self.tokens = min(self.requests_per_minute, self.tokens + tokens_to_add)
        self.last_refill = now


def retry_with_backoff(max_attempts: int = 3, base_delay: float = 1.0):
    """
    Retry decorator with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts (default 3)
        base_delay: Base delay in seconds, doubles each retry (default 1.0)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_attempts} failed: {e}. "
                            f"Retrying in {delay}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"All {max_attempts} attempts failed: {e}")

            # All attempts failed
            raise last_exception

        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_attempts} failed: {e}. "
                            f"Retrying in {delay}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"All {max_attempts} attempts failed: {e}")

            raise last_exception

        # Return appropriate wrapper based on whether func is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


class DeadLetterQueue:
    """JSON-based dead letter queue for failed scrape items."""

    @staticmethod
    def add(source: str, item: Dict[str, Any], error: str) -> None:
        """Add a failed item to the dead letter queue."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "source": source,
            "error": str(error),
            "item": item
        }

        with open(DEAD_LETTER_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")

        logger.warning(f"Added item to dead letter queue: {source} - {error}")

    @staticmethod
    def read_all() -> list[Dict[str, Any]]:
        """Read all entries from the dead letter queue."""
        if not DEAD_LETTER_PATH.exists():
            return []

        with open(DEAD_LETTER_PATH, "r") as f:
            return [json.loads(line) for line in f if line.strip()]

    @staticmethod
    def clear() -> None:
        """Clear the dead letter queue."""
        if DEAD_LETTER_PATH.exists():
            DEAD_LETTER_PATH.unlink()


class BaseScraper(ABC):
    """
    Abstract base class for all scrapers.

    Provides:
    - Retry with exponential backoff
    - Rate limiting
    - Dead letter queue for failed items
    - Alerting on consecutive failures
    - Source registry pattern
    """

    # Source metadata (override in subclasses)
    SOURCE_REGISTRY: Optional[SourceRegistry] = None

    # User-Agent header
    USER_AGENT = "Overplanned/1.0 (Travel Planning Bot; +https://overplanned.travel)"

    def __init__(self):
        if self.SOURCE_REGISTRY is None:
            raise ValueError(f"{self.__class__.__name__} must define SOURCE_REGISTRY")

        self.rate_limiter = RateLimiter(self.SOURCE_REGISTRY.requests_per_minute)
        self.consecutive_failures = 0
        self._alert_threshold = 3

    @abstractmethod
    def scrape(self) -> list[Dict[str, Any]]:
        """
        Fetch raw data from the source.

        Returns:
            List of raw items (dicts, HTML, etc.)
        """
        pass

    @abstractmethod
    def parse(self, raw_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse a raw item into structured data.

        Args:
            raw_item: Raw data from scrape()

        Returns:
            Parsed data dict or None if parsing fails
        """
        pass

    @abstractmethod
    def store(self, parsed_item: Dict[str, Any]) -> None:
        """
        Store a parsed item (DB, Qdrant, etc.).

        Args:
            parsed_item: Structured data from parse()
        """
        pass

    @retry_with_backoff(max_attempts=3, base_delay=1.0)
    def _run_scrape(self) -> list[Dict[str, Any]]:
        """Internal method to scrape with retries."""
        # Rate limit before scraping
        self.rate_limiter.acquire()
        return self.scrape()

    def run(self) -> Dict[str, Any]:
        """
        Execute the full scrape → parse → store pipeline.

        Returns:
            Dict with stats: {success: int, failed: int, dead_letter: int}
        """
        stats = {"success": 0, "failed": 0, "dead_letter": 0}

        try:
            # Scrape with retries
            raw_items = self._run_scrape()
            logger.info(f"Scraped {len(raw_items)} items from {self.SOURCE_REGISTRY.name}")

            # Parse and store each item
            for raw_item in raw_items:
                try:
                    parsed = self.parse(raw_item)
                    if parsed:
                        self.store(parsed)
                        stats["success"] += 1
                    else:
                        stats["failed"] += 1
                except Exception as e:
                    stats["failed"] += 1
                    stats["dead_letter"] += 1
                    DeadLetterQueue.add(
                        self.SOURCE_REGISTRY.name,
                        raw_item,
                        str(e)
                    )

            # Reset failure counter on success
            self.consecutive_failures = 0

        except Exception as e:
            self.consecutive_failures += 1
            self._check_alert()
            raise

        return stats

    def _check_alert(self) -> None:
        """Check if we should alert on consecutive failures."""
        if self.consecutive_failures >= self._alert_threshold:
            error_msg = (
                f"ALERT: {self.SOURCE_REGISTRY.name} has failed "
                f"{self.consecutive_failures} consecutive times"
            )
            logger.warning(error_msg)

            # Sentry capture (import here to avoid hard dependency)
            try:
                import sentry_sdk
                sentry_sdk.capture_message(error_msg, level="warning")
            except ImportError:
                logger.debug("Sentry not available, skipping capture")

    def get_headers(self) -> Dict[str, str]:
        """Get HTTP headers with respectful User-Agent."""
        return {
            "User-Agent": self.USER_AGENT
        }
