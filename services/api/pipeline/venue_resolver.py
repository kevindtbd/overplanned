"""Simplified 2-tier venue name resolver for Pipeline D.

Only exact + fuzzy name matching (no coordinates/external IDs).
Unresolved venues stored for later enrichment pipeline.
"""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 0.7


class MatchType(str, Enum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    UNRESOLVED = "unresolved"


@dataclass
class ResolutionResult:
    venue_name_raw: str
    activity_node_id: Optional[str]
    canonical_name: Optional[str]
    match_type: MatchType
    confidence: float


async def resolve_venue_names(
    pool: asyncpg.Pool,
    city_slug: str,
    venue_signals: list[dict],
) -> list[ResolutionResult]:
    """Resolve venue name strings to ActivityNode IDs.

    2-tier cascade (city-scoped):
    1. Exact match on canonicalName (case-insensitive)
    2. Fuzzy match via pg_trgm similarity > 0.7 + substring containment
    """
    results = []
    async with pool.acquire() as conn:
        for signal in venue_signals:
            name = signal.get("venue_name", signal.get("venueNameRaw", ""))
            if not name:
                results.append(ResolutionResult(
                    venue_name_raw=name, activity_node_id=None,
                    canonical_name=None, match_type=MatchType.UNRESOLVED, confidence=0.0))
                continue

            # Tier 1: Exact match (case-insensitive, city-scoped)
            row = await conn.fetchrow(
                'SELECT id, "canonicalName" FROM activity_nodes '
                'WHERE LOWER("canonicalName") = LOWER($1) '
                'AND city = $2 AND "isCanonical" = true LIMIT 1',
                name, city_slug)
            if row:
                results.append(ResolutionResult(
                    venue_name_raw=name, activity_node_id=row["id"],
                    canonical_name=row["canonicalName"],
                    match_type=MatchType.EXACT, confidence=1.0))
                continue

            # Tier 2: Fuzzy match (pg_trgm + substring, city-scoped)
            row = await conn.fetchrow(
                'SELECT id, "canonicalName", '
                '       similarity("canonicalName", $1) AS similarity '
                'FROM activity_nodes '
                'WHERE city = $2 AND "isCanonical" = true '
                'AND ( '
                '    similarity("canonicalName", $1) > $3 '
                '    OR LOWER("canonicalName") LIKE \'%%\' || LOWER($1) || \'%%\' '
                '    OR LOWER($1) LIKE \'%%\' || LOWER("canonicalName") || \'%%\' '
                ') '
                'ORDER BY similarity("canonicalName", $1) DESC LIMIT 1',
                name, city_slug, FUZZY_THRESHOLD)
            if row:
                results.append(ResolutionResult(
                    venue_name_raw=name, activity_node_id=row["id"],
                    canonical_name=row["canonicalName"],
                    match_type=MatchType.FUZZY,
                    confidence=float(row.get("similarity", 0.7))))
                continue

            results.append(ResolutionResult(
                venue_name_raw=name, activity_node_id=None,
                canonical_name=None, match_type=MatchType.UNRESOLVED, confidence=0.0))

    resolved = sum(1 for r in results if r.match_type != MatchType.UNRESOLVED)
    logger.info("Resolved %d/%d venues for %s (exact: %d, fuzzy: %d, unresolved: %d)",
                resolved, len(results), city_slug,
                sum(1 for r in results if r.match_type == MatchType.EXACT),
                sum(1 for r in results if r.match_type == MatchType.FUZZY),
                sum(1 for r in results if r.match_type == MatchType.UNRESOLVED))
    return results
