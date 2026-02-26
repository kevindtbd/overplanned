from __future__ import annotations

"""
Post-ranking score floor for cantMiss ActivityNodes.

Applied AFTER persona-based ranking, BEFORE final slot assignment.
Ensures irreplaceable venues (e.g., Fushimi Inari in Kyoto, Central Park in
NYC) cannot be suppressed below a score of 0.72, regardless of persona fit.

Rules from the Activity Dogma doc:
- cantMiss applies to ~0.1% of nodes
- Score floor is 0.72
- Both seeding criteria must hold: (1) genuinely irreplaceable,
  (2) locals still endorse it
- Persona still affects timing/ordering — cannot suppress inclusion
- If a node has cantMiss=true but no 'iconic-worth-it' vibe tag, log a warning
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

CANT_MISS_SCORE_FLOOR = 0.72
ICONIC_VIBE_TAG = "iconic-worth-it"


async def apply_cant_miss_floor(
    ranked_candidates: list[dict[str, Any]],
    pool: Any,  # asyncpg pool
) -> list[dict[str, Any]]:
    """Post-ranking pass: boost any cantMiss nodes below the score floor.

    Applied AFTER persona-based ranking, BEFORE final slot assignment.
    Does NOT re-sort — caller decides ordering after this pass.

    Args:
        ranked_candidates: List of dicts with at least:
            - id: str  (activityNodeId)
            - score: float  (ranking score, 0.0-1.0)
        pool: asyncpg connection pool

    Returns:
        Same list (mutated in-place) with scores adjusted for cantMiss nodes.
        Returns an empty list when ranked_candidates is empty.

    Raises:
        Does not raise — pool query failures are logged and the original list
        is returned unchanged so the caller's ranking pass is never blocked.
    """
    if not ranked_candidates:
        return ranked_candidates

    candidate_ids: list[str] = [c["id"] for c in ranked_candidates]

    # -----------------------------------------------------------------
    # 1. Fetch cantMiss rows from DB (only ids flagged as true)
    # -----------------------------------------------------------------
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    an."id",
                    an."cantMiss",
                    COALESCE(
                        json_agg(vt."slug") FILTER (WHERE vt."slug" IS NOT NULL),
                        '[]'::json
                    ) AS vibe_tag_slugs
                FROM activity_nodes an
                LEFT JOIN activity_node_vibe_tags anvt ON anvt."activityNodeId" = an."id"
                LEFT JOIN vibe_tags vt ON vt."id" = anvt."vibeTagId"
                WHERE an."id" = ANY($1::text[])
                  AND an."cantMiss" = true
                GROUP BY an."id"
                """,
                candidate_ids,
            )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "cant_miss_floor: pool query failed — skipping floor pass. error=%s",
            exc,
        )
        return ranked_candidates

    if not rows:
        return ranked_candidates

    # -----------------------------------------------------------------
    # 2. Build a lookup: id -> row for O(1) access
    # -----------------------------------------------------------------
    cant_miss_map: dict[str, Any] = {row["id"]: row for row in rows}

    # -----------------------------------------------------------------
    # 3. Apply floor and emit warnings
    # -----------------------------------------------------------------
    boosted_ids: list[str] = []

    for candidate in ranked_candidates:
        node_id = candidate["id"]
        row = cant_miss_map.get(node_id)
        if row is None:
            continue

        # Warn if the canonical vibe tag is missing
        vibe_slugs: list[str] = list(row["vibe_tag_slugs"] or [])
        if ICONIC_VIBE_TAG not in vibe_slugs:
            logger.warning(
                "cant_miss_floor: node %s has cantMiss=true but missing "
                "vibe tag '%s' — check seeding pipeline. vibe_tags=%s",
                node_id,
                ICONIC_VIBE_TAG,
                vibe_slugs,
            )

        current_score: float = candidate["score"]
        if current_score < CANT_MISS_SCORE_FLOOR:
            candidate["score"] = CANT_MISS_SCORE_FLOOR
            boosted_ids.append(node_id)

    if boosted_ids:
        logger.info(
            "cant_miss_floor applied to %d node(s): %s",
            len(boosted_ids),
            boosted_ids,
        )

    return ranked_candidates


async def set_cant_miss(
    pool: Any,
    activity_node_id: str,
    cant_miss: bool = True,
) -> bool:
    """Admin function: set cantMiss on an ActivityNode.

    Both seeding criteria must be satisfied before calling this:
      1. The venue is genuinely irreplaceable for its city.
      2. Local sources still endorse it (not tourist-only).

    Args:
        pool: asyncpg connection pool
        activity_node_id: UUID of the ActivityNode to update
        cant_miss: True to mark as cantMiss, False to unmark

    Returns:
        True if a row was updated, False if the node was not found.
    """
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE activity_nodes
            SET "cantMiss" = $1
            WHERE "id" = $2
            """,
            cant_miss,
            activity_node_id,
        )
    # asyncpg returns "UPDATE N" — parse the count
    updated_count = int(result.split()[-1])
    return updated_count > 0
