"""
Scraper framework for Overplanned.

All scrapers inherit from BaseScraper and provide:
- Retry with exponential backoff
- Rate limiting
- Dead letter queue
- Alerting on failures
"""

from .base import (
    BaseScraper,
    SourceRegistry,
    RateLimiter,
    DeadLetterQueue,
    retry_with_backoff,
)

__all__ = [
    "BaseScraper",
    "SourceRegistry",
    "RateLimiter",
    "DeadLetterQueue",
    "retry_with_backoff",
]
