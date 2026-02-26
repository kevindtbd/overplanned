# Bend Canary Execution Guide

Bend, Oregon is the canary city for the V2 seeding pipeline. It validates the
full chain (scrape -> resolve -> extract -> infer -> converge -> sync) before
rolling out to larger cities. This guide covers pre-flight checks, execution,
and manual review.

## Prerequisites

- PostgreSQL running with schema migrated (`prisma migrate deploy`)
- `.env` with `DATABASE_URL` and `ANTHROPIC_API_KEY` (Haiku extraction)
- Arctic Shift Parquet data downloaded to `data/arctic_shift/`
- Python dependencies installed: `asyncpg`, `httpx`, `feedparser`, `pyarrow`

## Known Pipeline Gaps (Must Fix Before Running)

The validation audit found these issues that need resolution before the first
live canary run:

### GAP-1: Arctic Shift city detection is Japan-only

`services/api/scrapers/arctic_shift.py` has hardcoded `TARGET_CITIES` and
`TERM_TO_CITY` dicts at module level containing only Tokyo/Kyoto/Osaka terms.
The `detect_city()` function uses these module-level lookups.

Even though `ArcticShiftScraper.__init__` accepts `target_cities=["bend"]`,
the `detect_city()` function won't find "bend", "old mill district", "pilot
butte", etc. because those terms aren't in `ALL_CITY_TERMS`.

**Fix**: `detect_city()` needs to use `city_configs.get_all_neighborhood_terms()`
instead of the hardcoded Japan-only dicts. Alternatively, inject neighborhood
terms from the city config at scraper init time.

### GAP-2: Blog RSS has no Bend-specific editorial feeds

`city_seeder.py` passes `feed_filter=city` to `BlogRssScraper`, but
`FEED_REGISTRY` in `blog_rss.py` has zero feeds with "bend" in the name or
with `city="Bend"`. The `_active_feeds()` method filters on `name.lower()`,
so `feed_filter="bend"` returns an empty list.

Multi-city feeds (The Infatuation, Eater, Atlas Obscura, Bon Appetit) will
also be excluded because they don't contain "bend" in their name.

**Fix**: Either add Bend-specific RSS feeds (e.g., Bend Bulletin Food,
Visit Bend Blog, Source Weekly) to `FEED_REGISTRY`, or change the filter
logic to also match on `city` field, or pass `feed_filter=None` and rely
on downstream city-matching to filter content.

### GAP-3: Rule inference uses snake_case SQL, other steps use camelCase

`rule_inference.py` queries `activity_nodes`, `vibe_tags`,
`activity_node_vibe_tags` with snake_case column names (`is_canonical`,
`price_level`, `created_at`). Every other pipeline step uses Prisma-style
quoted camelCase (`"ActivityNode"`, `"isCanonical"`, `"createdAt"`).

This will cause SQL errors at runtime if the DB schema uses Prisma naming.

**Fix**: Update `rule_inference.py` to use `"ActivityNode"`, `"VibeTag"`,
`"ActivityNodeVibeTag"` with proper camelCase column names.

### GAP-4: Convergence scorer lacks tourist_score and local 3x weighting

The design docs reference `tourist_score` and local source 3x weighting, but
`convergence.py` implements only `convergenceScore` (source count / 3.0) and
`authorityScore` (average of source authorities). There is no tourist_score
column, no local weighting multiplier, and no overrated_flag consensus logic.

**Status**: Either these features were deferred from the convergence module,
or they live elsewhere in the pipeline. Verify against the design docs before
considering this a blocker.

### GAP-5: Vocabulary drift between vibe extraction and rule inference

`vibe_extraction.py` uses a 44-tag controlled vocabulary (ALL_TAGS, with
slugs like "hidden-gem", "destination-meal", "nature-immersive").
`rule_inference.py` uses its own `CATEGORY_TAG_RULES` with different slugs
("food-focused", "sit-down", "deep-dive", "fresh-air", "browsing", "unique",
"memorable", "restorative", "quiet"). Many of these don't exist in the 44-tag
vocabulary and will log `missing_vibe_tags` warnings at runtime.

**Fix**: Align `rule_inference.py` tag slugs with the 44-tag vocabulary from
`vibe_extraction.py`.

---

## Step 1: Pre-flight Check

Verify Arctic Shift data is available for Bend subreddits:

```bash
# Check if Parquet files exist
ls -la data/arctic_shift/*.parquet

# Verify Bend subreddit data is present
python3 -c "
from services.api.pipeline.city_configs import get_city_config
cfg = get_city_config('bend')
print(f'City: {cfg.name}')
print(f'Subreddits: {list(cfg.subreddits.keys())}')
print(f'Neighborhood terms: {len(cfg.neighborhood_terms)}')
print(f'Expected nodes: {cfg.expected_nodes_min}-{cfg.expected_nodes_max}')
print(f'Is canary: {cfg.is_canary}')
"
```

Expected output:
```
City: Bend
Subreddits: ['bend', 'bendoregon', 'centraloregon']
Neighborhood terms: 16
Expected nodes: 100-500
Is canary: True
```

## Step 2: Run the Seeder

```bash
# Full pipeline (after fixing gaps above)
python3 -m services.api.pipeline.city_seeder bend -v

# Skip scrape (re-process existing data)
python3 -m services.api.pipeline.city_seeder bend --skip-scrape -v

# Skip LLM extraction (saves API cost during dev)
python3 -m services.api.pipeline.city_seeder bend --skip-llm -v

# Force restart (ignore previous progress)
python3 -m services.api.pipeline.city_seeder bend --force-restart -v
```

Progress is tracked in `data/seed_progress/bend.json`. If the pipeline
crashes, re-running picks up from the last completed step.

## Step 3: Generate Canary Report

```bash
# Terminal output
python3 scripts/bend_canary_report.py --city bend --format terminal

# JSON export for archival
python3 scripts/bend_canary_report.py --city bend --format json > data/canary_reports/bend_report.json
```

Note: `scripts/bend_canary_report.py` and `scripts/check_arctic_shift_availability.py`
are referenced in the task spec but do not exist in the codebase yet. They need
to be created before this step.

## Step 4: Manual Review Checklist

After the pipeline completes and the report is generated:

- [ ] Are there any tourist traps surfacing in top results? (TripAdvisor-style venues)
- [ ] Is the overrated_flag consensus correct? (>40% threshold, if implemented)
- [ ] Are local recommendations weighted higher than tourist content?
- [ ] Is vibe_confidence reasonable? (harmonic mean > 0.3 for well-sourced venues)
- [ ] Are there enough unique ActivityNodes? (target: 100-500 for Bend per city config)
- [ ] Is the tourist_score distribution sensible? (most venues 0.3-0.7, few extremes)
- [ ] Are the top 10 venues ones a local would actually recommend?
- [ ] Cost: should be approximately $0.13 for Haiku extraction (verify in extraction logs)
- [ ] Check `data/seed_progress/bend.json` for step-by-step metrics
- [ ] Verify no steps have `status: "failed"` in the progress file
- [ ] Check `data/dead_letter.jsonl` for any scraper failures

## Step 5: If Issues Found

| Symptom | Likely Cause | Investigation |
|---------|-------------|---------------|
| Tourist traps surfacing | Missing overrated_flag logic or low convergence threshold | Check GAP-4, review convergence scores on flagged venues |
| Too few nodes (<100) | Arctic Shift city detection not matching Bend terms | Check GAP-1, verify Parquet files contain r/Bend data |
| Zero blog RSS results | No Bend feeds in registry | Check GAP-2, add Bend editorial feeds |
| rule_inference SQL errors | Snake_case vs camelCase mismatch | Check GAP-3, fix table/column names |
| Many "missing vibe tag" warnings | Rule inference slugs not in vocabulary | Check GAP-5, align tag slugs |
| Bad vibes on venues | Extraction prompt not tuned for Bend context | Review extraction logs, check Haiku responses |
| High cost (>$0.50) | Too many nodes sent to Haiku | Check batch size, limit parameter |

## Step 6: After Validation

If the canary passes (all checklist items green, gaps resolved):

1. **Tacoma** -- second canary city (similar size to Bend)
2. **Nashville, Denver** -- larger cities with more data
3. **Full city list deployment** -- Austin, New Orleans, Seattle, Asheville, Portland, Mexico City
4. **Production monitoring** -- Sentry alerts on pipeline failures, cost tracking per city
