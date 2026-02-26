"""
LLM-based vibe tag extraction for ActivityNodes.

Uses Claude Haiku to classify ActivityNodes against the locked 44-tag
vibe vocabulary.  Each node's name, description, and quality signal
excerpts are sent as input; the model returns scored tags from the
controlled set, plus extraction metadata (overrated_flag, price_signal,
explicit_recommendation, author_type, crowd_notes).

Extraction rules (from vibe-vocabulary.md + heuristics-addendum.md):
  - 3–8 tags per node, max 5 per source ("llm_extraction")
  - Confidence threshold: >= 0.75 or the tag is discarded
  - Scores clamped to [0.0, 1.0]
  - Tags are positive signals only — no "anti" tags
  - Contradictory pairs flagged for human review
  - Results written to ActivityNodeVibeTag with source = "llm_extraction"
  - Every extraction batch logged in ModelRegistry with cost + latency
  - Per-mention extraction details logged to data/extraction_logs/{city}.jsonl
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional
from uuid import uuid4

import asyncpg
import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 42-tag controlled vocabulary (locked Feb 2026)
# ---------------------------------------------------------------------------

VIBE_VOCABULARY: dict[str, list[str]] = {
    "pace_energy": [
        "high-energy", "slow-burn", "immersive",
    ],
    "crowd_atmosphere": [
        "hidden-gem", "iconic-worth-it", "locals-only",
    ],
    "food_drink": [
        "destination-meal", "street-food", "local-institution", "drinks-forward",
    ],
    "physical_outdoors": [
        "physically-demanding", "easy-walk", "nature-immersive", "urban-exploration",
    ],
    "culture_depth": [
        "deep-history", "contemporary-culture", "people-watching", "hands-on",
    ],
    "time_social": [
        "late-night", "early-morning", "solo-friendly", "group-friendly",
        "social-scene", "low-interaction",
    ],
    "atmosphere_mood": [
        "intimate", "lively", "offbeat", "scenic", "interactive", "participatory",
    ],
    "practical": [
        "cash-only", "queue-worthy", "book-ahead", "no-frills",
    ],
    "visit_character": [
        "repeat-worthy", "once-in-a-trip", "underrated", "seasonal",
        "time-sensitive", "locals-routine",
    ],
    "cost_character": [
        "budget-friendly", "mid-range", "splurge-worthy", "free",
    ],
}

ALL_TAGS: set[str] = {tag for tags in VIBE_VOCABULARY.values() for tag in tags}
assert len(ALL_TAGS) == 44, f"Vocabulary drift: expected 44, got {len(ALL_TAGS)}"

# Known contradictory pairs — flag for human review, don't auto-apply both
CONTRADICTORY_PAIRS: list[tuple[str, str]] = [
    ("hidden-gem", "iconic-worth-it"),
    ("physically-demanding", "easy-walk"),
    ("solo-friendly", "group-friendly"),
    ("budget-friendly", "splurge-worthy"),
    ("early-morning", "late-night"),
]

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL_NAME = "claude-haiku-4-5-20251001"
PROMPT_VERSION = "vibe-extract-v2"
CONFIDENCE_THRESHOLD = 0.75
MAX_TAGS_PER_SOURCE = 5
BATCH_SIZE = 10
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0  # exponential backoff seconds

# Haiku pricing (per 1M tokens, as of Feb 2026)
INPUT_COST_PER_1M = 0.80   # USD
OUTPUT_COST_PER_1M = 4.00  # USD

# Extraction log output directory (one JSONL file per city)
EXTRACTION_LOG_DIR = Path("data/extraction_logs")
EXTRACTION_LOG_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

PriceSignal = Optional[Literal["budget", "mid", "splurge", "free"]]
AuthorType = Literal["local", "expat", "tourist", "unknown"]


@dataclass
class NodeInput:
    """Minimal ActivityNode data needed for extraction."""
    id: str
    name: str
    city: str
    category: str
    description_short: Optional[str] = None
    description_long: Optional[str] = None
    quality_excerpts: list[str] = field(default_factory=list)


@dataclass
class TagResult:
    """A single extracted vibe tag with score."""
    tag_slug: str
    score: float


@dataclass
class ExtractionMetadata:
    """
    Per-venue extraction metadata captured alongside vibe tags.

    These fields are not vibe tags — they describe the signal quality and
    character of the sources. Stored in QualitySignal JSON payload fields
    pending the A.WT1 schema migration that adds a dedicated column.
    """
    overrated_flag: bool = False
    price_signal: PriceSignal = None
    explicit_recommendation: bool = False
    author_type: AuthorType = "unknown"
    crowd_notes: Optional[str] = None


@dataclass
class ExtractionResult:
    """Result of extracting vibe tags for one ActivityNode."""
    node_id: str
    node_name: str
    city: str
    tags: list[TagResult]
    metadata: ExtractionMetadata
    flagged_contradictions: list[tuple[str, str]]
    input_tokens: int
    output_tokens: int


@dataclass
class BatchStats:
    """Aggregated stats for a batch extraction run."""
    nodes_processed: int = 0
    tags_written: int = 0
    nodes_skipped: int = 0
    contradictions_flagged: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    latency_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a venue classification system for a travel planning app.
You receive a venue's name, city, category, description, and review excerpts.
You must classify the venue against a FIXED vocabulary of 44 vibe tags AND extract
signal metadata about the sources.

RULES:
- Return ONLY tags from the provided vocabulary. No invented tags.
- Return between 1 and 5 tags. Less is better than forcing irrelevant tags.
- Each tag gets a confidence score between 0.0 and 1.0.
- Only include tags where you have genuine evidence from the provided text.
- Tags are POSITIVE signals only. No negative associations.
- If the text is too sparse for confident tagging, return fewer tags.
- Output ONLY a JSON object — no prose, no markdown, no explanation."""


def _build_user_prompt(node: NodeInput) -> str:
    """Build the user message for a single node extraction."""
    parts = [
        f"Venue: {node.name}",
        f"City: {node.city}",
        f"Category: {node.category}",
    ]

    if node.description_short:
        parts.append(f"Short description: {node.description_short}")
    if node.description_long:
        parts.append(f"Full description: {node.description_long}")

    if node.quality_excerpts:
        excerpts = "\n".join(f"- {e}" for e in node.quality_excerpts[:10])
        parts.append(f"Review excerpts:\n{excerpts}")

    tag_list = ", ".join(sorted(ALL_TAGS))
    parts.append(
        f"\nValid tags (use ONLY these): {tag_list}"
        "\n\nReturn a JSON object with exactly two keys:"
        "\n1. \"tags\": array of objects with \"tag\" (string) and \"score\" (float 0.0-1.0)"
        "\n2. \"metadata\": object with:"
        "\n   - \"overrated_flag\": boolean — true if any source calls this a tourist trap or overrated"
        "\n   - \"price_signal\": one of \"budget\"|\"mid\"|\"splurge\"|\"free\"|null"
        "\n   - \"explicit_recommendation\": boolean — true if any source explicitly recommends this venue"
        "\n   - \"author_type\": one of \"local\"|\"expat\"|\"tourist\"|\"unknown\" — inferred from writing style/context"
        "\n   - \"crowd_notes\": string with crowd/atmosphere summary, or null if no crowd info present"
        "\n\nExample output:"
        '\n{"tags": [{"tag": "hidden-gem", "score": 0.92}, {"tag": "street-food", "score": 0.85}],'
        ' "metadata": {"overrated_flag": false, "price_signal": "budget",'
        ' "explicit_recommendation": true, "author_type": "local", "crowd_notes": "packed on weekends"}}'
    )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------

async def _call_haiku(
    client: httpx.AsyncClient,
    api_key: str,
    node: NodeInput,
) -> ExtractionResult:
    """Call Haiku for a single node, parse and validate response."""

    user_prompt = _build_user_prompt(node)

    payload = {
        "model": MODEL_NAME,
        "max_tokens": 768,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    resp = await client.post(
        "https://api.anthropic.com/v1/messages",
        json=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    body = resp.json()

    input_tokens = body.get("usage", {}).get("input_tokens", 0)
    output_tokens = body.get("usage", {}).get("output_tokens", 0)

    # Extract text content from response
    text = ""
    for block in body.get("content", []):
        if block.get("type") == "text":
            text += block["text"]

    # Parse JSON from response text
    tag_list, raw_metadata = _parse_extraction_response(text)

    # Validate tags against vocabulary + threshold
    valid_tags: list[TagResult] = []
    for item in tag_list:
        slug = item.get("tag", "").strip().lower()
        raw_score = item.get("score", 0.0)

        if slug not in ALL_TAGS:
            logger.debug("Dropping invalid tag %r for node %s", slug, node.id)
            continue

        score = max(0.0, min(1.0, float(raw_score)))
        if score < CONFIDENCE_THRESHOLD:
            logger.debug(
                "Dropping low-confidence tag %s (%.2f) for node %s",
                slug, score, node.id,
            )
            continue

        valid_tags.append(TagResult(tag_slug=slug, score=score))

    # Enforce max tags per source — keep highest scored
    valid_tags.sort(key=lambda t: t.score, reverse=True)
    valid_tags = valid_tags[:MAX_TAGS_PER_SOURCE]

    # Check for contradictory pairs
    tag_slugs = {t.tag_slug for t in valid_tags}
    contradictions: list[tuple[str, str]] = []
    for a, b in CONTRADICTORY_PAIRS:
        if a in tag_slugs and b in tag_slugs:
            contradictions.append((a, b))
            # Drop the lower-scored tag from the contradictory pair
            scores = {t.tag_slug: t.score for t in valid_tags}
            drop = a if scores.get(a, 0) < scores.get(b, 0) else b
            valid_tags = [t for t in valid_tags if t.tag_slug != drop]
            logger.warning(
                "Contradictory tags %s & %s on node %s — dropped %s",
                a, b, node.id, drop,
            )

    # Parse + validate extraction metadata
    metadata = _parse_extraction_metadata(raw_metadata)

    return ExtractionResult(
        node_id=node.id,
        node_name=node.name,
        city=node.city,
        tags=valid_tags,
        metadata=metadata,
        flagged_contradictions=contradictions,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _parse_extraction_response(text: str) -> tuple[list[dict], dict]:
    """
    Parse LLM response text into (tag_list, raw_metadata).

    Returns ([], {}) on parse failure — caller handles empty gracefully.
    Tolerates markdown code fences.
    """
    text = text.strip()

    def _extract_from_data(data: dict | list) -> tuple[list[dict], dict]:
        if isinstance(data, dict):
            tags = data.get("tags", [])
            metadata = data.get("metadata", {})
            if isinstance(tags, list):
                return tags, (metadata if isinstance(metadata, dict) else {})
        if isinstance(data, list):
            # Legacy: bare tag list with no metadata
            return data, {}
        return [], {}

    # Try direct JSON parse
    try:
        data = json.loads(text)
        return _extract_from_data(data)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from markdown code block
    if "```" in text:
        for block in text.split("```"):
            block = block.strip()
            if block.startswith("json"):
                block = block[4:].strip()
            try:
                data = json.loads(block)
                return _extract_from_data(data)
            except json.JSONDecodeError:
                continue

    logger.error("Failed to parse extraction response: %s", text[:200])
    return [], {}


_VALID_PRICE_SIGNALS: frozenset[str] = frozenset({"budget", "mid", "splurge", "free"})
_VALID_AUTHOR_TYPES: frozenset[str] = frozenset({"local", "expat", "tourist", "unknown"})


def _parse_extraction_metadata(raw: dict) -> ExtractionMetadata:
    """
    Validate and coerce raw metadata dict from LLM into ExtractionMetadata.

    Unknown or malformed values are coerced to safe defaults rather than
    raising — the extraction should never fail due to a metadata parse error.
    """
    overrated_flag = bool(raw.get("overrated_flag", False))
    explicit_recommendation = bool(raw.get("explicit_recommendation", False))

    raw_price = raw.get("price_signal")
    price_signal: PriceSignal = raw_price if raw_price in _VALID_PRICE_SIGNALS else None

    raw_author = raw.get("author_type", "unknown")
    author_type: AuthorType = raw_author if raw_author in _VALID_AUTHOR_TYPES else "unknown"

    crowd_notes_raw = raw.get("crowd_notes")
    crowd_notes: Optional[str] = str(crowd_notes_raw).strip() if crowd_notes_raw else None

    return ExtractionMetadata(
        overrated_flag=overrated_flag,
        price_signal=price_signal,
        explicit_recommendation=explicit_recommendation,
        author_type=author_type,
        crowd_notes=crowd_notes,
    )


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------

async def _fetch_untagged_nodes(
    pool: asyncpg.Pool,
    limit: int,
) -> list[NodeInput]:
    """
    Fetch ActivityNodes that have no llm_extraction vibe tags yet.

    Includes nodes in 'pending' or 'approved' status — new nodes created
    by scrapers start as 'pending' and must not be filtered out.
    The 'active' status does NOT exist in NodeStatus enum (pending/approved/
    flagged/archived are the valid values).
    """
    rows = await pool.fetch(
        """
        SELECT
            an.id, an.name, an.city, an.category,
            an."descriptionShort", an."descriptionLong"
        FROM "ActivityNode" an
        WHERE an."isCanonical" = true
          AND an.status IN ('pending', 'approved')
          AND NOT EXISTS (
            SELECT 1 FROM "ActivityNodeVibeTag" anvt
            WHERE anvt."activityNodeId" = an.id
              AND anvt.source = 'llm_extraction'
          )
        ORDER BY an."sourceCount" DESC, an."createdAt" ASC
        LIMIT $1
        """,
        limit,
    )

    nodes: list[NodeInput] = []
    for row in rows:
        nodes.append(NodeInput(
            id=row["id"],
            name=row["name"],
            city=row["city"],
            category=row["category"],
            description_short=row["descriptionShort"],
            description_long=row["descriptionLong"],
        ))

    return nodes


async def _fetch_quality_excerpts(
    pool: asyncpg.Pool,
    node_ids: list[str],
) -> dict[str, list[str]]:
    """Fetch quality signal excerpts for a batch of nodes."""
    if not node_ids:
        return {}

    rows = await pool.fetch(
        """
        SELECT "activityNodeId", "rawExcerpt"
        FROM "QualitySignal"
        WHERE "activityNodeId" = ANY($1::uuid[])
          AND "rawExcerpt" IS NOT NULL
        ORDER BY "sourceAuthority" DESC
        """,
        node_ids,
    )

    excerpts: dict[str, list[str]] = {}
    for row in rows:
        nid = row["activityNodeId"]
        if nid not in excerpts:
            excerpts[nid] = []
        # Cap at 10 excerpts per node to control input token count
        if len(excerpts[nid]) < 10:
            excerpts[nid].append(row["rawExcerpt"])

    return excerpts


async def _resolve_vibe_tag_ids(
    pool: asyncpg.Pool,
    tag_slugs: set[str],
) -> dict[str, str]:
    """Map tag slugs to VibeTag UUIDs."""
    if not tag_slugs:
        return {}

    rows = await pool.fetch(
        """
        SELECT id, slug FROM "VibeTag"
        WHERE slug = ANY($1::text[])
          AND "isActive" = true
        """,
        list(tag_slugs),
    )
    return {row["slug"]: row["id"] for row in rows}


async def _write_vibe_tags(
    pool: asyncpg.Pool,
    results: list[ExtractionResult],
    tag_id_map: dict[str, str],
) -> int:
    """Write extracted vibe tags to ActivityNodeVibeTag. Returns count written."""
    records: list[tuple] = []
    for result in results:
        for tag in result.tags:
            vibe_tag_id = tag_id_map.get(tag.tag_slug)
            if not vibe_tag_id:
                logger.warning("No VibeTag row for slug %r — skipping", tag.tag_slug)
                continue
            records.append((
                str(uuid4()),
                result.node_id,
                vibe_tag_id,
                tag.score,
                "llm_extraction",
            ))

    if not records:
        return 0

    await pool.executemany(
        """
        INSERT INTO "ActivityNodeVibeTag" (id, "activityNodeId", "vibeTagId", score, source)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT ("activityNodeId", "vibeTagId", source) DO UPDATE
          SET score = EXCLUDED.score
        """,
        records,
    )
    return len(records)


def _write_extraction_log(
    results: list[ExtractionResult],
    city: str,
) -> None:
    """
    Append per-venue extraction results to data/extraction_logs/{city}.jsonl.

    One JSON line per result. Used by canary review to inspect raw LLM output
    before aggregation. Non-blocking — errors are logged but never re-raised.
    """
    if not results:
        return

    log_path = EXTRACTION_LOG_DIR / f"{city.lower().replace(' ', '_').replace('-', '_')}.jsonl"
    try:
        with log_path.open("a", encoding="utf-8") as fh:
            for result in results:
                record = {
                    "node_id": result.node_id,
                    "node_name": result.node_name,
                    "city": result.city,
                    "extracted_at": datetime.now(timezone.utc).isoformat(),
                    "tags": [
                        {"tag": t.tag_slug, "score": t.score} for t in result.tags
                    ],
                    "metadata": {
                        "overrated_flag": result.metadata.overrated_flag,
                        "price_signal": result.metadata.price_signal,
                        "explicit_recommendation": result.metadata.explicit_recommendation,
                        "author_type": result.metadata.author_type,
                        "crowd_notes": result.metadata.crowd_notes,
                    },
                    "flagged_contradictions": [
                        list(pair) for pair in result.flagged_contradictions
                    ],
                }
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.debug(
            "Extraction log updated: %s (%d entries)", log_path, len(results)
        )
    except OSError as exc:
        logger.warning("Could not write extraction log to %s: %s", log_path, exc)


async def _log_to_model_registry(
    pool: asyncpg.Pool,
    stats: BatchStats,
) -> str:
    """Log extraction batch to ModelRegistry. Returns registry entry ID."""
    entry_id = str(uuid4())
    now = datetime.now(timezone.utc)

    await pool.execute(
        """
        INSERT INTO "ModelRegistry" (
            id, "modelName", "modelVersion", stage, "modelType",
            description, "configSnapshot", metrics, "evaluatedAt",
            "createdAt", "updatedAt"
        ) VALUES ($1, $2, $3, 'production', 'llm_extraction',
                  $4, $5, $6, $7, $8, $8)
        """,
        entry_id,
        MODEL_NAME,
        PROMPT_VERSION,
        f"Vibe extraction batch: {stats.nodes_processed} nodes, {stats.tags_written} tags",
        json.dumps({
            "model": MODEL_NAME,
            "prompt_version": PROMPT_VERSION,
            "confidence_threshold": CONFIDENCE_THRESHOLD,
            "max_tags_per_source": MAX_TAGS_PER_SOURCE,
            "batch_size": BATCH_SIZE,
        }),
        json.dumps({
            "nodes_processed": stats.nodes_processed,
            "tags_written": stats.tags_written,
            "nodes_skipped": stats.nodes_skipped,
            "contradictions_flagged": stats.contradictions_flagged,
            "total_input_tokens": stats.total_input_tokens,
            "total_output_tokens": stats.total_output_tokens,
            "estimated_cost_usd": round(stats.estimated_cost_usd, 6),
            "latency_seconds": round(stats.latency_seconds, 2),
            "errors": stats.errors[:20],  # cap error log size
        }),
        now,
        now,
    )
    return entry_id


# ---------------------------------------------------------------------------
# Core extraction pipeline
# ---------------------------------------------------------------------------

async def extract_vibe_tags_batch(
    pool: asyncpg.Pool,
    api_key: str,
    nodes: list[NodeInput],
) -> tuple[list[ExtractionResult], BatchStats]:
    """
    Extract vibe tags for a batch of nodes via Haiku.

    Returns (results, stats). Failures are logged in stats.errors
    and the batch continues — one bad node doesn't kill the run.
    """
    stats = BatchStats()
    results: list[ExtractionResult] = []

    # Pre-fetch quality excerpts for the batch
    node_ids = [n.id for n in nodes]
    excerpts = await _fetch_quality_excerpts(pool, node_ids)
    for node in nodes:
        node.quality_excerpts = excerpts.get(node.id, [])

    start = time.monotonic()

    async with httpx.AsyncClient() as client:
        for node in nodes:
            result = await _extract_single_node(client, api_key, node, stats)
            if result:
                results.append(result)

    stats.latency_seconds = time.monotonic() - start

    # Write tags to DB
    if results:
        all_slugs = {t.tag_slug for r in results for t in r.tags}
        tag_id_map = await _resolve_vibe_tag_ids(pool, all_slugs)
        stats.tags_written = await _write_vibe_tags(pool, results, tag_id_map)

        # Append extraction log for canary review (grouped by city)
        city_groups: dict[str, list[ExtractionResult]] = {}
        for r in results:
            city_groups.setdefault(r.city, []).append(r)
        for city, city_results in city_groups.items():
            _write_extraction_log(city_results, city)

    # Compute cost
    stats.estimated_cost_usd = (
        (stats.total_input_tokens / 1_000_000) * INPUT_COST_PER_1M
        + (stats.total_output_tokens / 1_000_000) * OUTPUT_COST_PER_1M
    )

    return results, stats


async def _extract_single_node(
    client: httpx.AsyncClient,
    api_key: str,
    node: NodeInput,
    stats: BatchStats,
) -> Optional[ExtractionResult]:
    """Extract tags for a single node with retries."""
    for attempt in range(MAX_RETRIES):
        try:
            result = await _call_haiku(client, api_key, node)
            stats.nodes_processed += 1
            stats.total_input_tokens += result.input_tokens
            stats.total_output_tokens += result.output_tokens
            stats.contradictions_flagged += len(result.flagged_contradictions)

            if not result.tags:
                stats.nodes_skipped += 1
                logger.info("No tags above threshold for node %s (%s)", node.id, node.name)

            return result

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 429 or status >= 500:
                wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                logger.warning(
                    "Haiku API %d for node %s, retry %d/%d in %.1fs",
                    status, node.id, attempt + 1, MAX_RETRIES, wait,
                )
                await asyncio.sleep(wait)
                continue
            # Non-retryable HTTP error
            msg = f"HTTP {status} for node {node.id}: {exc.response.text[:200]}"
            stats.errors.append(msg)
            stats.nodes_skipped += 1
            logger.error(msg)
            return None

        except Exception as exc:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                logger.warning(
                    "Error for node %s, retry %d/%d: %s",
                    node.id, attempt + 1, MAX_RETRIES, exc,
                )
                await asyncio.sleep(wait)
                continue

            msg = f"Failed after {MAX_RETRIES} attempts for node {node.id}: {exc}"
            stats.errors.append(msg)
            stats.nodes_skipped += 1
            logger.error(msg)
            return None

    return None


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

async def run_extraction(
    pool: asyncpg.Pool,
    api_key: str,
    limit: int = 50,
) -> BatchStats:
    """
    Main entry point: fetch untagged nodes and extract vibe tags.

    Args:
        pool: asyncpg connection pool
        api_key: Anthropic API key
        limit: max nodes to process (default 50)

    Returns:
        BatchStats with full run metrics
    """
    logger.info("Starting vibe extraction run (limit=%d)", limit)

    nodes = await _fetch_untagged_nodes(pool, limit)
    if not nodes:
        logger.info("No untagged nodes found — nothing to do")
        return BatchStats()

    logger.info("Found %d untagged nodes to process", len(nodes))

    # Process in batches to avoid holding too many connections
    all_stats = BatchStats()

    for i in range(0, len(nodes), BATCH_SIZE):
        batch = nodes[i : i + BATCH_SIZE]
        logger.info(
            "Processing batch %d/%d (%d nodes)",
            (i // BATCH_SIZE) + 1,
            (len(nodes) + BATCH_SIZE - 1) // BATCH_SIZE,
            len(batch),
        )

        _, batch_stats = await extract_vibe_tags_batch(pool, api_key, batch)

        # Accumulate stats
        all_stats.nodes_processed += batch_stats.nodes_processed
        all_stats.tags_written += batch_stats.tags_written
        all_stats.nodes_skipped += batch_stats.nodes_skipped
        all_stats.contradictions_flagged += batch_stats.contradictions_flagged
        all_stats.total_input_tokens += batch_stats.total_input_tokens
        all_stats.total_output_tokens += batch_stats.total_output_tokens
        all_stats.estimated_cost_usd += batch_stats.estimated_cost_usd
        all_stats.latency_seconds += batch_stats.latency_seconds
        all_stats.errors.extend(batch_stats.errors)

    # Log to model registry
    registry_id = await _log_to_model_registry(pool, all_stats)
    logger.info(
        "Extraction complete: %d nodes → %d tags, cost=$%.4f, registry=%s",
        all_stats.nodes_processed,
        all_stats.tags_written,
        all_stats.estimated_cost_usd,
        registry_id,
    )

    return all_stats
