"""
Cross-source convergence scoring for ActivityNodes.

Scores nodes based on two dimensions:
  1. Convergence — how many independent sources reference the same node.
     Formula: convergenceScore = min(unique_sources / 3.0, 1.0)
     Bonus: if 3+ sources agree on the same vibe tag, boost by 0.1 (capped at 1.0).
  2. Authority — weighted average of source authority scores.
     Source weights come from QualitySignal.sourceAuthority (written at scrape time),
     with a fallback registry for known sources.
     Local signals (signalType = "local_recommendation") receive 3x weight multiplier.

Also computes per-node:
  - tourist_score: fraction of overrated_flag signals (from extractionMetadata),
    scaled by tier: >40% -> 0.7-1.0, 20-40% -> 0.4-0.75, <20% -> unchanged.
  - vibe_confidence: harmonic mean of source_diversity and mention_count_score.
    Stored in convergence output / canary report (no DB column yet).

Runs after entity resolution and vibe tag extraction.
Writes convergenceScore, authorityScore, and tourist_score to ActivityNode.
"""

import json
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

# Weight multiplier for local_recommendation signals in authority scoring
_LOCAL_SIGNAL_WEIGHT_MULTIPLIER = 3.0

# SignalType that identifies local-sourced posts
_LOCAL_SIGNAL_TYPE = "local_recommendation"

# Tourist score thresholds (fraction of overrated_flag signals)
_TOURIST_HIGH_THRESHOLD = 0.40   # > 40% overrated -> tier 1
_TOURIST_MID_THRESHOLD = 0.20    # > 20% overrated -> tier 2

# Epsilon for harmonic mean division-by-zero guard
_HARMONIC_EPSILON = 1e-9

# Caps for vibe_confidence inputs
_VIBE_CONF_SOURCE_CAP = 5.0    # cap source diversity at 5 unique sources
_VIBE_CONF_MENTION_CAP = 20.0  # cap mention count normalisation at 20


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
    tourist_scores_written: int = 0
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


def compute_authority_score_with_local_weighting(
    source_signal_types: list[tuple[str, float, str]],
) -> float:
    """
    Compute authority score with 3x weight for local_recommendation signals.

    Local signals (signalType = "local_recommendation") are treated as 3x
    as authoritative as non-local signals in the weighted average — a single
    local recommendation is equivalent to 3 regular-authority mentions.

    Args:
        source_signal_types: list of (source_name, authority_weight, signal_type) triples.
            authority_weight should already be resolved (DB value or fallback).

    Returns:
        Weighted average with local multiplier applied, or 0.0 if no sources.
    """
    if not source_signal_types:
        return 0.0

    weighted_sum = 0.0
    effective_count = 0.0

    for _source, authority, signal_type in source_signal_types:
        multiplier = _LOCAL_SIGNAL_WEIGHT_MULTIPLIER if signal_type == _LOCAL_SIGNAL_TYPE else 1.0
        weighted_sum += authority * multiplier
        effective_count += multiplier

    if effective_count == 0:
        return 0.0

    return round(weighted_sum / effective_count, 4)


def resolve_authority(source_name: str, db_authority: Optional[float]) -> float:
    """
    Resolve the authority weight for a source.

    Priority: DB value (if > 0) → fallback registry → default.
    """
    if db_authority is not None and db_authority > 0:
        return db_authority

    return SOURCE_AUTHORITY_DEFAULTS.get(source_name, _DEFAULT_AUTHORITY)


def compute_tourist_score(
    overrated_count: int,
    total_mentions: int,
) -> Optional[float]:
    """
    Compute tourist_score from overrated signal fraction.

    Tiers:
      >40% overrated: 0.7 + (pct * 0.3)  — strongly tourist-signal
      20-40%:         0.4 + (pct * 0.75)  — moderate signal
      <20%:           None (no update — leave existing value)

    Args:
        overrated_count: number of quality signals where overrated_flag = true
        total_mentions: total quality signal count for the node

    Returns:
        New tourist_score float, or None if below 20% threshold.
    """
    if total_mentions == 0:
        return None

    pct = overrated_count / total_mentions

    if pct > _TOURIST_HIGH_THRESHOLD:
        score = 0.7 + (pct * 0.3)
        return round(min(score, 1.0), 4)

    if pct > _TOURIST_MID_THRESHOLD:
        score = 0.4 + (pct * 0.75)
        return round(min(score, 1.0), 4)

    return None


def compute_vibe_confidence(
    unique_source_count: int,
    mention_count: int,
) -> float:
    """
    Compute vibe_confidence as the harmonic mean of source_diversity and
    mention_count_score.

    Formula:
      source_diversity     = min(unique_sources / 5.0, 1.0)
      mention_count_score  = min(mention_count / 20.0, 1.0)
      vibe_confidence      = 2 * (A * B) / (A + B + epsilon)

    Returns a value in [0.0, 1.0].
    """
    source_diversity = min(unique_source_count / _VIBE_CONF_SOURCE_CAP, 1.0)
    mention_count_score = min(mention_count / _VIBE_CONF_MENTION_CAP, 1.0)

    numerator = 2.0 * source_diversity * mention_count_score
    denominator = source_diversity + mention_count_score + _HARMONIC_EPSILON

    return round(numerator / denominator, 4)


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
        "Convergence scoring complete: %d processed, %d updated, %d skipped, "
        "%d vibe boosts, %d tourist scores written, %d errors",
        stats.nodes_processed,
        stats.nodes_updated,
        stats.nodes_skipped,
        stats.vibe_boosts_applied,
        stats.tourist_scores_written,
        stats.errors,
    )
    return stats


async def _score_batch(
    conn: asyncpg.Connection,
    node_ids: list[str],
    stats: ConvergenceStats,
) -> int:
    """Score a batch of nodes. Returns count of nodes actually updated."""

    # Fetch quality signals grouped by node (include signalType for local weighting
    # and extractionMetadata for tourist_score aggregation)
    signals = await conn.fetch(
        """
        SELECT
            "activityNodeId",
            "sourceName",
            "sourceAuthority",
            "signalType",
            "extractionMetadata"
        FROM "QualitySignal"
        WHERE "activityNodeId" = ANY($1::text[])
        """,
        node_ids,
    )

    # Group signals by node — store (source_name, authority, signal_type, metadata)
    NodeSignalRow = tuple[str, Optional[float], str, Optional[dict]]
    node_signals: dict[str, list[NodeSignalRow]] = {}
    for row in signals:
        nid = row["activityNodeId"]
        if nid not in node_signals:
            node_signals[nid] = []

        # extractionMetadata may be stored as a JSON string or already a dict
        raw_meta = row.get("extractionMetadata")
        meta: Optional[dict] = None
        if raw_meta is not None:
            if isinstance(raw_meta, str):
                try:
                    meta = json.loads(raw_meta)
                except (ValueError, TypeError):
                    meta = None
            elif isinstance(raw_meta, dict):
                meta = raw_meta

        node_signals[nid].append((
            row["sourceName"],
            row["sourceAuthority"],
            row.get("signalType") or "mention",
            meta,
        ))

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

        all_signals = node_signals.get(nid)
        if not all_signals:
            stats.nodes_skipped += 1
            continue

        # Deduplicate by source_name — keep the first occurrence per source for
        # convergence counting, but accumulate all for local-weighted authority.
        # We also keep all rows for tourist_score aggregation (per-mention).
        seen_sources: set[str] = set()
        unique_source_triples: list[tuple[str, float, str]] = []
        for source_name, db_authority, signal_type, _meta in all_signals:
            if source_name not in seen_sources:
                seen_sources.add(source_name)
                authority = resolve_authority(source_name, db_authority)
                unique_source_triples.append((source_name, authority, signal_type))

        has_vibe = nid in nodes_with_vibe_agreement
        if has_vibe:
            stats.vibe_boosts_applied += 1

        convergence = compute_convergence_score(len(seen_sources), has_vibe)

        # Authority with local 3x weighting
        authority = compute_authority_score_with_local_weighting(unique_source_triples)

        # Tourist score — aggregate overrated_flag from extraction metadata
        overrated_count = sum(
            1 for _sn, _sa, _st, meta in all_signals
            if meta and meta.get("overrated_flag") is True
        )
        total_mentions = len(all_signals)
        tourist_score = compute_tourist_score(overrated_count, total_mentions)

        # Vibe confidence — harmonic mean of source diversity + mention count
        vibe_confidence = compute_vibe_confidence(len(seen_sources), total_mentions)

        # Write convergence + authority + tourist_score back to ActivityNode.
        # tourist_score is only written when it crosses a threshold (not None).
        if tourist_score is not None:
            await conn.execute(
                """
                UPDATE "ActivityNode"
                SET "convergenceScore" = $1,
                    "authorityScore" = $2,
                    "sourceCount" = $3,
                    tourist_score = $4,
                    "updatedAt" = NOW()
                WHERE id = $5
                """,
                convergence,
                authority,
                len(seen_sources),
                tourist_score,
                nid,
            )
            stats.tourist_scores_written += 1
        else:
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
                len(seen_sources),
                nid,
            )

        logger.debug(
            "Node %s: convergence=%.3f authority=%.3f tourist=%s vibe_confidence=%.3f",
            nid, convergence, authority,
            f"{tourist_score:.3f}" if tourist_score is not None else "unchanged",
            vibe_confidence,
        )
        updated += 1

    return updated
