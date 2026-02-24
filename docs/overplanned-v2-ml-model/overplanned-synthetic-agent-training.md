# Overplanned — Synthetic Agent Training Framework
## LLM Agent-to-Agent Simulation for Pre-Launch Model Bootstrap

*February 2026 · Internal*
*Extends: bootstrap-deepdive.md, ml-architecture-deepdive.md, product-ml-features.md*

---

## The Core Idea

We need behavioral training data before we have users. LLMs can simulate it.

The standard cold-start problem assumes you wait for real users to generate signal. But LLMs can role-play as typed persona archetypes with enough fidelity to generate statistically useful synthetic behavioral sequences — not as ground truth, but as a **prior** that real behavioral data corrects over time.

Two agents, one loop:

- **Persona Agent:** embodies a specific traveler archetype. Given a trip context, it decides which activities to accept, skip, pivot from, and linger on — behaving consistently with its persona dimensions.
- **Recommendation Agent:** generates ranked candidate lists using the current model (LLM ranker at pre-launch). Receives feedback from the Persona Agent. Updates its understanding of what this persona type prefers.

The output is synthetic `behavioral_signals` rows — same schema as real users, flagged `synthetic: true` — that pre-seed the training pipeline before launch.

This is legitimate. Netflix, Spotify, and Airbnb all use simulation to bootstrap recommendation models. The difference is we're using LLMs to generate richer, more behaviorally consistent synthetic users than random sampling would produce.

---

## Why This Works (and Where It Doesn't)

**Why it works:**

LLMs have internalized real traveler behavior from the corpus they were trained on. When you ask Sonnet to "act as a 34-year-old food-obsessed solo traveler who hates tourist traps and prefers standing bars to sit-down restaurants," it's not generating random decisions — it's drawing on millions of travel discussions, reviews, Reddit threads, and forum posts. The persona simulation is grounded in the same local source signals that Overplanned's Pipeline C is built to extract.

This is exactly the "LLMs already trained on our corpus" insight from earlier conversations — turned into an advantage. We're using the LLM's compressed world model to generate behavioral priors, then using real user data to correct where the LLM's priors are wrong.

**Where it doesn't work:**

- Synthetic data cannot train the ranking model directly. It has no counterfactual — we don't know what the persona agent *would have* accepted if shown different candidates. Use it for persona dimension initialization only, not ranking model training. Same rule as backfill.
- Synthetic data encodes the LLM's biases. If Sonnet systematically underestimates budget sensitivity for certain persona types, that bias enters the synthetic training set. Mitigation: run multiple LLM variants as persona agents (Sonnet + GPT-4o), compare outputs, flag high-divergence decisions for review.
- The simulation doesn't capture within-trip state evolution well. A real user gets tired on Day 3. The persona agent has to be explicitly prompted for fatigue accumulation or it produces implausibly consistent decisions throughout a trip.

---

## Persona Archetype Library

These 12 archetypes are the simulation population. They map directly to combinations of the persona dimension space. Each archetype is a starting point — the simulation introduces noise and variance within each type to avoid synthetic data that's too clean.

| ID | Label | Key Dimensions | Vibe Signature |
|---|---|---|---|
| `A1` | Solo Local Hunter | local_bias: 0.9, food: 0.8, pace: slow, budget: mid | Standing bars, market stalls, zero tourist overlap |
| `A2` | Couples Slow | pace: slow, social: low, food: high, cost: low-sensitive | Long dinners, quiet neighborhoods, afternoon wine |
| `A3` | Group Packed | pace: fast, social: high, adventure: high, cost: mid | Everything in two days, shared plates, loud |
| `A4` | Culture Deep | culture: 0.9, pace: slow, local: 0.6, food: moderate | Museums, historical sites, architectural walks |
| `A5` | Budget Backpacker | cost: 0.9 sensitive, food: street, pace: fast, local: 0.7 | Hostel-era behavior, street food, free attractions |
| `A6` | Business Traveler | time: tight, pace: efficient, food: mid-high, social: low | Quick lunches, reliable quality, near transit |
| `A7` | Family Practical | pace: moderate, social: mixed, food: safe, adventure: low | Kid-friendly, early dinners, low complexity |
| `A8` | Foodie First | food: 0.95, pace: moderate, local: 0.8, culture: low | Eater-level obsession, research-heavy, queue-worthy |
| `A9` | Outdoor / Active | nature: 0.85, pace: high-energy, food: functional, culture: low | Hikes, parks, physical, early start |
| `A10` | Luxury Minimal | cost: indifferent, pace: slow, social: low, culture: selective | Boutique stays, curated meals, less is more |
| `A11` | Curious First-Timer | culture: 0.6, food: 0.6, local: 0.4, pace: moderate | Landmark-willing but wants to feel local, uncertain |
| `A12` | Night Owl Social | social: 0.9, food: late, pace: night-heavy, culture: low | Bars, clubs, late dinner, sleeps until noon |

### Archetype Variance

Each archetype is not a single user — it's a distribution. When instantiating a Persona Agent, sample within the archetype with controlled noise:

```python
def instantiate_persona(archetype: str, seed: int) -> PersonaDimensions:
    base = ARCHETYPE_BASES[archetype]
    rng = np.random.default_rng(seed)

    # Add Gaussian noise to each dimension
    # Sigma = 0.1 — enough variation to produce distinguishable users
    # Clamp to [0, 1]
    return PersonaDimensions(**{
        dim: float(np.clip(base[dim] + rng.normal(0, 0.1), 0, 1))
        for dim in base
    })
```

Run 50 instantiations per archetype = 600 synthetic users. This is the pre-launch synthetic population.

---

## The Simulation Loop

### Setup

For each synthetic user:
- Assign archetype + sampled persona dimensions
- Assign a destination city (start with the launch city)
- Assign a trip shape: duration (3–7 days), group size (1–4), dates

### Loop Structure

```
For each simulated trip (user × city × shape):
  For each day (1 → N):
    For each slot (morning / afternoon / evening):

      1. RECOMMENDATION AGENT
         → Given: persona_snapshot, city, day_number, day_part,
                  previous_slots_today, trip_history
         → Generate: ranked list of 10 candidate activities (from real ActivityNode DB)
         → Return: candidate_ids + LLM's predicted top choice

      2. PERSONA AGENT
         → Given: same context + ranked candidate list + full persona
         → Decide: accept / skip / pivot / linger
         → Return: decision + optional pivot signal (mood, fatigue)

      3. LOG behavioral_signal (synthetic=true)
         → signal_type: card_accepted | card_skipped | pivot_requested
         → activity_id, persona_snapshot, context
         → source: 'synthetic_agent_v1'

      4. UPDATE persona_snapshot
         → If pivot: adjust pace_preference slightly
         → If Day 3+: inject fatigue accumulation (energy -0.1/day)
         → If food slot: reinforce food_priority in persona

      5. CONTINUE to next slot
```

### Key Prompts

**Persona Agent System Prompt:**
```
You are simulating a specific traveler making real-time trip decisions.

Your persona:
{persona_json}

Your behavioral rules:
- You make decisions consistent with your persona dimensions
- You are NOT perfectly rational — you have moods, fatigue, and context
- Day 3+ of a trip: you are 20% more likely to choose lower-energy options
- Evening slots: weight social_energy dimension more heavily
- You have seen tourist trap venues before and react negatively if local_bias > 0.6

Given this ranked list of activities:
{candidates_json}

And your current context:
{context_json}

Respond with:
{
  "decision": "accept" | "skip" | "pivot",
  "chosen_id": "<activity_id or null if pivot>",
  "pivot_reason": "<null or: tired | too_crowded | want_food | want_quiet | weather>",
  "confidence": 0.0-1.0
}

JSON only. No explanation.
```

**Recommendation Agent System Prompt:**
```
You are a travel recommendation engine. Given a user's compressed persona
and trip context, rank these candidate activities.

Persona (compressed):
{persona_compact_json}

Context:
{context_json}

Candidates:
{candidates_compact_json}

Respond with:
{"ranked": ["id1", "id2", ..., "id10"]}

JSON only. Rank from most to least suitable for this persona.
```

---

## What We Measure From the Simulation

The simulation produces three types of output data. Each serves a different purpose.

### Output 1: Synthetic Behavioral Sequences

Direct output: 600 users × ~4 days × 3 slots = ~7,200 slot decisions. These populate `behavioral_signals` with `synthetic=true` flag.

**Training use:** Persona dimension initialization only. The sequences show which activity categories, vibe tags, and quality signals consistently attract each archetype. This seeds the persona dimension priors before any real user data arrives.

**Not for ranking model training.** No counterfactual.

### Output 2: Per-Model Acceptance Rates

For each model variation we want to evaluate, run the same synthetic population through it and measure:

```python
SimulationResult {
  model_id: str                     # 'llm_baseline' | 'two_tower_v1' | 'sasrec_v1'
  archetype: str                    # which persona type
  acceptance_rate: float            # % of top-1 recommendations accepted
  hr_at_5: float                    # was accepted activity in top 5?
  pivot_rate: float                 # how often did persona agent pivot?
  tourist_trap_rate: float          # % of accepted activities with tourist_score > 0.7
  local_gem_rate: float             # % with high cross_ref_confidence + low tourist_score
  energy_curve_fit: float           # did recommendations match the day's energy arc?
  day3_fatigue_response: float      # did model respond well to Day 3 low-energy signals?
}
```

This is the **baseline statistics** for each model variation before a single real user has been seen. It won't tell you which model is best in production — that requires real behavioral data — but it tells you which models are obviously broken and which are plausible candidates.

### Output 3: Archetype × Venue Cross-Reference Matrix

The simulation generates a matrix: for each archetype, which venues were accepted most consistently? This bootstraps the persona-to-activity affinity scores that normally require months of real user data.

```
archetype_affinity[A1][venue_123] = 0.84   # local hunter consistently accepted this izakaya
archetype_affinity[A8][venue_456] = 0.91   # foodie archetype loves this ramen counter
archetype_affinity[A7][venue_789] = 0.23   # family archetype mostly skipped this bar
```

This matrix is a synthetic prior that the real behavioral data updates. It gives the recommendation system something to work with on Day 1 beyond pure LLM ranking.

---

## Model Comparison Statistics

Run the simulation for each model variant. Compare these metrics across models:

### Primary Metrics

**HR@5 (Hit Rate at 5)** — Was the activity the persona agent accepted within the top 5 recommendations? This is the standard offline RecSys metric. Higher = better.

**Tourist Trap Escape Rate** — For archetypes with high `local_vs_tourist_bias` (A1, A2, A8): what % of top-1 recommendations have `tourist_score < 0.5`? The LLM baseline will score low here due to its internet-weighted training bias. A well-calibrated ML model should score higher.

**Energy Arc Coherence** — Does the sequence of recommendations over a day form a sensible energy curve? Morning → high energy, afternoon → moderate, evening → contextual. Measure as correlation between slot energy level and recommended activity energy level. This is where SASRec should outperform Two-Tower.

**Day 3 Adaptation** — On simulated Day 3+ (fatigue accumulation active): does the model recommend lower-energy options than it did on Day 1 for the same archetype? Pure content-based models won't adapt. Sequential models (SASRec) will.

**Persona Divergence Score** — For two archetypes that differ primarily on one dimension (e.g., A1 vs A11 — both moderate pace but very different local bias): do the top-5 recommendation lists actually diverge? A model that gives very similar lists to very different archetypes is not personalizing effectively.

### Secondary Metrics

**Pivot Rate by Archetype** — How often does each archetype request a pivot? High pivot rate = model is generating poor initial fits. Acceptable pivot rates: 10-20% for group trips, <10% for warm solo users.

**Novel Venue Exposure** — What % of recommended activities have `cross_ref_confidence > 0.7` and `tourist_score < 0.4`? This measures whether the model is surfacing genuinely local content vs. defaulting to well-indexed popular venues.

**Cross-Model Agreement Rate** — When LLM and ML model agree on top choice, what's the acceptance rate? When they disagree, which was right more often? This directly informs the arbitration layer thresholds.

### Sample Expected Results Table

This is what we expect to see (to be validated against actual simulation output):

| Metric | LLM Baseline | Two-Tower | SASRec | Hybrid Arbiter |
|---|---|---|---|---|
| HR@5 (warm users) | ~0.42 | ~0.48 | ~0.55 | ~0.58 |
| Tourist Trap Escape (A1) | ~0.55 | ~0.68 | ~0.65 | ~0.72 |
| Energy Arc Coherence | ~0.51 | ~0.49 | ~0.71 | ~0.69 |
| Day 3 Adaptation | ~0.38 | ~0.40 | ~0.67 | ~0.65 |
| Persona Divergence | ~0.61 | ~0.70 | ~0.66 | ~0.74 |
| Novel Venue Exposure | ~0.48 | ~0.55 | ~0.52 | ~0.60 |

*Note: LLM baseline will likely win on HR@5 for cold users — that's expected. SASRec wins on temporal metrics. Two-Tower wins on persona divergence (static features are good at basic content matching). Hybrid wins overall by combining strengths.*

These numbers are hypotheses. Run the simulation, compare against expectations, revise the arbitration rules where the actual numbers diverge from the expected pattern.

---

## Cost Model for the Simulation

600 synthetic users × ~12 slots per trip = 7,200 Persona Agent calls + 7,200 Recommendation Agent calls = 14,400 total LLM calls.

At ~1,500 tokens per call average (context + response):
- Total tokens: ~21.6M
- At Sonnet 4.5 batch pricing ($1.50/$7.50): ~$32,400 output tokens → ~**$35 total**
- At Haiku 4.5 batch pricing ($0.50/$2.50): ~**$12 total**

Run Haiku for Persona Agent (it can simulate decisions reliably), Sonnet for Recommendation Agent (ranking quality matters more). Estimated total: **~$20 for the full simulation run.**

Re-run cost per model variant being tested: ~$20 each. Run 5 variants = $100 total pre-launch simulation budget.

---

## Integration with Real Data

### Synthetic → Real Transition

Synthetic signals are tagged `source: 'synthetic_agent_v1'`. Real behavioral signals are tagged `source: 'user_behavioral'`. The training pipeline applies different confidence weights:

| Signal Source | Persona Training Weight | Ranking Model Eligible |
|---|---|---|
| `user_behavioral` (warm user) | 1.0× | Yes |
| `user_behavioral` (cold user) | 0.5× | No |
| `backfill_tier_1` | 0.8× | No |
| `synthetic_agent_v1` | 0.3× | No |

As real data accumulates, synthetic signals are progressively deprioritized. At 500 real users with 3+ trips each, synthetic signals are excluded from persona training entirely — they've been superseded.

### The Correction Signal

The most valuable output of the simulation isn't the synthetic data itself — it's the **correction signal** that emerges when real user behavior diverges from synthetic predictions.

When archetype A1 synthetic users consistently accepted `venue_X` but real users with A1-like personas consistently skip it, that divergence tells you:
- The LLM's model of "local hunter behavior" is miscalibrated for this specific venue type
- The ActivityNode's vibe tags may be wrong (the venue presents as local but isn't)
- The persona dimension weights need updating

This correction pattern is early evidence for what the arbitration layer should overrule.

---

## Implementation Steps

These are discrete, parallelizable tasks — can be started before users are on the platform.

**Step 1 — Build the persona instantiation library** (~2 hours)
Define the 12 archetypes as JSON configs. Write the `instantiate_persona()` sampler. No LLM calls yet.

**Step 2 — Write and test the agent prompts** (~3 hours)
Prompt engineering for both Persona Agent and Recommendation Agent. Test with 5 manual runs before batch. Key: get the JSON output stable and parseable.

**Step 3 — Build the simulation loop** (~4 hours)
Python script: reads ActivityNodes from Qdrant, iterates the loop, writes to `behavioral_signals` with `synthetic=true`. Use batch API for cost efficiency.

**Step 4 — Run first simulation pass** (~1 day wall time, async)
600 users × 12 slots = 7,200 Persona Agent calls. Submit as batch job. Cost: ~$20.

**Step 5 — Build the metrics computation layer** (~3 hours)
SQL + Python queries against the simulation output. Compute the 6 primary metrics per model variant.

**Step 6 — Run model variants** (~1 week of training runs)
For each model (LLM baseline, Two-Tower trained on synthetic data, SASRec trained on synthetic sequences): compute metrics. Fill the comparison table with real numbers.

**Step 7 — Calibrate arbitration thresholds** (~2 hours)
Use cross-model agreement data to set initial `agreement_score` threshold in the arbitration layer. If LLM and Two-Tower agree > X% of the time for warm A1 users, set that archetype's threshold at X.

**Step 8 — Deprecation schedule**
At 200 real users: re-run simulation metrics using real data as ground truth. Compare synthetic vs. real acceptance rates per archetype. Where they diverge >15%: flag and investigate.
At 500 real users: exclude synthetic signals from all training. They've done their job.

---

## What This Gives You on Launch Day

Without synthetic training:
- LLM ranker only
- No baseline to compare models against
- No sense of which archetypes the system handles well or poorly
- No persona priors — every user starts truly cold

With synthetic training:
- Persona dimension priors for all 12 archetypes — users who match an archetype get better Day 1 recommendations
- Baseline model comparison table — you know which models are plausible before exposing them to real users
- Archetype × venue affinity matrix — the system has "seen" which activities resonate with which traveler types
- Calibrated arbitration thresholds — the LLM/ML arbitration layer has starting values rather than arbitrary constants
- A correction signal framework — you know what to watch for as real data arrives

The simulation doesn't replace real data. It gives the system a credible starting point so the first real users don't experience a blank-slate system, and so the first model comparisons are statistically grounded rather than guesswork.

---

*Last updated: February 2026*
*Owner: Kevin*
*Next: Build persona instantiation library, draft agent prompts, run first 50-user test batch before full simulation*
