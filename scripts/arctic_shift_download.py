"""
Arctic Shift Reddit data downloader.

Downloads posts and comments from the Arctic Shift API for configured
subreddits and saves as Parquet files that the ArcticShiftScraper can consume.

Usage:
    # Download data for a specific city's subreddits
    python scripts/arctic_shift_download.py tacoma

    # Download for all configured cities
    python scripts/arctic_shift_download.py --all

    # Custom date range
    python scripts/arctic_shift_download.py tacoma --after 2023-01-01 --before 2026-03-01

    # Download only posts or only comments
    python scripts/arctic_shift_download.py tacoma --posts-only
    python scripts/arctic_shift_download.py tacoma --comments-only

Output: data/arctic_shift/<subreddit>_posts.parquet
        data/arctic_shift/<subreddit>_comments.parquet
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Arctic Shift API
BASE_URL = "https://arctic-shift.photon-reddit.com"
PAGE_SIZE = 100  # max allowed by API
REQUEST_DELAY_S = 0.5  # be polite

# Columns the ArcticShiftScraper actually reads
POST_FIELDS = [
    "id", "subreddit", "title", "selftext", "score",
    "created_utc", "author", "permalink", "upvote_ratio",
    "num_comments",
]
COMMENT_FIELDS = [
    "id", "subreddit", "body", "score", "created_utc",
    "author", "permalink", "link_id", "parent_id",
]


def _fetch_page(
    endpoint: str,
    subreddit: str,
    after_utc: Optional[int],
    before_utc: Optional[int],
    client: httpx.Client,
) -> list[dict]:
    """Fetch one page of results from Arctic Shift API."""
    params = {
        "subreddit": subreddit,
        "limit": PAGE_SIZE,
        "sort": "asc",
    }
    if after_utc is not None:
        params["after"] = after_utc
    if before_utc is not None:
        params["before"] = before_utc

    resp = client.get(f"{BASE_URL}{endpoint}", params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    if data.get("error"):
        raise RuntimeError(f"API error: {data['error']}")

    return data.get("data") or []


def _trim_row(row: dict, keep_fields: list[str]) -> dict:
    """Keep only the fields the scraper needs."""
    return {k: row.get(k) for k in keep_fields}


def download_subreddit(
    subreddit: str,
    *,
    content_type: str,  # "posts" or "comments"
    after: str = "2023-01-01",
    before: str = "2026-03-01",
    output_dir: Path,
) -> int:
    """
    Download all posts or comments for a subreddit via Arctic Shift API.

    Uses date-based pagination (sort=asc, advance after= to last item's created_utc).

    Returns the number of items downloaded.
    """
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        print("pyarrow is required: pip install pyarrow", file=sys.stderr)
        sys.exit(1)

    endpoint = f"/api/{content_type}/search"
    fields = POST_FIELDS if content_type == "posts" else COMMENT_FIELDS
    output_file = output_dir / f"{subreddit}_{content_type}.parquet"

    # Convert date strings to UTC timestamps
    after_utc = int(datetime.strptime(after, "%Y-%m-%d").timestamp())
    before_utc = int(datetime.strptime(before, "%Y-%m-%d").timestamp())

    all_rows: list[dict] = []
    page_num = 0
    current_after = after_utc

    client = httpx.Client(
        headers={"User-Agent": "overplanned-city-seeder/1.0"},
        follow_redirects=True,
    )

    try:
        while True:
            page_num += 1
            items = _fetch_page(endpoint, subreddit, current_after, before_utc, client)

            if not items:
                break

            trimmed = [_trim_row(item, fields) for item in items]
            all_rows.extend(trimmed)

            last_utc = items[-1].get("created_utc", 0)
            logger.info(
                "r/%s %s page %d: %d items (total: %d, last_utc: %s)",
                subreddit, content_type, page_num, len(items), len(all_rows),
                datetime.utcfromtimestamp(last_utc).strftime("%Y-%m-%d") if last_utc else "?",
            )

            if len(items) < PAGE_SIZE:
                break  # last page

            # Advance past the last item's timestamp
            current_after = last_utc
            time.sleep(REQUEST_DELAY_S)
    finally:
        client.close()

    if not all_rows:
        logger.warning("r/%s: 0 %s found", subreddit, content_type)
        return 0

    # Convert to Parquet
    # Build columnar dict from rows
    columns = {field: [row.get(field) for row in all_rows] for field in fields}
    table = pa.table(columns)

    output_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, str(output_file))

    logger.info(
        "r/%s: wrote %d %s to %s (%.1f MB)",
        subreddit, len(all_rows), content_type, output_file,
        output_file.stat().st_size / (1024 * 1024),
    )
    return len(all_rows)


def get_subreddits_for_city(city_slug: str) -> list[str]:
    """Get subreddits configured for a city, plus general travel subs."""
    from services.api.pipeline.city_configs import get_city_config
    config = get_city_config(city_slug)
    city_subs = list(config.subreddits.keys())

    # Add general travel subs that aren't already included
    general = ["solotravel", "travel", "foodtravel"]
    for sub in general:
        if sub not in city_subs:
            city_subs.append(sub)

    return city_subs


def get_all_configured_subreddits() -> list[str]:
    """Get deduplicated list of all subreddits across all cities."""
    from services.api.pipeline.city_configs import CITY_CONFIGS
    seen: set[str] = set()
    result: list[str] = []
    for config in CITY_CONFIGS.values():
        for sub in config.subreddits:
            if sub not in seen:
                seen.add(sub)
                result.append(sub)
    # Add general travel subs
    for sub in ["solotravel", "travel", "foodtravel"]:
        if sub not in seen:
            seen.add(sub)
            result.append(sub)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Download Reddit data from Arctic Shift for city seeding"
    )
    parser.add_argument(
        "city",
        nargs="?",
        help="City slug (e.g. tacoma, bend). Use --all for all cities.",
    )
    parser.add_argument("--all", action="store_true", help="Download for all configured cities")
    parser.add_argument("--after", default="2023-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--before", default="2026-03-01", help="End date (YYYY-MM-DD)")
    parser.add_argument("--output-dir", default="data/arctic_shift", help="Output directory")
    parser.add_argument("--posts-only", action="store_true")
    parser.add_argument("--comments-only", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not args.city and not args.all:
        parser.error("Specify a city slug or --all")

    # Resolve subreddits
    if args.all:
        subreddits = get_all_configured_subreddits()
        logger.info("Downloading for all configured cities: %d subreddits", len(subreddits))
    else:
        subreddits = get_subreddits_for_city(args.city)
        logger.info("Downloading for %s: %s", args.city, subreddits)

    output_dir = Path(args.output_dir)
    content_types = []
    if not args.comments_only:
        content_types.append("posts")
    if not args.posts_only:
        content_types.append("comments")

    total_items = 0
    total_subs = 0

    for sub in subreddits:
        for ct in content_types:
            try:
                count = download_subreddit(
                    sub,
                    content_type=ct,
                    after=args.after,
                    before=args.before,
                    output_dir=output_dir,
                )
                total_items += count
                if count > 0:
                    total_subs += 1
            except Exception:
                logger.exception("Failed to download r/%s %s", sub, ct)

    logger.info(
        "Download complete: %d items across %d subreddit files in %s",
        total_items, total_subs, output_dir,
    )


if __name__ == "__main__":
    main()
