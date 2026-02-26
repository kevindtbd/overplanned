"""
Shared fixtures for pipeline test suite.

Provides mock DB pools, HTTP responses, Qdrant clients, and
factory helpers for ActivityNode / QualitySignal test data.
"""

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# UUID / ID helpers
# ---------------------------------------------------------------------------

def make_id() -> str:
    """Generate a random UUID string."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Fake asyncpg pool / connection
# ---------------------------------------------------------------------------

class FakeRecord(dict):
    """Dict subclass that also supports attribute-style access like asyncpg.Record."""
    def __getitem__(self, key):
        return super().__getitem__(key)


def _make_record(**kwargs) -> FakeRecord:
    return FakeRecord(**kwargs)


class FakeConnection:
    """In-memory fake asyncpg connection for testing."""

    def __init__(self, pool: "FakePool"):
        self._pool = pool

    async def fetch(self, query: str, *args) -> list:
        return self._pool._fetch_results.get(query.strip()[:80], [])

    async def fetchrow(self, query: str, *args) -> Optional[FakeRecord]:
        rows = self._pool._fetchrow_results.get(query.strip()[:80])
        if rows is not None:
            return rows
        return None

    async def fetchval(self, query: str, *args):
        return self._pool._fetchval_results.get(query.strip()[:80], 0)

    async def execute(self, query: str, *args) -> str:
        self._pool._executed.append((query, args))
        return "UPDATE 0"

    async def executemany(self, query: str, args_list) -> None:
        for args in args_list:
            self._pool._executed.append((query, args))

    def transaction(self):
        return _FakeTransaction()


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass


class FakePool:
    """In-memory fake asyncpg pool for testing."""

    def __init__(self):
        self._fetch_results: dict[str, list] = {}
        self._fetchrow_results: dict[str, Optional[FakeRecord]] = {}
        self._fetchval_results: dict[str, Any] = {}
        self._executed: list[tuple] = []

    def acquire(self):
        return _FakePoolAcquire(self)

    async def fetch(self, query: str, *args) -> list:
        conn = FakeConnection(self)
        return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        conn = FakeConnection(self)
        return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        conn = FakeConnection(self)
        return await conn.fetchval(query, *args)

    async def execute(self, query: str, *args) -> str:
        conn = FakeConnection(self)
        return await conn.execute(query, *args)

    async def executemany(self, query: str, args_list) -> None:
        conn = FakeConnection(self)
        return await conn.executemany(query, args_list)

    async def close(self):
        pass


class _FakePoolAcquire:
    def __init__(self, pool: FakePool):
        self._pool = pool

    async def __aenter__(self) -> FakeConnection:
        return FakeConnection(self._pool)

    async def __aexit__(self, *exc):
        pass


@pytest.fixture
def fake_pool():
    """Provide a fresh FakePool for each test."""
    return FakePool()


# ---------------------------------------------------------------------------
# ActivityNode factory
# ---------------------------------------------------------------------------

def make_activity_node(
    *,
    node_id: Optional[str] = None,
    name: str = "Test Venue",
    canonical_name: Optional[str] = None,
    city: str = "tokyo",
    category: str = "dining",
    latitude: float = 35.6762,
    longitude: float = 139.6503,
    source_count: int = 1,
    foursquare_id: Optional[str] = None,
    google_place_id: Optional[str] = None,
    content_hash: Optional[str] = None,
    convergence_score: float = 0.0,
    authority_score: float = 0.0,
    is_canonical: bool = True,
    description_short: Optional[str] = None,
    price_level: Optional[int] = None,
    status: str = "active",
    created_at: Optional[datetime] = None,
    updated_at: Optional[datetime] = None,
) -> FakeRecord:
    """Factory for ActivityNode-shaped records."""
    now = datetime.now(timezone.utc)
    return _make_record(
        id=node_id or make_id(),
        name=name,
        canonicalName=canonical_name or name.strip().lower(),
        city=city,
        category=category,
        latitude=latitude,
        longitude=longitude,
        sourceCount=source_count,
        foursquareId=foursquare_id,
        googlePlaceId=google_place_id,
        contentHash=content_hash,
        convergenceScore=convergence_score,
        authorityScore=authority_score,
        isCanonical=is_canonical,
        descriptionShort=description_short,
        descriptionLong=None,
        priceLevel=price_level,
        status=status,
        createdAt=created_at or now,
        updatedAt=updated_at or now,
        vibe_tag_slugs=[],
    )


# ---------------------------------------------------------------------------
# QualitySignal factory
# ---------------------------------------------------------------------------

def make_quality_signal(
    *,
    signal_id: Optional[str] = None,
    activity_node_id: str = "00000000-0000-0000-0000-000000000000",
    source_name: str = "foursquare",
    source_url: Optional[str] = None,
    source_authority: float = 0.75,
    signal_type: str = "mention",
    raw_excerpt: Optional[str] = "Great place to visit",
    extracted_at: Optional[datetime] = None,
) -> FakeRecord:
    """Factory for QualitySignal-shaped records."""
    now = datetime.now(timezone.utc)
    return _make_record(
        id=signal_id or make_id(),
        activityNodeId=activity_node_id,
        sourceName=source_name,
        sourceUrl=source_url,
        sourceAuthority=source_authority,
        signalType=signal_type,
        rawExcerpt=raw_excerpt,
        extractedAt=extracted_at or now,
        createdAt=now,
    )


# ---------------------------------------------------------------------------
# HTTP mocking helpers
# ---------------------------------------------------------------------------

def make_http_response(
    status_code: int = 200,
    json_body: Optional[dict] = None,
    text_body: str = "",
    headers: Optional[dict] = None,
) -> MagicMock:
    """Create a mock HTTP response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}

    if json_body is not None:
        resp.json.return_value = json_body
        resp.text = json.dumps(json_body)
    else:
        resp.text = text_body
        resp.json.side_effect = json.JSONDecodeError("No JSON", "", 0)

    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(
            f"HTTP {status_code}"
        )
    else:
        resp.raise_for_status.return_value = None

    return resp


# ---------------------------------------------------------------------------
# Atlas Obscura HTML factory
# ---------------------------------------------------------------------------

def make_atlas_card_html(
    title: str = "Hidden Temple",
    subtitle: str = "An ancient hidden temple",
    slug: str = "hidden-temple",
    location: str = "Tokyo, Japan",
    category: str = "religion",
) -> str:
    """Generate minimal Atlas Obscura card HTML for testing."""
    return f"""
    <div class="content-card">
        <a href="/places/{slug}">
            <h3 class="content-card-title">{title}</h3>
        </a>
        <p class="subtitle">{subtitle}</p>
        <span class="place">{location}</span>
        <span class="category">{category}</span>
    </div>
    """


# ---------------------------------------------------------------------------
# Checkpoint / progress helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_progress_dir(tmp_path):
    """Override PROGRESS_DIR with a temp directory for checkpoint tests."""
    progress_dir = tmp_path / "seed_progress"
    progress_dir.mkdir()
    return progress_dir


# ---------------------------------------------------------------------------
# Mock embedding service
# ---------------------------------------------------------------------------

class FakeEmbeddingService:
    """Mock embedding service that returns zero vectors of correct dimension."""

    def __init__(self, dim: int = 768):
        self.dim = dim
        self.calls: list[tuple] = []

    def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
        is_query: bool = False,
    ) -> list[list[float]]:
        self.calls.append((texts, batch_size, is_query))
        return [[0.0] * self.dim for _ in texts]


@pytest.fixture
def fake_embedding_service():
    return FakeEmbeddingService()


# ---------------------------------------------------------------------------
# Qdrant mock
# ---------------------------------------------------------------------------

class FakeQdrantCollection:
    """Tracks points upserted to a fake Qdrant collection."""

    def __init__(self):
        self.points: dict[str, dict] = {}
        self.points_count = 0


class FakeQdrantClient:
    """In-memory fake Qdrant client."""

    def __init__(self):
        self.collections: dict[str, FakeQdrantCollection] = {}

    async def get_collections(self):
        class FakeCollections:
            def __init__(self, names):
                self.collections = [type("C", (), {"name": n})() for n in names]
        return FakeCollections(list(self.collections.keys()))

    async def create_collection(self, collection_name, vectors_config=None):
        self.collections[collection_name] = FakeQdrantCollection()

    async def get_collection(self, collection_name):
        col = self.collections.get(collection_name, FakeQdrantCollection())
        return type("Info", (), {"points_count": col.points_count})()

    async def upsert(self, collection_name, points, wait=True):
        col = self.collections.setdefault(collection_name, FakeQdrantCollection())
        for p in points:
            col.points[p.id] = {"vector": p.vector, "payload": p.payload}
        col.points_count = len(col.points)

    async def delete(self, collection_name, points_selector):
        col = self.collections.get(collection_name)
        if col:
            for pid in points_selector:
                col.points.pop(pid, None)
            col.points_count = len(col.points)

    async def close(self):
        pass


@pytest.fixture
def fake_qdrant():
    return FakeQdrantClient()


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def days_ago(n: int) -> datetime:
    """Return a datetime n days in the past."""
    return datetime.now(timezone.utc) - timedelta(days=n)
