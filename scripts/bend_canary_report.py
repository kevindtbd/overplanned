#!/usr/bin/env python3
"""
Bend, OR Canary Report Generator.

Queries the database after a Bend pipeline run and produces a human-readable
review report for manual validation that the pipeline produces authentic,
local-first recommendations.

Output:
  - JSON: data/canary_reports/bend_report.json
  - Stdout: formatted terminal table

Usage:
    python scripts/bend_canary_report.py
    python scripts/bend_canary_report.py --database-url postgresql://...
    python scripts/bend_canary_report.py --city portland  # any seeded city
    python scripts/bend_canary_report.py --json-only       # suppress terminal output
"""

import argparse
import json
import logging
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import asyncpg

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("data/canary_reports")

# Tourist score threshold above which a node is flagged as a possible tourist trap
TOURIST_TRAP_THRESHOLD = 0.5

# Low confidence: only 1 source AND average data_confidence below this
LOW_CONFIDENCE_THRESHOLD = 0.4

# Bend should have outdoor/active content — these categories are required for
# the pipeline to be considered non-trivially correct for an outdoor city
REQUIRED_CATEGORIES_OUTDOOR_CITY = {"outdoors", "active"}

# Categories expected in any well-seeded city
MIN_REQUIRED_CATEGORIES = 3

# How many quality signal excerpts to include per node in the report
MAX_EXCERPTS_PER_NODE = 3

# Any node whose name exactly matches a known chain (lowercased, stripped) is flagged
COMMON_CHAIN_NAMES = {
    "mcdonalds", "mcdonald's", "burger king", "wendys", "wendy's",
    "taco bell", "subway", "chick-fil-a", "chick fil a",
    "dunkin", "starbucks", "panda express", "chipotle",
    "olive garden", "applebees", "applebee's",
    "dominos", "domino's", "pizza hut", "five guys",
    "in-n-out", "popeyes", "kfc", "panera", "panera bread",
}


# ---------------------------------------------------------------------------
# Data classes for report
# ---------------------------------------------------------------------------

@dataclass
class NodeReport:
    """Report entry for a single ActivityNode."""
    id: str
    name: str
    category: str
    status: str
    tourist_score: Optional[float]
    convergence_score: Optional[float]
    vibe_tags: list[str]
    source_count: int
    source_breakdown: dict[str, int]  # source_name -> count
    excerpts: list[str]
    avg_data_confidence: Optional[float]
    overrated_flag_mentions: int
    flags: list[str]  # human-readable flag reasons


@dataclass
class CanaryReport:
    """Full canary report for a city."""
    city: str
    generated_at: str
    total_nodes: int
    unique_sources: int
    avg_confidence: float
    category_distribution: dict[str, int]
    vibe_tag_histogram: dict[str, int]
    flagged_tourist_traps: list[NodeReport]
    low_confidence_nodes: list[NodeReport]
    chain_leakage: list[NodeReport]
    missing_categories: list[str]
    all_nodes: list[NodeReport]
    summary_issues: list[str]


# ---------------------------------------------------------------------------
# Database queries
# ---------------------------------------------------------------------------

async def fetch_nodes(conn: asyncpg.Connection, city_name: str) -> list[dict]:
    """Fetch all canonical ActivityNodes for a city with vibe tags."""
    rows = await conn.fetch(
        """
        SELECT
            an.id,
            an.name,
            an.category,
            an.status,
            an.tourist_score,
            an."convergenceScore",
            an."sourceCount",
            COALESCE(
                array_agg(DISTINCT vt.slug) FILTER (WHERE vt.slug IS NOT NULL),
                ARRAY[]::text[]
            ) AS vibe_tags
        FROM activity_nodes an
        LEFT JOIN activity_node_vibe_tags anvt ON anvt."activityNodeId" = an.id
        LEFT JOIN vibe_tags vt ON vt.id = anvt."vibeTagId"
        WHERE an.city = $1
          AND an."isCanonical" = true
        GROUP BY an.id, an.name, an.category, an.status,
                 an.tourist_score, an."convergenceScore", an."sourceCount"
        ORDER BY an."convergenceScore" DESC NULLS LAST, an.name
        """,
        city_name,
    )
    return [dict(r) for r in rows]


async def fetch_quality_signals(
    conn: asyncpg.Connection,
    node_ids: list[str],
) -> dict[str, list[dict]]:
    """
    Fetch QualitySignals for a list of node IDs.

    Returns a dict mapping activityNodeId -> list of signal dicts.
    """
    if not node_ids:
        return {}

    rows = await conn.fetch(
        """
        SELECT
            qs."activityNodeId",
            qs."sourceName",
            qs."rawExcerpt",
            qs."extractionMetadata",
            qs."sourceAuthority"
        FROM quality_signals qs
        WHERE qs."activityNodeId" = ANY($1::text[])
        ORDER BY qs."sourceAuthority" DESC, qs."createdAt" DESC
        """,
        node_ids,
    )

    result: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        result[row["activityNodeId"]].append(dict(row))
    return result


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def _extract_data_confidence(signals: list[dict]) -> Optional[float]:
    """
    Extract average data_confidence from extractionMetadata.

    extractionMetadata is a JSON field that may contain { data_confidence: float }.
    """
    confidences: list[float] = []
    for sig in signals:
        meta = sig.get("extractionMetadata")
        if not meta:
            continue
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                continue
        if isinstance(meta, dict):
            val = meta.get("data_confidence")
            if val is not None:
                try:
                    confidences.append(float(val))
                except (TypeError, ValueError):
                    pass
    return round(sum(confidences) / len(confidences), 3) if confidences else None


def _count_overrated_flag(signals: list[dict]) -> int:
    """Count how many signals mention an overrated_flag in extractionMetadata."""
    count = 0
    for sig in signals:
        meta = sig.get("extractionMetadata")
        if not meta:
            continue
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                continue
        if isinstance(meta, dict) and meta.get("overrated_flag"):
            count += 1
    return count


def _source_breakdown(signals: list[dict]) -> dict[str, int]:
    """Count signals per source name."""
    counts: dict[str, int] = Counter()
    for sig in signals:
        name = sig.get("sourceName") or "unknown"
        counts[name] += 1
    return dict(counts)


def _top_excerpts(signals: list[dict], max_count: int = MAX_EXCERPTS_PER_NODE) -> list[str]:
    """Return the top N non-empty raw excerpts, highest authority first."""
    excerpts: list[str] = []
    for sig in signals:
        excerpt = sig.get("rawExcerpt")
        if excerpt and excerpt.strip():
            excerpts.append(excerpt.strip())
        if len(excerpts) >= max_count:
            break
    return excerpts


def _detect_chain_leakage(name: str) -> bool:
    """Return True if the node name matches a known chain (case-insensitive)."""
    cleaned = name.lower().strip()
    # Exact match or "starts with" (catches "Starbucks on Bond Street")
    for chain in COMMON_CHAIN_NAMES:
        if cleaned == chain or cleaned.startswith(chain + " ") or cleaned.startswith(chain + ","):
            return True
    return False


def build_node_report(
    node: dict,
    signals: list[dict],
) -> NodeReport:
    """Build a NodeReport from a raw DB row + its quality signals."""
    flags: list[str] = []

    tourist_score = node.get("tourist_score")
    convergence_score = node.get("convergenceScore")
    source_count = node.get("sourceCount") or len(set(s["sourceName"] for s in signals))

    avg_confidence = _extract_data_confidence(signals)
    overrated_count = _count_overrated_flag(signals)
    breakdown = _source_breakdown(signals)
    excerpts = _top_excerpts(signals)

    # Flag: possible tourist trap
    if tourist_score is not None and tourist_score > TOURIST_TRAP_THRESHOLD:
        flags.append(f"POSSIBLE TOURIST TRAP (tourist_score={tourist_score:.2f})")

    # Flag: low confidence
    if source_count <= 1:
        if avg_confidence is not None and avg_confidence < LOW_CONFIDENCE_THRESHOLD:
            flags.append(f"LOW CONFIDENCE (1 source, avg_confidence={avg_confidence:.2f})")
        elif avg_confidence is None:
            flags.append("LOW CONFIDENCE (1 source, no confidence data)")

    # Flag: overrated mentions
    if overrated_count > 0:
        flags.append(f"OVERRATED FLAG ({overrated_count} signal(s) flagged)")

    # Flag: chain leakage
    if _detect_chain_leakage(node["name"]):
        flags.append("CHAIN LEAKAGE (stopword not caught)")

    return NodeReport(
        id=node["id"],
        name=node["name"],
        category=node["category"],
        status=node["status"],
        tourist_score=tourist_score,
        convergence_score=convergence_score,
        vibe_tags=list(node.get("vibe_tags") or []),
        source_count=source_count,
        source_breakdown=breakdown,
        excerpts=excerpts,
        avg_data_confidence=avg_confidence,
        overrated_flag_mentions=overrated_count,
        flags=flags,
    )


def assemble_report(
    city_name: str,
    node_rows: list[dict],
    signals_by_node: dict[str, list[dict]],
) -> CanaryReport:
    """Assemble the full CanaryReport from fetched DB data."""
    all_nodes: list[NodeReport] = []
    category_dist: dict[str, int] = Counter()
    vibe_histogram: dict[str, int] = Counter()
    all_source_names: set[str] = set()
    all_confidences: list[float] = []

    for row in node_rows:
        node_id = row["id"]
        sigs = signals_by_node.get(node_id, [])
        nr = build_node_report(row, sigs)
        all_nodes.append(nr)

        category_dist[nr.category] += 1
        for tag in nr.vibe_tags:
            vibe_histogram[tag] += 1
        all_source_names.update(nr.source_breakdown.keys())
        if nr.avg_data_confidence is not None:
            all_confidences.append(nr.avg_data_confidence)

    avg_confidence = (
        round(sum(all_confidences) / len(all_confidences), 3)
        if all_confidences
        else 0.0
    )

    flagged_tourist_traps = [n for n in all_nodes if any("TOURIST TRAP" in f for f in n.flags)]
    low_confidence_nodes = [n for n in all_nodes if any("LOW CONFIDENCE" in f for f in n.flags)]
    chain_leakage = [n for n in all_nodes if any("CHAIN LEAKAGE" in f for f in n.flags)]

    # Detect missing categories
    present_categories = set(category_dist.keys())
    missing_categories: list[str] = []

    # For outdoor-first cities (Bend, Asheville), flag if outdoor/active are absent
    city_lower = city_name.lower()
    if city_lower in ("bend", "asheville", "denver"):
        for cat in REQUIRED_CATEGORIES_OUTDOOR_CITY:
            if cat not in present_categories:
                missing_categories.append(cat)

    # All cities: warn if fewer than MIN_REQUIRED_CATEGORIES
    if len(present_categories) < MIN_REQUIRED_CATEGORIES:
        missing_categories.append(
            f"ONLY {len(present_categories)} category/ies present "
            f"(minimum {MIN_REQUIRED_CATEGORIES})"
        )

    # Build summary issues
    summary_issues: list[str] = []
    if not all_nodes:
        summary_issues.append("CRITICAL: Zero canonical nodes found — pipeline may not have run")
    if flagged_tourist_traps:
        summary_issues.append(
            f"{len(flagged_tourist_traps)} node(s) flagged as possible tourist traps"
        )
    if low_confidence_nodes:
        summary_issues.append(
            f"{len(low_confidence_nodes)} node(s) with low confidence / single source"
        )
    if chain_leakage:
        summary_issues.append(
            f"{len(chain_leakage)} chain(s) leaked through stopword filter"
        )
    if missing_categories:
        summary_issues.append(
            f"Missing expected categories: {', '.join(missing_categories)}"
        )
    if not summary_issues:
        summary_issues.append("No critical issues detected")

    return CanaryReport(
        city=city_name,
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_nodes=len(all_nodes),
        unique_sources=len(all_source_names),
        avg_confidence=avg_confidence,
        category_distribution=dict(sorted(category_dist.items(), key=lambda x: -x[1])),
        vibe_tag_histogram=dict(sorted(vibe_histogram.items(), key=lambda x: -x[1])),
        flagged_tourist_traps=flagged_tourist_traps,
        low_confidence_nodes=low_confidence_nodes,
        chain_leakage=chain_leakage,
        missing_categories=missing_categories,
        all_nodes=all_nodes,
        summary_issues=summary_issues,
    )


# ---------------------------------------------------------------------------
# Terminal rendering
# ---------------------------------------------------------------------------

def _format_sources(breakdown: dict[str, int]) -> str:
    """Format source breakdown as 'Reddit (3), Foursquare (1)'."""
    parts = [f"{name} ({count})" for name, count in sorted(breakdown.items())]
    return ", ".join(parts) if parts else "none"


def _flag_label(flags: list[str]) -> str:
    """Return the header label for a node based on its flags."""
    if any("CHAIN LEAKAGE" in f for f in flags):
        return "FLAG: CHAIN LEAKED"
    if any("TOURIST TRAP" in f for f in flags):
        return "FLAG: POSSIBLE TOURIST TRAP"
    if any("OVERRATED" in f for f in flags):
        return "FLAG: OVERRATED SIGNAL"
    if any("LOW CONFIDENCE" in f for f in flags):
        return "LOW CONFIDENCE"
    return "HIGH CONFIDENCE"


def _render_node(nr: NodeReport) -> str:
    """Render a single NodeReport as a terminal block."""
    label = _flag_label(nr.flags)
    lines: list[str] = []
    lines.append(f"[{label}] {nr.name}")
    lines.append(
        f"  Category: {nr.category} | "
        f"Tourist: {f'{nr.tourist_score:.2f}' if nr.tourist_score is not None else 'n/a'} | "
        f"Convergence: {f'{nr.convergence_score:.2f}' if nr.convergence_score is not None else 'n/a'}"
    )
    if nr.vibe_tags:
        lines.append(f"  Tags: {', '.join(nr.vibe_tags)}")
    else:
        lines.append("  Tags: (none)")
    lines.append(f"  Sources: {_format_sources(nr.source_breakdown)}")
    if nr.avg_data_confidence is not None:
        lines.append(f"  Avg confidence: {nr.avg_data_confidence:.2f}")
    for excerpt in nr.excerpts:
        # Truncate long excerpts for readability
        short = excerpt[:120] + "..." if len(excerpt) > 120 else excerpt
        lines.append(f'  "{short}"')
    if nr.flags:
        for flag in nr.flags:
            lines.append(f"  !! {flag}")
    return "\n".join(lines)


def render_terminal_report(report: CanaryReport) -> str:
    """Render the full report as a terminal string."""
    lines: list[str] = []

    lines.append("")
    lines.append(f"=== {report.city.upper()} — Canary Report ===")
    lines.append(
        f"Nodes: {report.total_nodes} | "
        f"Sources: {report.unique_sources} | "
        f"Avg Confidence: {report.avg_confidence:.2f}"
    )
    lines.append(f"Generated: {report.generated_at}")
    lines.append("")

    # Summary issues
    lines.append("--- SUMMARY ---")
    for issue in report.summary_issues:
        lines.append(f"  * {issue}")
    lines.append("")

    # Category distribution
    lines.append("--- CATEGORY DISTRIBUTION ---")
    total = max(report.total_nodes, 1)
    for cat, count in report.category_distribution.items():
        pct = count / total * 100
        bar = "#" * int(pct / 2)  # scale bar to ~50 chars max
        lines.append(f"  {cat:<20} {count:>4}  ({pct:5.1f}%)  {bar}")
    lines.append("")

    # Vibe tag histogram (top 20)
    lines.append("--- VIBE TAG DISTRIBUTION (top 20) ---")
    top_tags = sorted(report.vibe_tag_histogram.items(), key=lambda x: -x[1])[:20]
    for tag, count in top_tags:
        lines.append(f"  {tag:<30} {count:>4}")
    if len(report.vibe_tag_histogram) > 20:
        lines.append(f"  ... and {len(report.vibe_tag_histogram) - 20} more tags")
    lines.append("")

    # Missing categories
    if report.missing_categories:
        lines.append("--- MISSING CATEGORIES (pipeline failure indicator) ---")
        for cat in report.missing_categories:
            lines.append(f"  !! {cat}")
        lines.append("")

    # Chain leakage
    if report.chain_leakage:
        lines.append(f"--- CHAIN LEAKAGE ({len(report.chain_leakage)} node(s)) ---")
        for nr in report.chain_leakage:
            lines.append(_render_node(nr))
            lines.append("")

    # Tourist traps
    if report.flagged_tourist_traps:
        lines.append(
            f"--- FLAGGED NODES: POSSIBLE TOURIST TRAPS ({len(report.flagged_tourist_traps)}) ---"
        )
        for nr in report.flagged_tourist_traps:
            lines.append(_render_node(nr))
            lines.append("")

    # Low confidence
    if report.low_confidence_nodes:
        lines.append(
            f"--- LOW CONFIDENCE NODES ({len(report.low_confidence_nodes)}) ---"
        )
        for nr in report.low_confidence_nodes:
            lines.append(_render_node(nr))
            lines.append("")

    # All nodes (clean list)
    lines.append(f"--- ALL NODES ({report.total_nodes}) ---")
    for nr in report.all_nodes:
        lines.append(_render_node(nr))
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON serialization helper
# ---------------------------------------------------------------------------

def _report_to_dict(report: CanaryReport) -> dict[str, Any]:
    """Convert CanaryReport to a JSON-serializable dict."""
    def node_to_dict(nr: NodeReport) -> dict:
        return {
            "id": nr.id,
            "name": nr.name,
            "category": nr.category,
            "status": nr.status,
            "tourist_score": nr.tourist_score,
            "convergence_score": nr.convergence_score,
            "vibe_tags": nr.vibe_tags,
            "source_count": nr.source_count,
            "source_breakdown": nr.source_breakdown,
            "excerpts": nr.excerpts,
            "avg_data_confidence": nr.avg_data_confidence,
            "overrated_flag_mentions": nr.overrated_flag_mentions,
            "flags": nr.flags,
        }

    return {
        "city": report.city,
        "generated_at": report.generated_at,
        "total_nodes": report.total_nodes,
        "unique_sources": report.unique_sources,
        "avg_confidence": report.avg_confidence,
        "category_distribution": report.category_distribution,
        "vibe_tag_histogram": report.vibe_tag_histogram,
        "summary_issues": report.summary_issues,
        "missing_categories": report.missing_categories,
        "flagged_tourist_traps": [node_to_dict(n) for n in report.flagged_tourist_traps],
        "low_confidence_nodes": [node_to_dict(n) for n in report.low_confidence_nodes],
        "chain_leakage": [node_to_dict(n) for n in report.chain_leakage],
        "all_nodes": [node_to_dict(n) for n in report.all_nodes],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def generate_report(
    database_url: str,
    city_name: str = "Bend",
    json_only: bool = False,
) -> CanaryReport:
    """
    Generate a canary report for a city.

    Args:
        database_url: PostgreSQL connection string.
        city_name: Canonical city name (matches ActivityNode.city).
        json_only: If True, suppress terminal output (still writes JSON).

    Returns:
        Assembled CanaryReport.
    """
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=3)
    try:
        async with pool.acquire() as conn:
            logger.info("Fetching nodes for city: %s", city_name)
            node_rows = await fetch_nodes(conn, city_name)

            if not node_rows:
                logger.warning("No canonical nodes found for %s", city_name)

            node_ids = [r["id"] for r in node_rows]
            logger.info("Fetching quality signals for %d nodes...", len(node_ids))
            signals_by_node = await fetch_quality_signals(conn, node_ids)

        report = assemble_report(city_name, node_rows, signals_by_node)

        # Write JSON output
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        city_slug = city_name.lower().replace(" ", "-")
        json_path = OUTPUT_DIR / f"{city_slug}_report.json"
        with open(json_path, "w") as f:
            json.dump(_report_to_dict(report), f, indent=2)
        logger.info("JSON report written to %s", json_path)

        # Print terminal output
        if not json_only:
            print(render_terminal_report(report))

        return report
    finally:
        await pool.close()


async def main() -> None:
    """CLI entry point."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        description="Generate a canary review report for a seeded city"
    )
    parser.add_argument(
        "--city",
        default="Bend",
        help="Canonical city name to report on (default: Bend)",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="PostgreSQL connection string (or set DATABASE_URL env var)",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Suppress terminal output, only write JSON file",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not args.database_url:
        print("ERROR: DATABASE_URL not set. Pass --database-url or set the env var.", file=sys.stderr)
        sys.exit(1)

    report = await generate_report(
        args.database_url,
        city_name=args.city,
        json_only=args.json_only,
    )

    if report.summary_issues and report.summary_issues != ["No critical issues detected"]:
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
