"""
Cross-source convergence scoring for ActivityNodes.

Scores nodes based on two dimensions:
  1. Convergence — how many independent sources reference the same node.
     Formula: convergenceScore = min(unique_sources / 3.0, 1.0)
     Bonus: if 3+ sources agree on the same vibe tag, boost by 0.1 (capped at 1.0).
  2. Authority — weighted average of source authority scores.
     Source weights come from QualitySignal.sourceAuthority (written at scrape time),
     with a fallback registry for known sources.

Runs after entity resolution and vibe tag extraction.
Writes convergenceScore and authorityScore to ActivityNode.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Source authority fallback registry
#
# QualitySignal rows carry their own sourceAuthority (set at scrape time).
# This registry provides fallback weights when sourceAuthority is NULL or 0.
# ---------------------------------------------------------------------------

SOURCE_AUTHORITY_DEFAULTS: dict[str, float] = {
    "the_infatuation": 0.9,
    "atlas_obscura": 0.85,
    "foursquare": 0.7,
    "reddit_high_upvotes": 0.6,
    "generic_blog": 0.4,
}

# Fallback when source is completely unknown
_DEFAULT_AUTHORITY = 0.3

# Convergence bonus when 3+ sources agree on the same vibe tag
_VIBE_AGREEMENT_BONUS = 0.1

# Denominator for base convergence score
_CONVERGENCE_DENOMINATOR = 3.0


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@dataclass
class ConvergenceStats:
    """Summary of a convergence scoring run."""
    nodes_processed: int = 0
    nodes_updated: int = 0
    nodes_skipped: int = 0  # no quality signals
    vibe_boosts_applied: int = 0
    errors: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Core scoring functions (pure, no DB)
# ---------------------------------------------------------------------------

def compute_convergence_score(
    unique_source_count: int,
    has_vibe_agreement: bool,
) -> float:
    """
    Compute convergence score for a node.

    Base: min(unique_sources / 3.0, 1.0)
    Bonus: +0.1 if 3+ sources agree on same vibe tag (capped at 1.0).
    """
    base = min(unique_source_count / _CONVERGENCE_DENOMINATOR, 1.0)
    if has_vibe_agreement:
        base = min(base + _VIBE_AGREEMENT_BONUS, 1.0)
    return round(base, 4)


def compute_authority_score(
    source_authorities: list[tuple[str, float]],
) -> float:
    """
    Compute authority score as weighted average of source authorities.

    Args:
        source_authorities: list of (source_name, authority_weight) pairs.
            authority_weight should already be resolved (DB value or fallback).

    Returns:
        Weighted average, or 0.0 if no sources.
    """
    if not source_authorities:
        return 0.0

    total_weight = sum(w for _, w in source_authorities)
    if total_weight == 0:
        return 0.0

    # Weighted average where each source contributes its own authority
    # (all sources weighted equally — authority IS the value, not a weight on something else)
    return round(sum(w for _, w in source_authorities) / len(source_authorities), 4)


def resolve_authority(source_name: str, db_authority: Optional[float]) -> float:
    """
    Resolve the authority weight for a source.

    Priority: DB value (if > 0) → fallback registry → default.
    """
    if db_authority is not None and db_authority > 0:
        return db_authority

    return SOURCE_AUTHORITY_DEFAULTS.get(source_name, _DEFAULT_AUTHORITY)


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

async def run_convergence_scoring(
    pool: asyncpg.Pool,
    *,
    batch_size: int = 500,
    node_ids: Optional[list[str]] = None,
) -> ConvergenceStats:
    """
    Score all canonical ActivityNodes for convergence and authority.

    Args:
        pool: asyncpg connection pool.
        batch_size: Nodes per DB round-trip.
        node_ids: Optional specific node IDs. If None, scores all canonical nodes.

    Returns:
        ConvergenceStats with processing counts.
    """
    stats = ConvergenceStats(started_at=datetime.now(timezone.utc))

    async with pool.acquire() as conn:
        # 1. Get target nodes
        if node_ids:
            nodes = await conn.fetch(
                """
                SELECT id FROM "ActivityNode"
                WHERE id = ANY($1::text[])
                  AND "isCanonical" = true
                """,
                node_ids,
            )
        else:
            nodes = await conn.fetch(
                """
                SELECT id FROM "ActivityNode"
                WHERE "isCanonical" = true
                ORDER BY "createdAt"
                """,
            )

        logger.info("Convergence scoring: %d nodes to process", len(nodes))

        # 2. Process in batches
        all_node_ids = [r["id"] for r in nodes]

        for offset in range(0, len(all_node_ids), batch_size):
            batch_ids = all_node_ids[offset : offset + batch_size]

            try:
                updated = await _score_batch(conn, batch_ids, stats)
                stats.nodes_updated += updated
            except Exception:
                logger.exception(
                    "Convergence scoring failed for batch at offset %d", offset
                )
                stats.errors += 1

    stats.finished_at = datetime.now(timezone.utc)
    logger.info(
        "Convergence scoring complete: %d processed, %d updated, %d skipped, %d vibe boosts, %d errors",
        stats.nodes_processed,
        stats.nodes_updated,
        stats.nodes_skipped,
        stats.vibe_boosts_applied,
        stats.errors,
    )
    return stats


async def _score_batch(
    conn: asyncpg.Connection,
    node_ids: list[str],
    stats: ConvergenceStats,
) -> int:
    """Score a batch of nodes. Returns count of nodes actually updated."""

    # Fetch quality signals grouped by node
    signals = await conn.fetch(
        """
        SELECT "activityNodeId", "sourceName", "sourceAuthority"
        FROM "QualitySignal"
        WHERE "activityNodeId" = ANY($1::text[])
        """,
        node_ids,
    )

    # Group signals by node
    node_signals: dict[str, list[tuple[str, Optional[float]]]] = {}
    for row in signals:
        nid = row["activityNodeId"]
        if nid not in node_signals:
            node_signals[nid] = []
        node_signals[nid].append((row["sourceName"], row["sourceAuthority"]))

    # Fetch vibe tag source counts per node — how many distinct sources
    # wrote the same vibe tag for a given node
    vibe_agreement = await conn.fetch(
        """
        SELECT "activityNodeId", "vibeTagId", COUNT(DISTINCT source) AS source_count
        FROM "ActivityNodeVibeTag"
        WHERE "activityNodeId" = ANY($1::text[])
        GROUP BY "activityNodeId", "vibeTagId"
        HAVING COUNT(DISTINCT source) >= 3
        """,
        node_ids,
    )

    # Set of node IDs that have vibe tag agreement (3+ sources on same tag)
    nodes_with_vibe_agreement: set[str] = {r["activityNodeId"] for r in vibe_agreement}

    # Score each node
    updated = 0
    for nid in node_ids:
        stats.nodes_processed += 1

        sources = node_signals.get(nid)
        if not sources:
            stats.nodes_skipped += 1
            continue

        # Unique sources
        unique_sources: dict[str, float] = {}
        for source_name, db_authority in sources:
            if source_name not in unique_sources:
                unique_sources[source_name] = resolve_authority(source_name, db_authority)

        has_vibe = nid in nodes_with_vibe_agreement
        if has_vibe:
            stats.vibe_boosts_applied += 1

        convergence = compute_convergence_score(len(unique_sources), has_vibe)
        authority = compute_authority_score(list(unique_sources.items()))

        # Write back to ActivityNode
        await conn.execute(
            """
            UPDATE "ActivityNode"
            SET "convergenceScore" = $1,
                "authorityScore" = $2,
                "sourceCount" = $3,
                "updatedAt" = NOW()
            WHERE id = $4
            """,
            convergence,
            authority,
            len(unique_sources),
            nid,
        )
        updated += 1

    return updated
