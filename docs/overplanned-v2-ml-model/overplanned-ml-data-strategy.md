# Overplanned — ML Data Strategy & Persona Architecture
*February 2026 · Internal*
*Extends: bootstrap-deepdive.md, product-ml-features.md, backfill-enrichment.md*

---

## Overview

This document consolidates the full data philosophy for Overplanned's recommendation engine, covering:

1. Local source hierarchy and signal architecture
2. Persona dimension design and behavioral modeling
3. ChatGPT export import and markdown parsing — a new cold-start accelerator
4. Signal confidence tiers and training data integrity

The core thesis: **recommendation quality comes from knowing who the user is, not just what they clicked.** Persona drives weighting. Weighting drives ranking. Ranking drives acceptance. Acceptance refines persona. The loop only works if the persona dimensions are real.

---

## Part I — Local Source Hierarchy

### Why "Local" Is the Core Advantage

Tourist aggregators (TripAdvisor, Google Maps top 10) optimize for average satisfaction across a heterogeneous user base. They are structurally incapable of serving a user who wants what locals actually eat, because their ranking signal is dominated by tourist volume. Overplanned's edge is deliberately sourcing from communities that filter out that tourist bias.

### Tier 1 Sources — High Local Signal, Low Tourist Noise

These sources are prioritized because their authors self-select as non-tourists:

**Reddit (city/neighborhood subreddits)**
- `r/AskNYC`, `r/AskLosAngeles`, `r/chicago`, etc.
- High-value query types: "what do locals actually do", "hidden spots", "where not to go as a tourist", "neighborhood restaurant recs"
- Signal extraction: venue mentions + upvote consensus + sentiment toward tourist aggregators (negative sentiment toward "tourist traps" is an authority indicator for the source)
- Scraping strategy: RSS and pushshift-style archival. Reddit API restrictions noted — alternative access documented in `overplanned-reddit-access-addendum.md`.

**Eater (city verticals)**
- Eater SF, Eater NY, Eater Chicago, etc.
- High credibility for restaurant recommendations. Editorial, not UGC — signal confidence is higher per record but volume is lower.
- Extract: venue mentions, category, vibe descriptors, neighborhood, recency of mention.

**Atlas Obscura**
- Exceptional for non-food, non-mainstream experiences. Self-selects for curiosity-driven travelers.
- Bias: skews toward unusual and hidden. Use as a "weird/offbeat" signal layer, not as a general recommendation corpus.
- Extract: location, experience type, vibe tags, contributor density as a confidence signal.

**Infatuation**
- Editorial restaurant guide. Strong neighborhood specificity. Stronger on vibe categorization than Eater (they use explicit tags like "good for dates", "neighborhood locals").

**Nextdoor (future / research)**
- True hyperlocal signal but access is gated. Not viable for V1. Flag for V2 research.

### Tier 2 Sources — Forum & Community Signal

**City-specific forums and Facebook groups**
- e.g., SF Eats (Facebook), NYC Food subreddits, local neighborhood groups
- Lower structure than Reddit but higher locality specificity
- Extraction is noisier; require higher convergence threshold before entity resolution

**Substack city newsletters**
- "The Infatuation Local", "Eater newsletter", independent food writers
- High trust per author but author authority must be verified (# subscribers, longevity, cross-reference with Tier 1)

**Yelp (selectively)**
- Not a primary source due to tourist volume bias. Use only for cross-reference divergence calculation: when Yelp consensus diverges from local sources, that divergence is itself a signal (potential tourist trap detection).

### Tier 3 — Tourist Aggregators (Divergence Signal Only)

TripAdvisor and Google Maps top results are ingested but treated as comparison anchors rather than quality signals:

```python
tourist_local_divergence = local_source_score - tourist_aggregator_score
# Positive: locals like it more than tourists expect → underrated gem
# Negative: tourists rate higher than locals → potential tourist trap
# Threshold: abs(divergence) > 0.3 → flag for human review
```

This divergence score is a first-class feature in the ranking model. It is stored separately and never collapsed into a unified quality score.

### Cross-Reference Convergence — The Core Quality Signal

A venue mentioned independently by Reddit, Eater, and an Infatuation review has a higher `cross_ref_confidence` than one mentioned only once. Source independence matters: two Reddit posts from the same author are one independent source, not two.

```python
CrossReferenceSignal {
  activity_id: UUID
  reddit_mention_count: int
  eater_mention: bool
  atlas_obscura_mention: bool
  infatuation_mention: bool
  blog_mention_count: int
  independent_source_count: int     # key metric
  convergence_score: float          # weighted by source independence
  last_signal_date: date            # recency decay applied here
}
```

Venues that appear only in TripAdvisor top 10 and nowhere in local sources are not seeded. Venues that appear in 3+ independent local sources but not in TripAdvisor are prioritized.

---

## Part II — Persona Dimension Architecture

### Design Principles

Persona dimensions must be:
- **Behavioral, not demographic.** No age, gender, income as primary signals. Only derived from what a user does.
- **Continuous, not categorical.** Each dimension is a float on a normalized scale. No "foodie: yes/no" binary.
- **Context-tagged.** A signal from a solo trip and a family trip contribute to different sub-personas. Context prevents cross-contamination.
- **Decayable.** Old signals decay. Recent behavior outweighs historical behavior except for high-confidence structural preferences.

### Core Persona Dimensions (64-dimensional embedding)

These are the primary dimensions surfaced in the model. LLM narration and admin tooling reference these by name.

| Dimension | Description | High Value Signals |
|---|---|---|
| `pace_preference` | slow & wandering ↔ packed & efficient | day completeness, itinerary slot density acceptance |
| `food_adventurousness` | safe & familiar ↔ experimental & local | cuisine type acceptance, "try something new" engagement |
| `local_vs_tourist_bias` | tourist attraction OK ↔ locals-only preference | overrated flag engagement, source preference patterns |
| `cost_sensitivity` | budget-first ↔ cost-indifferent | price tier of accepted recommendations |
| `social_energy` | solo/quiet ↔ crowded/social | venue capacity preferences, time-of-day patterns |
| `nature_vs_urban` | nature & outdoors ↔ urban density | venue category acceptance |
| `culture_depth` | surface sightseeing ↔ deep cultural immersion | museum/historical site dwell patterns |
| `spontaneity` | rigid planner ↔ improvisational | pivot rate, mid-trip modification frequency |
| `morning_vs_night` | early bird ↔ night person | time slot acceptance patterns |
| `group_flexibility` | strong preferences ↔ highly accommodating | group compromise behavior |

Additional dimensions exist for specific verticals (food, nightlife, outdoor) and are weighted by relevance to the current trip shape.

### Cold Start Initialization

Without behavioral data, persona dimensions seed from:

1. **Preset template selection** (onboarding) — each preset maps to a soft prior over dimensions
2. **Vibe tag selections** — 6–8 tags during trip shape → dimension weights
3. **Trip shape signals** — solo vs. group, dates, destination type → structural priors
4. **Backfill import** (see Part III) — historical trips as behavioral signal

Seed confidence is low (0.2–0.4) and converges quickly as in-session behavior is observed. Mid-trip signals are weighted 3× because they represent revealed preference under real conditions.

### Signal Weighting by Source

| Signal Type | Weight Multiplier | Rationale |
|---|---|---|
| Mid-trip pivot accept/dismiss | 3.0× | Highest revealed preference signal |
| In-session card accept | 1.5× | Strong intent |
| In-session card skip | 1.0× | Negative signal |
| Backfill — Tier 1 (structured) | 0.8× | Historical, no counterfactual |
| Backfill — Tier 2 (annotated) | 0.6× | Self-reported, lower trust |
| Backfill — Tier 3–4 | 0.3× | Noisy, extracted |
| ChatGPT/MD import | 0.5×–0.7× | See Part III for tiering |
| Preset tag selection | 0.2× | Stated preference only |

---

## Part III — ChatGPT Export Import & Markdown Parsing

### Strategic Rationale

Many prospective Overplanned users have extensive travel planning history stored in ChatGPT conversations — itineraries they've built, places they've asked about, trips they've planned collaboratively. This history is a rich, underutilized persona signal that sits entirely outside existing import flows (TripIt, Google export, booking confirmation).

The ChatGPT export import creates a new cold-start accelerator: a user who has never booked through a structured tool but has two years of "help me plan a trip to Kyoto" conversations can seed a meaningful persona before planning their first trip in Overplanned.

This also covers any structured markdown itinerary — from Notion, Obsidian, travel blogs, or custom planning documents — as the parsing pipeline is format-agnostic at the extraction layer.

### What ChatGPT Exports Contain

ChatGPT allows full conversation export as a ZIP containing `conversations.json`. Each conversation contains the full message history including user prompts and assistant responses.

High-value signals extractable from this data:

- **Destination mentions** — places the user asked about, even if they never went
- **Venue-level requests** — "find me a restaurant in Oaxaca with mezcal and local vibe" reveals preference attributes directly
- **Trip shape signals** — solo trip framing, partner mentions, budget signals in prompts
- **Preference language** — explicit "I hate tourist traps", "I prefer local spots", "nothing too fancy"
- **Rejection signals** — "not that, something more _____" is a strong negative sample
- **Trip completion** — follow-up questions ("we ended up going, it was great") promote a planned trip to a completed one

### Import UX Flow

```
[Settings → Import Past Trips]
    → "Import from ChatGPT" card (alongside TripIt, Google, Manual)

[ChatGPT Import Screen]
    → "Download your data from ChatGPT" — link to chat.openai.com/settings/data-controls
    → "Upload your conversations.json or the full ZIP"
    → File picker → upload

[Processing Screen]
    → "Reading your travel conversations..." (async job, ~30s for large exports)
    → Progress: "Found X travel conversations"

[Review Screen — Conversation Triage]
    → List of conversations Overplanned identified as travel-related
    → Each shows: detected destination, approximate date, confidence level
    → User can: include, exclude, or mark as "planning only (never went)"
    → "Planning only" conversations still contribute preference signal, not trip history

[Persona Preview]
    → "Based on your conversations, here's what we learned about how you travel"
    → Dimension bars shown at low opacity to indicate these are early inferences
    → "This will refine as you use Overplanned"

[Confirmation]
    → Records saved as backfill Tier 3 (free text, LLM-extracted)
    → Planning-only conversations flagged — excluded from trip history, included in preference modeling
```

### Markdown / Plain Text Import

Same pipeline handles:
- Notion exports (markdown)
- Obsidian travel vaults
- Any `.md` or `.txt` file containing itinerary or travel planning content
- Blog post URLs (future: fetch + extract)

Entry point: "Import from file" in the same flow. File picker accepts `.zip`, `.json`, `.md`, `.txt`.

### Extraction Pipeline — ChatGPT & Markdown

**Stage 1 — Conversation Classification**

Each conversation (or markdown document) is classified before extraction:

```python
ConversationClass {
  TRAVEL_PLANNING       # asking about destinations, venues, logistics
  TRIP_RETROSPECTIVE    # talking about a trip that happened
  DESTINATION_RESEARCH  # researching places without confirmed trip
  NON_TRAVEL            # skip entirely
}
```

Classification is LLM-based but gated by keyword pre-filter to avoid sending irrelevant conversations to the LLM layer. Only conversations containing travel-relevant terms proceed to LLM classification.

**Stage 2 — Destination & Venue Extraction**

For each classified conversation, extract:

```python
ExtractionResult {
  destinations: [
    {
      name: str,                    # "Kyoto", "Oaxaca", "Tokyo's Shimokitazawa"
      confidence: float,            # 0–1
      trip_status: "planned" | "completed" | "unknown",
      date_signal: str | None,      # "last October", "2023", None
    }
  ],
  venues: [
    {
      name: str,
      category: str | None,         # restaurant, bar, museum, hotel...
      sentiment: "positive" | "negative" | "neutral",
      context: str,                 # brief snippet from source conversation
      explicitly_recommended: bool,
      explicitly_rejected: bool,
    }
  ],
  preference_signals: [
    {
      dimension: str,               # maps to persona dimension
      direction: "high" | "low",
      confidence: float,
      source_text: str,             # the phrase that generated this signal
    }
  ]
}
```

Extraction prompt is conservative: output null rather than guess. Hallucinated venues are strictly worse than gaps.

**Stage 3 — Preference Signal Extraction (ChatGPT-Specific)**

The richest value in ChatGPT exports is the user's own language. Prompts like "find me somewhere that doesn't feel touristy" or "I want to eat where locals eat, not the Michelin guide" are explicit persona signals that would otherwise require months of behavioral inference.

These signals are mapped to persona dimensions with moderate confidence:

```python
preference_signal_mappings = {
  "doesn't feel touristy": ("local_vs_tourist_bias", "high", 0.65),
  "locals eat": ("local_vs_tourist_bias", "high", 0.70),
  "hidden gem": ("local_vs_tourist_bias", "high", 0.60),
  "not too expensive": ("cost_sensitivity", "high", 0.55),
  "splurge": ("cost_sensitivity", "low", 0.60),
  "slow travel": ("pace_preference", "low", 0.65),
  "packed itinerary": ("pace_preference", "high", 0.65),
  "adventurous food": ("food_adventurousness", "high", 0.60),
  "nothing too weird": ("food_adventurousness", "low", 0.55),
}
```

Confidence caps at 0.70 for stated preference — never as high as behavioral signals from actual trip data.

**Stage 4 — Tier Assignment**

| Source Type | Confidence Tier | Training Eligibility |
|---|---|---|
| ChatGPT trip retrospective with venue names | Tier 3 | Persona seed only (no ranking model) |
| ChatGPT planning-only | Tier 4 | Preference signal only |
| Markdown with structured dates + venues | Tier 3 | Persona seed only |
| Markdown itinerary (no dates) | Tier 4 | Preference signal only |

Backfilled records from ChatGPT import never enter ranking model training — there is no counterfactual. The tier travels with every derived signal.

**Stage 5 — Entity Resolution**

Extracted venue names are matched against the ActivityNode vector database using fuzzy matching. Confidence threshold: 0.80. Unresolved records stored in travel diary but excluded from persona scoring.

ChatGPT-sourced venues have an additional complication: ChatGPT may have hallucinated venue recommendations in its original responses. The entity resolution step naturally filters these out — a hallucinated venue will fail to match any known entity. This is the correct behavior.

### Data Schema

```sql
-- New table for ChatGPT/MD import jobs
CREATE TABLE import_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    source_type     VARCHAR(30) NOT NULL,
    -- 'chatgpt_export' | 'markdown_file' | 'tripit_xml' | 'google_export'
    status          VARCHAR(20) NOT NULL DEFAULT 'processing',
    -- 'processing' | 'review_required' | 'completed' | 'failed'
    raw_filename    TEXT,
    conversation_count INT,          -- for chatgpt exports
    extracted_destination_count INT,
    extracted_venue_count INT,
    resolved_venue_count INT,
    preference_signal_count INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

-- Extended backfill_trips to track import source
ALTER TABLE backfill_trips
    ADD COLUMN import_job_id UUID REFERENCES import_jobs(id),
    ADD COLUMN conversation_id TEXT,   -- source conversation identifier
    ADD COLUMN trip_status VARCHAR(20) DEFAULT 'unknown';
    -- 'completed' | 'planned_only' | 'unknown'

-- Preference signals from import (separate from behavioral_signals)
CREATE TABLE import_preference_signals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    import_job_id   UUID REFERENCES import_jobs(id),
    dimension       VARCHAR(50) NOT NULL,
    direction       VARCHAR(10) NOT NULL,  -- 'high' | 'low'
    confidence      FLOAT NOT NULL,
    source_text     TEXT,                  -- original phrase
    applied         BOOLEAN DEFAULT false, -- has this updated persona?
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Privacy & Consent

ChatGPT conversations may contain sensitive personal information beyond travel planning (health, relationships, work). Overplanned must handle this carefully:

- The user initiates the upload. No automated scraping or OAuth access to ChatGPT.
- Extraction prompt is explicitly scoped: "extract only travel-related content. Ignore all other content."
- Raw conversation text is processed in-memory and never persisted to storage. Only structured extraction results are stored.
- User can delete the import job at any time, cascading to all derived signals.
- Clear disclosure at upload screen: "We only read travel-related parts of your conversations. Raw conversations are never stored."

---

## Part IV — Signal Integrity & Training Guardrails

### The Counterfactual Problem

Backfilled and imported trips have no counterfactual. We know what the user did, not what else was available and skipped. This means they cannot train the ranking model — we can't compute a loss without negatives.

These records are persona signal only. The persona update pipeline uses them to initialize dimension weights. The ranking model training pipeline explicitly excludes any record with a non-null `import_job_id` or `backfill_confidence < 0.8`.

This is enforced at the extraction job level, not at training time. The exclusion flag is set at ingestion and is immutable.

### English-Weight Bias

Local source ingestion skews toward English-language communities even when operating in domestic US markets (NYC has significant Spanish, Mandarin, Korean communities with local recommendation cultures not reflected in English Reddit). 

Mitigation:
- Source quality signals are stored per-source, never collapsed
- `tourist_local_divergence` is calculated separately for each source type
- Persona weighting by source type is a learned parameter, not a hard-coded constant
- Plan for V2: Spanish-language Reddit and Yelp source integration for major US metro markets

### Recency Decay

Signals decay at different rates depending on dimension:

| Dimension Type | Decay Rate | Rationale |
|---|---|---|
| Structural preferences (pace, food adventurousness) | Slow (180d half-life) | Core personality traits, stable |
| Budget sensitivity | Medium (90d half-life) | Life circumstances change |
| Mid-trip behavioral signals | Fast (30d for initial weight; permanent archive) | Most accurate but context-specific |
| Backfill / import signals | No decay (static confidence floor) | Historical — already represents the past |

### Persona Version Control

Each persona update creates a new versioned snapshot. The previous snapshot is retained for:
- Debugging: "why did the recommendations change?"
- Regression detection: model changes can be compared against historical snapshots
- User transparency: "your travel profile has evolved — here's how" (future surface)

---

## Part V — Recommendation Quality Metrics

### What We're Optimizing

The north star metric is **trip completion rate** — did the user actually do the things we recommended? This is measured via GPS check-in, mid-trip confirmation, or post-trip retrospective.

Secondary metrics:
- **Pivot rate** — lower is better, but not zero (some pivots are discovery)
- **"Would return" annotations** — explicit signal but only available post-trip
- **Persona alignment score** — did the accepted activities match the user's persona dimensions?
- **Source diversity** — are we over-indexing on one source? (monitor for single-source dependency)
- **Tourist trap rate** — what percentage of accepted recommendations are flagged `overrated: true`?

### Feedback Loop Architecture

```
User behavior
    → behavioral_signals table
    → nightly extraction job → Parquet training data
    → persona updater → persona_dimensions snapshot
    → ranking model → activity scores
    → itinerary generation → user behavior
```

The loop closes in 24 hours at minimum (nightly update). Mid-trip signals are applied within the session via a lightweight session-scoped persona overlay — a fast path that doesn't wait for the nightly job.

---

## Appendix — ChatGPT Import: Prompt Templates

### Conversation Classification Prompt

```
You are classifying ChatGPT conversations to identify travel-related content.

For the following conversation, classify it as one of:
- TRAVEL_PLANNING: User is planning a future trip (asking about destinations, venues, logistics)
- TRIP_RETROSPECTIVE: User is talking about a trip that already happened
- DESTINATION_RESEARCH: User is researching places without a confirmed trip
- NON_TRAVEL: Not travel-related

Output JSON only: {"class": "<CLASS>", "confidence": 0.0-1.0, "destination_hint": "<city/region or null>"}

Conversation:
{conversation_text}
```

### Venue & Preference Extraction Prompt

```
You are extracting travel-relevant information from a ChatGPT conversation.

Extract only:
1. Destinations mentioned (cities, regions, neighborhoods)
2. Venues mentioned by name (restaurants, bars, museums, hotels, experiences)
3. Explicit user preferences expressed in their messages (NOT the assistant's messages)

Rules:
- Output null for any field you are not confident about. Do not guess.
- A venue mentioned only by the assistant (not confirmed by user) has lower confidence.
- Extract sentiment only from explicit user language.
- If a venue name is vague (e.g. "that ramen place"), omit it.

Output JSON only following this schema:
{
  "destinations": [...],
  "venues": [...],
  "preference_signals": [...]
}

Conversation:
{conversation_text}
```

---

*Last updated: February 2026*
*Next: Local source scraping implementation, ChatGPT import UI prototype*
