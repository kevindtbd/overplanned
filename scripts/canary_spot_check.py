#!/usr/bin/env python3
"""
Canary spot-check — pull N random nodes for a city and print a readable table.

Usage:
    python3 scripts/canary_spot_check.py --city bend
    python3 scripts/canary_spot_check.py --city bend --sample 10

Prints:
    name | category | city | vibes | geocoded | source

Checks:
    - City field matches expected city on all rows
    - Vibe tags assigned on >= 50% of nodes
    - Geocoded on >= 60% of nodes
    - No obviously garbage names (< 3 chars, all caps)
"""

import argparse
import os
import subprocess
import sys
import json
from pathlib import Path

# ANSI colors
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"
BOLD = "\033[1m"


def run_psql(sql: str) -> str:
    result = subprocess.run(
        ["docker", "exec", "overplanned-postgres",
         "psql", "-U", "overplanned", "-d", "overplanned",
         "-t", "--no-align", "-c", sql],
        capture_output=True, text=True,
        env={**os.environ, "DOCKER_API_VERSION": "1.42",
             "DOCKER_HOST": "unix:///var/run/docker.sock"},
    )
    if result.returncode != 0:
        print(f"psql error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def get_nodes(city: str, sample: int) -> list[dict]:
    sql = f"""
SELECT
    an.id,
    an.name,
    an.category,
    an.city,
    an.latitude,
    an.longitude,
    an.status,
    COALESCE(
        string_agg(vt.slug, ', ' ORDER BY vt.slug),
        ''
    ) as vibes
FROM activity_nodes an
LEFT JOIN activity_node_vibe_tags anvt ON anvt."activityNodeId" = an.id
LEFT JOIN vibe_tags vt ON vt.id = anvt."vibeTagId"
WHERE lower(an.city) = lower('{city}')
GROUP BY an.id, an.name, an.category, an.city, an.latitude, an.longitude, an.status
ORDER BY random()
LIMIT {sample};
"""
    raw = run_psql(sql)
    if not raw:
        return []

    nodes = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) < 8:
            continue
        nodes.append({
            "id": parts[0].strip(),
            "name": parts[1].strip(),
            "category": parts[2].strip(),
            "city": parts[3].strip(),
            "latitude": parts[4].strip(),
            "longitude": parts[5].strip(),
            "source": parts[6].strip(),
            "vibes": parts[7].strip(),
        })
    return nodes


def get_city_stats(city: str) -> dict:
    sql = f"""
SELECT
    COUNT(DISTINCT an.id) as total,
    COUNT(DISTINCT an.category) as categories,
    COUNT(DISTINCT CASE WHEN an.latitude IS NOT NULL AND an.longitude IS NOT NULL THEN an.id END) as geocoded,
    COUNT(DISTINCT anvt."activityNodeId") as has_vibes
FROM activity_nodes an
LEFT JOIN activity_node_vibe_tags anvt ON anvt."activityNodeId" = an.id
WHERE lower(an.city) = lower('{city}');
"""
    raw = run_psql(sql)
    if not raw:
        return {}
    parts = raw.strip().split("|")
    if len(parts) < 4:
        return {}
    return {
        "total": int(parts[0].strip() or 0),
        "categories": int(parts[1].strip() or 0),
        "geocoded": int(parts[2].strip() or 0),
        "has_vibes": int(parts[3].strip() or 0),
    }


def get_category_breakdown(city: str) -> list[tuple]:
    sql = f"""
SELECT category, COUNT(*) as cnt
FROM activity_nodes
WHERE lower(city) = lower('{city}') AND id != '__sentinel__'
GROUP BY category
ORDER BY cnt DESC;
"""
    raw = run_psql(sql)
    rows = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) >= 2:
            rows.append((parts[0].strip(), int(parts[1].strip() or 0)))
    return rows


def truncate(s: str, n: int) -> str:
    return s[:n - 1] + "…" if len(s) > n else s


def main():
    parser = argparse.ArgumentParser(description="Canary spot-check for a seeded city")
    parser.add_argument("--city", required=True, help="City slug (e.g. bend)")
    parser.add_argument("--sample", type=int, default=10, help="Number of nodes to sample")
    args = parser.parse_args()

    city = args.city
    sample = args.sample

    # --- Stats summary ---
    stats = get_city_stats(city)
    if not stats or stats["total"] == 0:
        print(f"{RED}No activity_nodes found for city='{city}'{RESET}")
        sys.exit(1)

    total = stats["total"]
    geocoded = stats["geocoded"]
    has_vibes = stats["has_vibes"]
    categories = stats["categories"]

    geocoded_pct = (geocoded / total * 100) if total else 0
    vibes_pct = (has_vibes / total * 100) if total else 0

    print(f"\n{BOLD}Canary Spot-Check: {city}{RESET}")
    print("=" * 70)
    print(f"  Total nodes:  {total}")
    print(f"  Categories:   {categories}")
    geocoded_color = GREEN if geocoded_pct >= 60 else YELLOW if geocoded_pct >= 30 else RED
    vibes_color = GREEN if vibes_pct >= 50 else YELLOW if vibes_pct >= 25 else RED
    print(f"  Geocoded:     {geocoded_color}{geocoded}/{total} ({geocoded_pct:.0f}%){RESET}")
    print(f"  Vibe tags:    {vibes_color}{has_vibes}/{total} ({vibes_pct:.0f}%){RESET}")

    # Category breakdown
    breakdown = get_category_breakdown(city)
    if breakdown:
        print(f"\n{BOLD}Categories:{RESET}")
        for cat, cnt in breakdown:
            bar = "█" * min(cnt, 30)
            print(f"  {cat:20s} {cnt:4d}  {bar}")

    # --- Automated pass criteria ---
    print(f"\n{BOLD}Automated Pass Criteria:{RESET}")
    issues = []

    def criterion(label, ok, detail=""):
        marker = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"  {marker}  {label}" + (f" — {detail}" if detail else ""))
        if not ok:
            issues.append(label)

    criterion("Total nodes ≥ 40", total >= 40, f"{total} nodes")
    criterion("Categories ≥ 5", categories >= 5, f"{categories} categories")
    criterion("Vibe tags on ≥ 50% of nodes", vibes_pct >= 50, f"{vibes_pct:.0f}%")
    criterion("Geocoded ≥ 60% of nodes", geocoded_pct >= 60, f"{geocoded_pct:.0f}%")

    # --- Sample nodes table ---
    nodes = get_nodes(city, sample)
    print(f"\n{BOLD}Sample Nodes (n={len(nodes)}, random):{RESET}")
    print("-" * 70)
    print(f"  {'Name':<28} {'Category':<14} {'City':<12} {'Geo':<5} {'Vibes'}")
    print("-" * 70)

    wrong_city_count = 0
    garbage_count = 0

    for node in nodes:
        name = truncate(node["name"], 28)
        cat = truncate(node["category"], 14)
        node_city = node["city"]
        geo = "yes" if node["latitude"] and node["longitude"] else "no"
        vibes = truncate(node["vibes"], 30) if node["vibes"] else f"{YELLOW}none{RESET}"

        city_ok = node_city.lower() == city.lower() or city.lower() in node_city.lower()
        city_display = node_city if city_ok else f"{RED}{node_city}{RESET}"
        if not city_ok:
            wrong_city_count += 1

        # Flag obviously garbage names
        is_garbage = len(node["name"]) < 3 or node["name"].isupper() and len(node["name"]) > 6
        name_display = f"{RED}{name}{RESET}" if is_garbage else name
        if is_garbage:
            garbage_count += 1

        geo_display = f"{GREEN}{geo}{RESET}" if geo == "yes" else f"{YELLOW}{geo}{RESET}"
        print(f"  {name_display:<28} {cat:<14} {city_display:<12} {geo_display:<5} {vibes}")

    print("-" * 70)

    # Flag cross-contamination and garbage
    criterion("All sampled nodes have correct city", wrong_city_count == 0,
              f"{wrong_city_count} wrong-city rows detected")
    criterion("No garbage names in sample", garbage_count == 0,
              f"{garbage_count} suspicious names detected")

    # Final verdict
    print("\n" + "=" * 70)
    if issues:
        print(f"{RED}{BOLD}CANARY FAILED{RESET} — {len(issues)} issue(s):")
        for i in issues:
            print(f"  - {i}")
        print()
        sys.exit(1)
    else:
        print(f"{GREEN}{BOLD}AUTOMATED CHECKS PASSED{RESET}")
        print(f"\n{BOLD}Manual review:{RESET} Look at the sample above.")
        print("  - Names should be real places in this city")
        print("  - Vibes should make sense for each venue")
        print("  - No obvious extraction artifacts")
        print()


if __name__ == "__main__":
    main()
