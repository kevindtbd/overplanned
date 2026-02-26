"""
Rule-based vibe tag inference — deterministic baseline tags for all ActivityNodes.

Maps ActivityCategory (+ optional priceLevel/subcategory) to vibe tags with
confidence scores. Runs after entity resolution, before convergence scoring.
Writes to ActivityNodeVibeTag with source = "rule_inference".

This ensures every node with a category gets baseline vibe tags even when
LLM extraction is unavailable or hasn't run yet.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import asyncpg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Source identifier — matches the @@unique constraint on ActivityNodeVibeTag
# ---------------------------------------------------------------------------

SOURCE = "rule_inference"

# ---------------------------------------------------------------------------
# Category → vibe tag mapping rules
#
# Each category maps to a list of (tag_slug, base_score) tuples.
# Conditional rules (e.g. priceLevel >= 4) are handled separately in
# _apply_conditional_rules.
# ---------------------------------------------------------------------------

CATEGORY_TAG_RULES: dict[str, list[tuple[str, float]]] = {
    "nightlife": [
        ("late-night", 0.9),
        ("high-energy", 0.7),
        ("social", 0.6),
    ],
    "dining": [
        ("food-focused", 0.9),
        ("sit-down", 0.7),
    ],
    "drinks": [
        ("social", 0.8),
        ("casual", 0.7),
        ("late-night", 0.5),
    ],
    "culture": [
        ("deep-dive", 0.7),
        ("slow-paced", 0.6),
        ("iconic", 0.5),
    ],
    "outdoors": [
        ("fresh-air", 0.9),
        ("active", 0.6),
        ("scenic", 0.7),
    ],
    "active": [
        ("high-energy", 0.8),
        ("active", 0.9),
        ("fresh-air", 0.5),
    ],
    "entertainment": [
        ("high-energy", 0.6),
        ("social", 0.7),
        ("iconic", 0.5),
    ],
    "shopping": [
        ("browsing", 0.8),
        ("casual", 0.6),
    ],
    "experience": [
        ("unique", 0.8),
        ("deep-dive", 0.6),
        ("memorable", 0.7),
    ],
    "group_activity": [
        ("social", 0.9),
        ("high-energy", 0.6),
        ("group-friendly", 0.8),
    ],
    "wellness": [
        ("slow-paced", 0.8),
        ("restorative", 0.9),
        ("quiet", 0.6),
    ],
}


def _apply_conditional_rules(
    category: str,
    price_level: Optional[int],
    subcategory: Optional[str],
) -> list[tuple[str, float]]:
    """Return additional vibe tags based on price/subcategory conditions."""
    extra: list[tuple[str, float]] = []

    # High-end dining → splurge
    if category == "dining" and price_level is not None and price_level >= 4:
        extra.append(("splurge", 0.8))

    # Budget dining → casual
    if category == "dining" and price_level is not None and price_level <= 2:
        extra.append(("casual", 0.7))

    # High-end drinks → splurge (cocktail bars, etc.)
    if category == "drinks" and price_level is not None and price_level >= 4:
        extra.append(("splurge", 0.6))

    # Outdoor + active subcategories
    if category == "outdoors" and subcategory:
        sub_lower = subcategory.lower()
        if any(k in sub_lower for k in ("hike", "trek", "climb")):
            extra.append(("high-energy", 0.7))
        if any(k in sub_lower for k in ("garden", "park", "beach")):
            extra.append(("slow-paced", 0.6))

    # Wellness subcategories
    if category == "wellness" and subcategory:
        sub_lower = subcategory.lower()
        if any(k in sub_lower for k in ("onsen", "spa", "bath")):
            extra.append(("unique", 0.5))

    return extra


def compute_tags_for_node(
    category: str,
    price_level: Optional[int] = None,
    subcategory: Optional[str] = None,
) -> list[tuple[str, float]]:
    """
    Compute deterministic vibe tags for a single node.

    Returns list of (tag_slug, score) tuples. Deduplicates by slug,
    keeping the highest score when a tag appears in both base and
    conditional rules.
    """
    base = CATEGORY_TAG_RULES.get(category, [])
    conditional = _apply_conditional_rules(category, price_level, subcategory)

    # Merge: highest score wins per slug
    merged: dict[str, float] = {}
    for slug, score in base + conditional:
        if slug not in merged or score > merged[slug]:
            merged[slug] = score

    return [(slug, score) for slug, score in merged.items()]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@dataclass
class RuleInferenceStats:
    """Summary of a rule inference run."""
    nodes_processed: int = 0
    tags_created: int = 0
    tags_skipped: int = 0  # already existed with this source
    missing_vibe_tags: int = 0  # tag slug not in VibeTag table
    errors: int = 0
    started_at: datetime = None  # type: ignore[assignment]
    finished_at: datetime = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

async def run_rule_inference(
    pool: asyncpg.Pool,
    *,
    batch_size: int = 500,
    node_ids: Optional[list[str]] = None,
) -> RuleInferenceStats:
    """
    Apply deterministic category→vibe tag rules to ActivityNodes.

    Args:
        pool: asyncpg connection pool.
        batch_size: Number of nodes to process per DB round-trip.
        node_ids: Optional list of specific node IDs to process.
                  If None, processes all canonical nodes with a category.

    Returns:
        RuleInferenceStats with counts of what happened.
    """
    stats = RuleInferenceStats(started_at=datetime.now(timezone.utc))

    async with pool.acquire() as conn:
        # Load the vibe tag vocabulary: slug → id
        # NOTE: Prisma uses PascalCase table names and camelCase columns (quoted).
        # Post-canary we'll standardize with @@map; for now, quote everything.
        rows = await conn.fetch('SELECT id, slug FROM "VibeTag" WHERE "isActive" = true')
        tag_lookup: dict[str, str] = {r["slug"]: r["id"] for r in rows}

        # Build the node query
        if node_ids:
            query = """
                SELECT id, category, "priceLevel", subcategory
                FROM "ActivityNode"
                WHERE id = ANY($1::text[])
                  AND "isCanonical" = true
                  AND status != 'archived'
            """
            all_nodes = await conn.fetch(query, node_ids)
        else:
            query = """
                SELECT id, category, "priceLevel", subcategory
                FROM "ActivityNode"
                WHERE "isCanonical" = true
                  AND status != 'archived'
                ORDER BY "createdAt"
            """
            all_nodes = await conn.fetch(query)

        logger.info("Rule inference: %d nodes to process", len(all_nodes))

        # Process in batches
        for offset in range(0, len(all_nodes), batch_size):
            batch = all_nodes[offset : offset + batch_size]
            insert_rows: list[tuple[str, str, str, float, str]] = []

            for node in batch:
                stats.nodes_processed += 1
                node_id = node["id"]
                category = node["category"]
                price_level = node["priceLevel"]
                subcategory = node["subcategory"]

                tags = compute_tags_for_node(category, price_level, subcategory)

                for tag_slug, score in tags:
                    vibe_tag_id = tag_lookup.get(tag_slug)
                    if vibe_tag_id is None:
                        stats.missing_vibe_tags += 1
                        logger.warning(
                            "Vibe tag slug %r not in DB — skipping for node %s",
                            tag_slug,
                            node_id,
                        )
                        continue

                    insert_rows.append((
                        str(uuid4()),
                        node_id,
                        vibe_tag_id,
                        score,
                        SOURCE,
                    ))

            if not insert_rows:
                continue

            # Upsert: skip if (activityNodeId, vibeTagId, source) already exists
            try:
                result = await conn.executemany(
                    """
                    INSERT INTO "ActivityNodeVibeTag"
                        (id, "activityNodeId", "vibeTagId", score, source, "createdAt")
                    VALUES ($1, $2, $3, $4, $5, NOW())
                    ON CONFLICT ("activityNodeId", "vibeTagId", source)
                    DO UPDATE SET score = EXCLUDED.score
                    """,
                    insert_rows,
                )
                stats.tags_created += len(insert_rows)
            except Exception:
                logger.exception("Failed to insert rule inference tags for batch at offset %d", offset)
                stats.errors += 1

    stats.finished_at = datetime.now(timezone.utc)
    logger.info(
        "Rule inference complete: %d nodes, %d tags created, %d missing slugs, %d errors",
        stats.nodes_processed,
        stats.tags_created,
        stats.missing_vibe_tags,
        stats.errors,
    )
    return stats
