#!/usr/bin/env python3
"""
Preflight check — run before any city seeding batch.

Usage:
    python3 scripts/preflight_check.py                  # global infra checks only
    python3 scripts/preflight_check.py --city bend      # + city-specific Parquet check

Exits 0 if all checks pass. Exits 1 if any check fails.
"""

import argparse
import os
import sys
from pathlib import Path

# ANSI colors
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"
BOLD = "\033[1m"

PASS = f"{GREEN}PASS{RESET}"
FAIL = f"{RED}FAIL{RESET}"
WARN = f"{YELLOW}WARN{RESET}"

failures = []


def check(label: str, fn):
    """Run a check function, print result, accumulate failures."""
    try:
        result = fn()
        if result is True or result is None:
            print(f"  {PASS}  {label}")
        elif isinstance(result, str) and result.startswith("WARN"):
            print(f"  {WARN}  {label}: {result[5:].strip()}")
        else:
            print(f"  {FAIL}  {label}: {result}")
            failures.append(label)
    except Exception as e:
        print(f"  {FAIL}  {label}: {e}")
        failures.append(label)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_anthropic_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        # Try reading from .env
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    if not key:
        return "ANTHROPIC_API_KEY is not set (checked env + .env)"
    if not key.startswith("sk-ant-"):
        return f"ANTHROPIC_API_KEY looks wrong (prefix: {key[:8]}...)"
    return True


def check_database_url():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("DATABASE_URL="):
                    url = line.split("=", 1)[1].strip()
                    break
    if not url:
        return "DATABASE_URL is not set"
    return True


def check_postgres_connectivity():
    import subprocess
    result = subprocess.run(
        ["docker", "exec", "overplanned-postgres",
         "psql", "-U", "overplanned", "-d", "overplanned",
         "-c", "SELECT 1 as ok FROM activity_nodes LIMIT 0;"],
        capture_output=True, text=True,
        env={**os.environ, "DOCKER_API_VERSION": "1.42",
             "DOCKER_HOST": "unix:///var/run/docker.sock"},
    )
    if result.returncode != 0:
        return f"Cannot connect to postgres: {result.stderr[:200]}"
    return True


def check_pg_trgm():
    import subprocess
    result = subprocess.run(
        ["docker", "exec", "overplanned-postgres",
         "psql", "-U", "overplanned", "-d", "overplanned",
         "-t", "-c", "SELECT similarity('bend','bend');"],
        capture_output=True, text=True,
        env={**os.environ, "DOCKER_API_VERSION": "1.42",
             "DOCKER_HOST": "unix:///var/run/docker.sock"},
    )
    if result.returncode != 0 or "0.5" not in result.stdout and "1" not in result.stdout:
        return f"pg_trgm not working: {result.stderr[:200]}"
    return True


REQUIRED_VIBE_SLUGS = [
    "low-key", "lively", "high-energy", "late-night", "physical",
    "instagram-worthy", "historical", "unique", "educational",
    "slow-paced", "quiet", "relaxing",
]


def check_vibe_tags():
    import subprocess
    slugs_csv = ",".join(f"'{s}'" for s in REQUIRED_VIBE_SLUGS)
    sql = f"""
SELECT
    (SELECT COUNT(*) FROM vibe_tags WHERE "isActive"=true) as total,
    (SELECT COUNT(*) FROM (
        SELECT unnest(ARRAY[{slugs_csv}]) AS slug
    ) req LEFT JOIN vibe_tags vt USING (slug) WHERE vt.slug IS NULL
    ) as missing;
"""
    result = subprocess.run(
        ["docker", "exec", "overplanned-postgres",
         "psql", "-U", "overplanned", "-d", "overplanned",
         "-t", "-c", sql],
        capture_output=True, text=True,
        env={**os.environ, "DOCKER_API_VERSION": "1.42",
             "DOCKER_HOST": "unix:///var/run/docker.sock"},
    )
    if result.returncode != 0:
        return f"Could not query vibe_tags: {result.stderr[:200]}"
    parts = result.stdout.strip().split("|")
    if len(parts) < 2:
        return f"Unexpected output: {result.stdout[:100]}"
    total = int(parts[0].strip())
    missing = int(parts[1].strip())
    if total < 40:
        return f"Only {total} active vibe_tags (need ≥ 40)"
    if missing > 0:
        return f"{missing} required rule_inference slugs missing from vibe_tags"
    return True


def check_model_registry():
    import subprocess
    result = subprocess.run(
        ["docker", "exec", "overplanned-postgres",
         "psql", "-U", "overplanned", "-d", "overplanned",
         "-t", "-c", "SELECT COUNT(*) FROM model_registry WHERE stage IN ('production','staging');"],
        capture_output=True, text=True,
        env={**os.environ, "DOCKER_API_VERSION": "1.42",
             "DOCKER_HOST": "unix:///var/run/docker.sock"},
    )
    if result.returncode != 0:
        return f"Could not query model_registry: {result.stderr[:200]}"
    count = int(result.stdout.strip())
    if count == 0:
        return "No active models in model_registry (stage=production or staging)"
    return True


def check_qdrant():
    import urllib.request
    import urllib.error
    qdrant_url = "http://127.0.0.1:6333/healthz"
    qdrant_api_key = _read_env_var("QDRANT_API_KEY") or "localdev123"
    req = urllib.request.Request(qdrant_url, headers={"api-key": qdrant_api_key})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status != 200:
                return f"Qdrant healthz returned {resp.status}"
    except urllib.error.URLError as e:
        return f"Qdrant unreachable at {qdrant_url}: {e}"
    return True


def check_parquet_for_city(city_slug: str):
    """Check that at least one Parquet file exists for the given city."""
    parquet_dir = Path(__file__).parent.parent / "data" / "arctic_shift"
    if not parquet_dir.exists():
        return f"Arctic Shift parquet directory not found: {parquet_dir}"

    # Get subreddits for city from city_configs
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from services.api.pipeline.city_configs import get_city_config
        config = get_city_config(city_slug)
        subreddits = list(config.subreddits.keys())
    except (ImportError, KeyError):
        subreddits = [city_slug.replace("-", "")]

    # Check for <subreddit>_posts.parquet
    found = []
    for sub in subreddits:
        posts_file = parquet_dir / f"{sub}_posts.parquet"
        if posts_file.exists():
            found.append(sub)

    # Also check bare city slug
    bare = city_slug.replace("-", "")
    bare_file = parquet_dir / f"{bare}_posts.parquet"
    if bare_file.exists() and bare not in found:
        found.append(bare)

    if not found:
        return (
            f"No Parquet files found for city '{city_slug}'. "
            f"Checked subreddits: {subreddits[:5]}. "
            f"Run: python3 scripts/arctic_shift_download.py --city {city_slug}"
        )
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_env_var(key: str) -> str:
    val = os.environ.get(key, "")
    if val:
        return val
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    return ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Preflight check for city seeding")
    parser.add_argument("--city", help="City slug to check Parquet files for")
    args = parser.parse_args()

    print(f"\n{BOLD}Overplanned Preflight Check{RESET}")
    print("=" * 40)

    print(f"\n{BOLD}Environment{RESET}")
    check("ANTHROPIC_API_KEY set", check_anthropic_key)
    check("DATABASE_URL set", check_database_url)

    print(f"\n{BOLD}Postgres{RESET}")
    check("Connectivity + activity_nodes table", check_postgres_connectivity)
    check("pg_trgm extension (similarity())", check_pg_trgm)
    check("vibe_tags: ≥40 active + required slugs", check_vibe_tags)
    check("model_registry: active entry exists", check_model_registry)

    print(f"\n{BOLD}Qdrant{RESET}")
    check("Qdrant reachable (/healthz)", check_qdrant)

    if args.city:
        print(f"\n{BOLD}City: {args.city}{RESET}")
        check(f"Arctic Shift Parquet files for '{args.city}'",
              lambda: check_parquet_for_city(args.city))

    print("\n" + "=" * 40)
    if failures:
        print(f"{RED}{BOLD}FAILED{RESET} — {len(failures)} check(s) failed:")
        for f in failures:
            print(f"  - {f}")
        print()
        sys.exit(1)
    else:
        print(f"{GREEN}{BOLD}ALL CHECKS PASSED{RESET}")
        print()
        sys.exit(0)


if __name__ == "__main__":
    main()
