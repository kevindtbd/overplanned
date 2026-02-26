"""
Qdrant vector sync for ActivityNodes.

Generates embeddings via nomic-embed-text-v1.5 (768 dim) and upserts
canonical ActivityNodes into the Qdrant ``activity_nodes`` collection.

Two sync modes:
  - Full sync: re-embed and upsert ALL canonical nodes.
  - Incremental sync: only nodes with updatedAt > last sync timestamp.

Embedding text formula:
    "{name}. {descriptionShort}. Category: {category}. Vibes: {vibe_tag_slugs}"

Payload stored alongside each vector:
    id, city, category, priceLevel, convergenceScore, authorityScore,
    vibeTagSlugs, isCanonical

Runs after convergence scoring (M-008) and before city seeder (M-010).
"""

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import asyncpg
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

COLLECTION_NAME = "activity_nodes"
VECTOR_DIM = 768
BATCH_SIZE = 100  # nodes per Qdrant upsert batch
EMBED_BATCH_SIZE = 32  # texts per embedding batch

# Env-based Qdrant connection (matches foundation config.py pattern)
_QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
_QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "") or None


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@dataclass
class SyncStats:
    """Summary of a Qdrant sync run."""
    mode: str = "full"  # "full" or "incremental"
    nodes_fetched: int = 0
    nodes_embedded: int = 0
    nodes_upserted: int = 0
    nodes_skipped: int = 0
    errors: int = 0
    embedding_time_s: float = 0.0
    upsert_time_s: float = 0.0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_details: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Embedding text construction
# ---------------------------------------------------------------------------

def build_embedding_text(
    name: str,
    description_short: Optional[str],
    category: str,
    vibe_tag_slugs: list[str],
) -> str:
    """
    Build the text that gets embedded for a node.

    Formula: "{name}. {descriptionShort}. Category: {category}. Vibes: {vibes}"
    Omits empty segments.
    """
    parts = [name]
    if description_short:
        parts.append(description_short)
    parts.append(f"Category: {category}")
    if vibe_tag_slugs:
        parts.append(f"Vibes: {', '.join(vibe_tag_slugs)}")
    return ". ".join(parts)


# ---------------------------------------------------------------------------
# Qdrant collection management
# ---------------------------------------------------------------------------

async def ensure_collection(client: AsyncQdrantClient) -> None:
    """Create the activity_nodes collection if it doesn't exist."""
    collections = await client.get_collections()
    existing = {c.name for c in collections.collections}

    if COLLECTION_NAME in existing:
        logger.info("Collection %s already exists", COLLECTION_NAME)
        return

    await client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=VECTOR_DIM,
            distance=Distance.COSINE,
        ),
    )
    logger.info("Created collection %s (%d-dim, cosine)", COLLECTION_NAME, VECTOR_DIM)


# ---------------------------------------------------------------------------
# DB queries
# ---------------------------------------------------------------------------

async def _fetch_canonical_nodes(
    pool: asyncpg.Pool,
    *,
    since: Optional[datetime] = None,
    node_ids: Optional[list[str]] = None,
) -> list[asyncpg.Record]:
    """
    Fetch canonical ActivityNodes with their vibe tag slugs.

    Args:
        since: If set, only nodes with updatedAt > since (incremental mode).
        node_ids: If set, only these specific node IDs.
    """
    base_query = """
        SELECT
            an.id,
            an.name,
            an.city,
            an.category,
            an."descriptionShort",
            an."priceLevel",
            an."convergenceScore",
            an."authorityScore",
            an."isCanonical",
            an."updatedAt",
            COALESCE(
                array_agg(DISTINCT vt.slug) FILTER (WHERE vt.slug IS NOT NULL),
                ARRAY[]::text[]
            ) AS vibe_tag_slugs
        FROM activity_nodes an
        LEFT JOIN activity_node_vibe_tags anvt ON anvt."activityNodeId" = an.id
        LEFT JOIN vibe_tags vt ON vt.id = anvt."vibeTagId"
        WHERE an."isCanonical" = true
    """

    params: list = []
    param_idx = 1

    if since is not None:
        base_query += f' AND an."updatedAt" > ${param_idx}'
        params.append(since)
        param_idx += 1

    if node_ids is not None:
        base_query += f" AND an.id = ANY(${param_idx}::text[])"
        params.append(node_ids)
        param_idx += 1

    base_query += """
        GROUP BY an.id
        ORDER BY an."updatedAt" ASC
    """

    async with pool.acquire() as conn:
        return await conn.fetch(base_query, *params)


async def _get_canonical_count(pool: asyncpg.Pool) -> int:
    """Count canonical ActivityNodes in Postgres."""
    async with pool.acquire() as conn:
        return await conn.fetchval(
            'SELECT COUNT(*) FROM activity_nodes WHERE "isCanonical" = true'
        )


# ---------------------------------------------------------------------------
# Core sync logic
# ---------------------------------------------------------------------------

async def _embed_and_upsert(
    client: AsyncQdrantClient,
    embedding_service,
    nodes: list[asyncpg.Record],
    stats: SyncStats,
) -> None:
    """Embed a batch of nodes and upsert to Qdrant."""

    # Build embedding texts
    texts: list[str] = []
    valid_nodes: list[asyncpg.Record] = []
    for node in nodes:
        text = build_embedding_text(
            name=node["name"],
            description_short=node["descriptionShort"],
            category=node["category"],
            vibe_tag_slugs=list(node["vibe_tag_slugs"]),
        )
        texts.append(text)
        valid_nodes.append(node)

    if not texts:
        return

    # Generate embeddings
    t0 = time.monotonic()
    try:
        vectors = embedding_service.embed_batch(
            texts,
            batch_size=EMBED_BATCH_SIZE,
            is_query=False,  # indexing documents, not queries
        )
        stats.embedding_time_s += time.monotonic() - t0
        stats.nodes_embedded += len(vectors)
    except Exception as exc:
        stats.errors += len(texts)
        stats.error_details.append(f"Embedding batch failed: {exc}")
        logger.exception("Embedding batch failed (%d texts)", len(texts))
        return

    # Build Qdrant points
    points: list[PointStruct] = []
    for node, vector in zip(valid_nodes, vectors):
        node_id = node["id"]
        # Use UUID as Qdrant point ID (string format)
        payload = {
            "id": node_id,
            "city": (node["city"] or "").lower(),
            "category": node["category"],
            "price_level": node["priceLevel"],
            "convergence_score": float(node["convergenceScore"] or 0),
            "authority_score": float(node["authorityScore"] or 0),
            "vibe_tag_slugs": list(node["vibe_tag_slugs"]),
            "is_canonical": True,
        }
        points.append(PointStruct(
            id=node_id,
            vector=vector,
            payload=payload,
        ))

    # Upsert to Qdrant
    t1 = time.monotonic()
    try:
        await client.upsert(
            collection_name=COLLECTION_NAME,
            points=points,
            wait=True,
        )
        stats.upsert_time_s += time.monotonic() - t1
        stats.nodes_upserted += len(points)
    except Exception as exc:
        stats.errors += len(points)
        stats.error_details.append(f"Qdrant upsert failed: {exc}")
        logger.exception("Qdrant upsert failed (%d points)", len(points))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_full_sync(
    pool: asyncpg.Pool,
    embedding_service,
    *,
    qdrant_url: Optional[str] = None,
    qdrant_api_key: Optional[str] = None,
) -> SyncStats:
    """
    Full sync: re-embed and upsert ALL canonical ActivityNodes.

    Args:
        pool: asyncpg connection pool.
        embedding_service: EmbeddingService instance (from foundation).
        qdrant_url: Override Qdrant URL (default from env).
        qdrant_api_key: Override Qdrant API key (default from env).

    Returns:
        SyncStats with processing counts.
    """
    stats = SyncStats(mode="full", started_at=datetime.now(timezone.utc))

    url = qdrant_url or _QDRANT_URL
    api_key = qdrant_api_key or _QDRANT_API_KEY

    client = AsyncQdrantClient(url=url, api_key=api_key, timeout=30)
    try:
        await ensure_collection(client)

        nodes = await _fetch_canonical_nodes(pool)
        stats.nodes_fetched = len(nodes)
        logger.info("Full sync: %d canonical nodes to process", len(nodes))

        # Process in batches
        for offset in range(0, len(nodes), BATCH_SIZE):
            batch = nodes[offset : offset + BATCH_SIZE]
            await _embed_and_upsert(client, embedding_service, batch, stats)
            logger.info(
                "Full sync progress: %d/%d upserted",
                stats.nodes_upserted,
                stats.nodes_fetched,
            )

        # Validate: Qdrant count should match Postgres canonical count
        await _validate_parity(client, pool, stats)

    finally:
        await client.close()

    stats.finished_at = datetime.now(timezone.utc)
    _log_summary(stats)
    return stats


async def run_incremental_sync(
    pool: asyncpg.Pool,
    embedding_service,
    since: datetime,
    *,
    qdrant_url: Optional[str] = None,
    qdrant_api_key: Optional[str] = None,
) -> SyncStats:
    """
    Incremental sync: only nodes updated after `since`.

    Args:
        pool: asyncpg connection pool.
        embedding_service: EmbeddingService instance (from foundation).
        since: Only sync nodes with updatedAt > this timestamp.
        qdrant_url: Override Qdrant URL (default from env).
        qdrant_api_key: Override Qdrant API key (default from env).

    Returns:
        SyncStats with processing counts.
    """
    stats = SyncStats(mode="incremental", started_at=datetime.now(timezone.utc))

    url = qdrant_url or _QDRANT_URL
    api_key = qdrant_api_key or _QDRANT_API_KEY

    client = AsyncQdrantClient(url=url, api_key=api_key, timeout=30)
    try:
        await ensure_collection(client)

        nodes = await _fetch_canonical_nodes(pool, since=since)
        stats.nodes_fetched = len(nodes)
        logger.info(
            "Incremental sync: %d nodes changed since %s",
            len(nodes),
            since.isoformat(),
        )

        if not nodes:
            logger.info("No changed nodes — nothing to sync")
            stats.finished_at = datetime.now(timezone.utc)
            return stats

        for offset in range(0, len(nodes), BATCH_SIZE):
            batch = nodes[offset : offset + BATCH_SIZE]
            await _embed_and_upsert(client, embedding_service, batch, stats)

    finally:
        await client.close()

    stats.finished_at = datetime.now(timezone.utc)
    _log_summary(stats)
    return stats


async def sync_specific_nodes(
    pool: asyncpg.Pool,
    embedding_service,
    node_ids: list[str],
    *,
    qdrant_url: Optional[str] = None,
    qdrant_api_key: Optional[str] = None,
) -> SyncStats:
    """
    Sync specific nodes by ID (e.g., after entity resolution merge).

    Args:
        pool: asyncpg connection pool.
        embedding_service: EmbeddingService instance.
        node_ids: Specific ActivityNode IDs to sync.

    Returns:
        SyncStats with processing counts.
    """
    stats = SyncStats(mode="specific", started_at=datetime.now(timezone.utc))

    url = qdrant_url or _QDRANT_URL
    api_key = qdrant_api_key or _QDRANT_API_KEY

    client = AsyncQdrantClient(url=url, api_key=api_key, timeout=30)
    try:
        await ensure_collection(client)

        nodes = await _fetch_canonical_nodes(pool, node_ids=node_ids)
        stats.nodes_fetched = len(nodes)

        # Nodes not found (deleted or no longer canonical) should be removed from Qdrant
        fetched_ids = {r["id"] for r in nodes}
        missing_ids = [nid for nid in node_ids if nid not in fetched_ids]
        if missing_ids:
            try:
                await client.delete(
                    collection_name=COLLECTION_NAME,
                    points_selector=missing_ids,
                )
                stats.nodes_skipped += len(missing_ids)
                logger.info(
                    "Removed %d non-canonical nodes from Qdrant", len(missing_ids)
                )
            except Exception as exc:
                stats.errors += 1
                stats.error_details.append(f"Delete failed: {exc}")
                logger.exception("Failed to delete non-canonical nodes from Qdrant")

        if nodes:
            for offset in range(0, len(nodes), BATCH_SIZE):
                batch = nodes[offset : offset + BATCH_SIZE]
                await _embed_and_upsert(client, embedding_service, batch, stats)

    finally:
        await client.close()

    stats.finished_at = datetime.now(timezone.utc)
    _log_summary(stats)
    return stats


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

async def validate_parity(
    pool: asyncpg.Pool,
    *,
    qdrant_url: Optional[str] = None,
    qdrant_api_key: Optional[str] = None,
) -> tuple[int, int, bool]:
    """
    Validate Qdrant count matches Postgres canonical count.

    Returns:
        (postgres_count, qdrant_count, is_match)
    """
    url = qdrant_url or _QDRANT_URL
    api_key = qdrant_api_key or _QDRANT_API_KEY

    pg_count = await _get_canonical_count(pool)

    client = AsyncQdrantClient(url=url, api_key=api_key, timeout=10)
    try:
        info = await client.get_collection(COLLECTION_NAME)
        qdrant_count = info.points_count or 0
    finally:
        await client.close()

    match = pg_count == qdrant_count
    if match:
        logger.info("Parity OK: Postgres=%d, Qdrant=%d", pg_count, qdrant_count)
    else:
        logger.warning(
            "Parity MISMATCH: Postgres=%d, Qdrant=%d (diff=%d)",
            pg_count,
            qdrant_count,
            abs(pg_count - qdrant_count),
        )

    return pg_count, qdrant_count, match


async def _validate_parity(
    client: AsyncQdrantClient,
    pool: asyncpg.Pool,
    stats: SyncStats,
) -> None:
    """Internal parity check using an existing client connection."""
    pg_count = await _get_canonical_count(pool)
    info = await client.get_collection(COLLECTION_NAME)
    qdrant_count = info.points_count or 0

    if pg_count != qdrant_count:
        msg = (
            f"Parity mismatch after sync: Postgres={pg_count}, Qdrant={qdrant_count}"
        )
        stats.error_details.append(msg)
        logger.warning(msg)
    else:
        logger.info("Post-sync parity OK: %d nodes", pg_count)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log_summary(stats: SyncStats) -> None:
    """Log a human-readable sync summary."""
    duration = 0.0
    if stats.started_at and stats.finished_at:
        duration = (stats.finished_at - stats.started_at).total_seconds()

    logger.info(
        "Qdrant sync complete [%s]: fetched=%d embedded=%d upserted=%d "
        "skipped=%d errors=%d embed_time=%.1fs upsert_time=%.1fs total=%.1fs",
        stats.mode,
        stats.nodes_fetched,
        stats.nodes_embedded,
        stats.nodes_upserted,
        stats.nodes_skipped,
        stats.errors,
        stats.embedding_time_s,
        stats.upsert_time_s,
        duration,
    )
    if stats.error_details:
        for err in stats.error_details[:10]:
            logger.error("  sync error: %s", err)
