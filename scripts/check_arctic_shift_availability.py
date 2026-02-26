#!/usr/bin/env python3
"""
Arctic Shift Data Availability Checker.

Checks whether Parquet dump files exist for the subreddits required by a
given city config before running the pipeline. Run this BEFORE seed_city()
to verify data is available.

Checks:
  - Parquet file exists for each subreddit in the city config
  - Reports: total posts, date range, score distribution
  - Reports: estimated posts passing the quality filter
  - Exits 0 if all required subreddits have data, 1 if any are missing

Usage:
    python scripts/check_arctic_shift_availability.py --city bend
    python scripts/check_arctic_shift_availability.py --city bend --data-dir /data/arctic_shift
    python scripts/check_arctic_shift_availability.py --city bend --require-all
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default directory where Arctic Shift Parquet dumps are stored
DEFAULT_DATA_DIR = Path("data/arctic_shift")

# Quality filter thresholds matching the ArcticShiftScraper defaults
QUALITY_MIN_SCORE = 3          # minimum upvote score
QUALITY_MIN_COMMENT_DEPTH = 0  # minimum comment depth (top-level = 0)
QUALITY_MIN_BODY_LEN = 20      # minimum post body character length

# Subreddits covering Bend — derived from city_configs.py but kept here
# for standalone use without importing pipeline code
SUBREDDIT_TARGETS: dict[str, list[str]] = {
    "bend": ["bend", "bendoregon", "centraloregon"],
    "tacoma": ["tacoma", "pnw"],
    "nashville": ["nashville", "visitingnashville"],
    "portland": ["portland", "askportland", "portlandfood"],
    "austin": ["austin", "austinfood"],
    "denver": ["denver", "denverfood"],
    "seattle": ["seattle", "seattlewa", "seattlefood", "seattlebeer"],
    "asheville": ["asheville", "ashevillefood", "wnc"],
    "new-orleans": ["asknola", "neworleans", "nola", "neworleansfood"],
    "mexico-city": ["mexicocity", "cdmx"],
}


# ---------------------------------------------------------------------------
# Parquet reading (tries pyarrow, falls back to pandas, then errors gracefully)
# ---------------------------------------------------------------------------

def _try_read_parquet(path: Path) -> Optional[Any]:
    """
    Attempt to read a Parquet file.

    Returns a DataFrame-like object with columns ['score', 'created_utc', 'selftext']
    if readable, otherwise returns None with a warning.
    """
    try:
        import pyarrow.parquet as pq  # type: ignore
        table = pq.read_table(str(path), columns=["score", "created_utc", "selftext"])
        return table.to_pandas()
    except ImportError:
        pass

    try:
        import pandas as pd  # type: ignore
        return pd.read_parquet(str(path), columns=["score", "created_utc", "selftext"])
    except ImportError:
        logger.warning(
            "Neither pyarrow nor pandas is installed — cannot read Parquet file stats. "
            "Install pyarrow: pip install pyarrow"
        )
        return None
    except Exception as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# Per-subreddit check
# ---------------------------------------------------------------------------

def _find_parquet_file(data_dir: Path, subreddit: str) -> Optional[Path]:
    """
    Find a Parquet dump file for a subreddit.

    Checks common naming patterns:
      - {subreddit}.parquet
      - r_{subreddit}.parquet
      - {subreddit}_posts.parquet
      - submissions_{subreddit}.parquet
    """
    candidates = [
        data_dir / f"{subreddit}.parquet",
        data_dir / f"r_{subreddit}.parquet",
        data_dir / f"{subreddit}_posts.parquet",
        data_dir / f"submissions_{subreddit}.parquet",
        data_dir / subreddit / "posts.parquet",
        data_dir / subreddit / f"{subreddit}.parquet",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _analyze_subreddit(
    data_dir: Path,
    subreddit: str,
) -> dict[str, Any]:
    """
    Analyze a subreddit's Parquet dump.

    Returns a dict with:
      - found: bool
      - path: str or None
      - total_posts: int
      - date_range: [min_date, max_date] or None
      - score_distribution: {p25, p50, p75, p90}
      - posts_passing_quality_filter: int
      - quality_filter_pass_rate: float
    """
    result: dict[str, Any] = {
        "subreddit": f"r/{subreddit}",
        "found": False,
        "path": None,
        "total_posts": 0,
        "date_range": None,
        "score_distribution": None,
        "posts_passing_quality_filter": 0,
        "quality_filter_pass_rate": 0.0,
        "error": None,
    }

    path = _find_parquet_file(data_dir, subreddit)
    if path is None:
        result["error"] = f"No Parquet file found in {data_dir} (tried common patterns)"
        return result

    result["found"] = True
    result["path"] = str(path)

    df = _try_read_parquet(path)
    if df is None:
        result["error"] = "File found but could not be parsed (missing pyarrow/pandas)"
        return result

    try:
        total = len(df)
        result["total_posts"] = total

        # Date range
        if "created_utc" in df.columns and total > 0:
            try:
                import pandas as pd  # type: ignore
                ts = pd.to_datetime(df["created_utc"], unit="s", utc=True, errors="coerce")
                ts = ts.dropna()
                if len(ts) > 0:
                    result["date_range"] = [
                        ts.min().strftime("%Y-%m-%d"),
                        ts.max().strftime("%Y-%m-%d"),
                    ]
            except Exception:
                pass

        # Score distribution
        if "score" in df.columns and total > 0:
            scores = df["score"].dropna()
            try:
                result["score_distribution"] = {
                    "p25": float(scores.quantile(0.25)),
                    "p50": float(scores.quantile(0.50)),
                    "p75": float(scores.quantile(0.75)),
                    "p90": float(scores.quantile(0.90)),
                    "max": float(scores.max()),
                }
            except Exception:
                pass

        # Quality filter
        passing = df.copy()
        if "score" in passing.columns:
            passing = passing[passing["score"] >= QUALITY_MIN_SCORE]
        if "selftext" in passing.columns:
            passing = passing[
                passing["selftext"].notna()
                & (passing["selftext"].str.len() >= QUALITY_MIN_BODY_LEN)
            ]
        pass_count = len(passing)
        result["posts_passing_quality_filter"] = pass_count
        result["quality_filter_pass_rate"] = (
            round(pass_count / total, 3) if total > 0 else 0.0
        )

    except Exception as exc:
        result["error"] = f"Analysis failed: {exc}"

    return result


# ---------------------------------------------------------------------------
# City-level check
# ---------------------------------------------------------------------------

def check_city_availability(
    city_slug: str,
    data_dir: Path,
) -> dict[str, Any]:
    """
    Check Arctic Shift data availability for all subreddits in a city.

    Returns a summary dict with per-subreddit breakdowns.
    """
    # Try to get the actual subreddit list from city_configs if available
    subreddits: list[str] = []
    try:
        import sys as _sys
        # Add project root to path for import
        project_root = Path(__file__).parent.parent
        if str(project_root) not in _sys.path:
            _sys.path.insert(0, str(project_root))
        from services.api.pipeline.city_configs import get_city_config  # type: ignore
        config = get_city_config(city_slug)
        subreddits = list(config.subreddits.keys())
        logger.info("Loaded subreddits from city_configs: %s", subreddits)
    except Exception:
        subreddits = SUBREDDIT_TARGETS.get(city_slug, [])
        if not subreddits:
            logger.warning(
                "Unknown city slug %r — no subreddit targets found. "
                "Known slugs: %s",
                city_slug,
                ", ".join(sorted(SUBREDDIT_TARGETS.keys())),
            )

    subreddit_results: list[dict] = []
    missing: list[str] = []
    available: list[str] = []

    for sub in subreddits:
        res = _analyze_subreddit(data_dir, sub)
        subreddit_results.append(res)
        if res["found"]:
            available.append(sub)
        else:
            missing.append(sub)

    total_available_posts = sum(
        r["total_posts"] for r in subreddit_results if r["found"]
    )
    total_quality_posts = sum(
        r["posts_passing_quality_filter"] for r in subreddit_results if r["found"]
    )

    return {
        "city": city_slug,
        "data_dir": str(data_dir),
        "subreddits_checked": len(subreddits),
        "subreddits_available": len(available),
        "subreddits_missing": len(missing),
        "missing_subreddits": missing,
        "available_subreddits": available,
        "total_available_posts": total_available_posts,
        "total_posts_passing_quality_filter": total_quality_posts,
        "ready_to_seed": len(missing) == 0,
        "subreddit_details": subreddit_results,
    }


# ---------------------------------------------------------------------------
# Terminal rendering
# ---------------------------------------------------------------------------

def render_check_report(result: dict[str, Any]) -> str:
    """Format the availability check result for terminal output."""
    lines: list[str] = []

    lines.append("")
    lines.append(f"=== Arctic Shift Data Check: {result['city'].upper()} ===")
    lines.append(f"Data directory: {result['data_dir']}")
    lines.append(
        f"Subreddits: {result['subreddits_available']}/{result['subreddits_checked']} available"
    )

    if result["ready_to_seed"]:
        lines.append("Status: READY TO SEED")
    else:
        lines.append(
            f"Status: NOT READY — missing {result['subreddits_missing']} subreddit(s)"
        )

    lines.append(
        f"Total posts available: {result['total_available_posts']:,} "
        f"({result['total_posts_passing_quality_filter']:,} pass quality filter)"
    )
    lines.append("")

    for sub_result in result["subreddit_details"]:
        sub = sub_result["subreddit"]
        if sub_result["found"]:
            lines.append(f"  [OK] {sub}")
            lines.append(f"       Path: {sub_result['path']}")
            lines.append(f"       Posts: {sub_result['total_posts']:,}")
            if sub_result["date_range"]:
                lines.append(
                    f"       Date range: {sub_result['date_range'][0]} to {sub_result['date_range'][1]}"
                )
            if sub_result["score_distribution"]:
                sd = sub_result["score_distribution"]
                lines.append(
                    f"       Score p25/p50/p75/p90: "
                    f"{sd['p25']:.0f} / {sd['p50']:.0f} / {sd['p75']:.0f} / {sd['p90']:.0f}"
                )
            lines.append(
                f"       Quality filter pass: "
                f"{sub_result['posts_passing_quality_filter']:,} "
                f"({sub_result['quality_filter_pass_rate']:.1%})"
            )
        else:
            lines.append(f"  [MISSING] {sub}")
            if sub_result.get("error"):
                lines.append(f"       {sub_result['error']}")
        lines.append("")

    if result["missing_subreddits"]:
        lines.append("Missing subreddits:")
        for sub in result["missing_subreddits"]:
            lines.append(f"  r/{sub}")
        lines.append("")
        lines.append(
            "To download missing dumps, use Arctic Shift's bulk download tool:"
        )
        lines.append(
            "  https://arctic-shift.photon-reddit.com/download"
        )
        lines.append(
            "  Download the subreddit Parquet files and place them in:"
        )
        lines.append(f"  {result['data_dir']}/")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Check Arctic Shift Parquet availability for a city"
    )
    parser.add_argument(
        "--city",
        default="bend",
        help=(
            "City slug to check (default: bend). "
            f"Known slugs: {', '.join(sorted(SUBREDDIT_TARGETS.keys()))}"
        ),
    )
    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help=f"Path to Arctic Shift Parquet dump directory (default: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--require-all",
        action="store_true",
        help="Exit 1 if any subreddit is missing (default: only warn)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output JSON instead of human-readable text",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    data_dir = Path(args.data_dir)
    result = check_city_availability(args.city, data_dir)

    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        print(render_check_report(result))

    if args.require_all and not result["ready_to_seed"]:
        sys.exit(1)

    if result["subreddits_missing"] > 0 and not args.require_all:
        # Soft warning — some subreddits missing but not all, pipeline can still run
        sys.exit(0)


if __name__ == "__main__":
    main()
