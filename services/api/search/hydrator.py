"""
Postgres batch hydration for ActivityNode search results.

Fetches ActivityNode rows with their VibeTag junction and QualitySignal
relations in a single query, returning enriched objects ready for API response.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def hydrate_activity_nodes(
    db,
    node_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """
    Batch-fetch ActivityNodes with vibe tags and quality signals.

    Returns a dict keyed by node ID for O(1) merge with Qdrant results.
    Fetches all three tables in a single round-trip using lateral joins.
    """
    if not node_ids:
        return {}

    placeholders = ", ".join(f"${i + 1}" for i in range(len(node_ids)))

    rows = await db.fetch(
        f"""
        SELECT
            an.id,
            an.name,
            an.slug,
            an."canonicalName",
            an.city,
            an.country,
            an.neighborhood,
            an.latitude,
            an.longitude,
            an.category,
            an.subcategory,
            an."priceLevel",
            an.hours,
            an.address,
            an."websiteUrl",
            an."primaryImageUrl",
            an."descriptionShort",
            an."sourceCount",
            an."convergenceScore",
            an."authorityScore",
            an.status,
            COALESCE(vt.tags, '[]'::jsonb) AS vibe_tags,
            COALESCE(qs.signals, '[]'::jsonb) AS quality_signals
        FROM activity_nodes an
        LEFT JOIN LATERAL (
            SELECT jsonb_agg(jsonb_build_object(
                'slug', v.slug,
                'name', v.name,
                'category', v.category,
                'score', avt.score,
                'source', avt.source
            )) AS tags
            FROM activity_node_vibe_tags avt
            JOIN vibe_tags v ON v.id = avt."vibeTagId"
            WHERE avt."activityNodeId" = an.id
        ) vt ON true
        LEFT JOIN LATERAL (
            SELECT jsonb_agg(jsonb_build_object(
                'sourceName', qs_inner."sourceName",
                'sourceAuthority', qs_inner."sourceAuthority",
                'signalType', qs_inner."signalType",
                'rawExcerpt', qs_inner."rawExcerpt",
                'extractedAt', qs_inner."extractedAt"
            )) AS signals
            FROM quality_signals qs_inner
            WHERE qs_inner."activityNodeId" = an.id
        ) qs ON true
        WHERE an.id IN ({placeholders})
        """,
        *node_ids,
    )

    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        node_id = row["id"]
        result[node_id] = {
            "id": node_id,
            "name": row["name"],
            "slug": row["slug"],
            "canonicalName": row["canonicalName"],
            "city": row["city"],
            "country": row["country"],
            "neighborhood": row["neighborhood"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "category": row["category"],
            "subcategory": row["subcategory"],
            "priceLevel": row["priceLevel"],
            "hours": row["hours"],
            "address": row["address"],
            "websiteUrl": row["websiteUrl"],
            "primaryImageUrl": row["primaryImageUrl"],
            "descriptionShort": row["descriptionShort"],
            "sourceCount": row["sourceCount"],
            "convergenceScore": row["convergenceScore"],
            "authorityScore": row["authorityScore"],
            "status": row["status"],
            "vibeTags": row["vibe_tags"] if row["vibe_tags"] else [],
            "qualitySignals": row["quality_signals"] if row["quality_signals"] else [],
        }

    return result
