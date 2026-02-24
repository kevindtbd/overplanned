# Overplanned — Subflow Recommendation Architecture
## HLLM Training, Hybrid Scoring, and Per-Subflow ML Systems

*February 2026 · Internal*
*Extends: bootstrap-deepdive.md, ml-explainer.md, onboarding-flow-strategy.md*

---

## 1. HLLM — What It Actually Is Here

HLLM (Hybrid LLM) isn't a specific published model we're adopting — it's an architectural pattern where LLM reasoning and ML scoring interact within the same inference pass rather than running in sequence or as alternatives. In our context, the relevant version is: **ML scores candidates, LLM re-ranks the top-K with reasoning about context the ML can't encode.**

The reason it rarely touches the arbitration layer in steady state is that by Month 9+, SASRec handles sequential context well enough that LLM re-ranking adds cost without adding much lift for warm users. But there are two specific scenarios where HLLM combination isn't just useful — it's the right answer.

---

## 2. How We Train the HLLM Layer

The HLLM pattern requires training data that captures cases where LLM judgment *should* override ML ranking. That's a subtle training problem because you need labeled examples where:
- ML ranked candidate X highly
- LLM would have ranked candidate Y higher
- The user chose Y (or would have — counterfactual)

**Training pipeline:**

### Phase 1 — Shadow Disagreement Logging (starts now, costs nothing)
Every shadow mode run already logs both LLM and ML rankings for the same candidate set. When they disagree significantly (rank position delta > 3 for the top-5), that disagreement record is a training candidate. Log:
- `llm_rank`, `ml_rank`, `final_user_choice`
- `disagreement_reason` — LLM's structured explanation for its ranking (extracted as JSON, not prose)
- `context_features` at time of disagreement: time of day, day of trip, energy trajectory, group composition

At 500 users × 3 trips × ~8 ranking events per trip = ~12,000 disagreement records before you have enough to analyze patterns.

### Phase 2 — Disagreement Pattern Analysis
Manual + automated pass over shadow disagreement records. Look for systematic patterns:
- LLM consistently outranks ML on Day 1 slots (novelty/orientation preference the ML hasn't learned)
- LLM consistently outranks ML for afternoon → evening transitions (energy shift the ML's static features miss)
- ML consistently outranks LLM for food repeat patterns ("user loved ramen on Day 2, LLM doesn't notice")

These patterns define the **HLLM trigger conditions** — the specific contexts where you route to the hybrid path instead of pure ML.

### Phase 3 — Training the Arbitration Classifier
Once trigger conditions are defined, train a lightweight binary classifier:
- Input: context features (day_part, trip_day, persona_momentum, energy_trajectory, group_flag)
- Output: `use_llm_rerank: bool` + confidence
- Training labels: from disagreement records where LLM choice = user choice (LLM was right) or ML choice = user choice (ML was right)

This classifier runs at ~0ms (tiny feature vector, linear model). When it fires `use_llm_rerank: true`, the top-10 ML candidates get passed to Haiku for re-ranking. Cost: ~$0.001 per HLLM call × estimated 15% of warm-user calls = acceptable.

### What Not to Do
Don't train the HLLM layer on synthetic data. The whole point is capturing cases where LLM reasoning about context beats ML pattern matching — and you need real context (real trip day, real energy signals, real group) to identify those cases. Synthetic simulation is useful for cold-start persona initialization, not for HLLM trigger training.

---

## 3. When HLLM Combination Is Right

The current architecture treats LLM and ML as alternatives routed by a deterministic if-else. That's correct for the common case. But there are specific scenarios where the right answer is LLM re-ranking *on top of* ML candidates:

### 3a. Day 1 Orientation Slots
ML has no trip-level sequential context yet. SASRec needs a sequence to model. Day 1, Slot 1 is the cold position even for a warm user. LLM adds value here by reasoning about: "this is their first morning, they just landed, the city is new — what's the right entry experience?" That's world-knowledge reasoning ML can't replicate.

**Trigger:** `trip_day == 1 AND slot_index <= 2`
**HLLM path:** ML scores all candidates → LLM re-ranks top-10 with `first_morning_context: true` in the prompt → serve LLM output
**Training signal:** Day 1 slot acceptance rate vs. Day 2+ acceptance rate, split by LLM-only vs. HLLM

### 3b. Energy Transition Moments
When SASRec detects an energy trajectory shift (high-energy morning → ML would recommend another high-energy afternoon slot, but the sequence pattern says the user usually drops pace mid-afternoon), LLM can reason about the transition in a way ML can't articulate.

**Trigger:** `energy_trajectory_delta > 0.3 AND upcoming_slot_energy_score > current_momentum`
**HLLM path:** ML ranks candidates → LLM filters for energy-appropriate options from top-15 → serve filtered ranking
**This is different from a swap.** The ML had the right candidates in its top-15 — the HLLM just re-orders. No new candidates pulled.

### 3c. Group Conflict Resolution Slots
When two members have diverging preferences and the system needs to fill a contested slot, ML can score for each member individually but can't reason about what a *good compromise* looks like. LLM can. "Sarah scores Museum +0.8, Marcus scores Museum -0.3 — but both score Street Food +0.6" is a reasoning problem, not just a scoring problem.

**Trigger:** `group_conflict_detected AND contested_slot`
**HLLM path:** ML generates per-member top-5 lists → LLM finds the Pareto-optimal intersection → serve intersection-ranked result
**Signal:** Group member post-trip satisfaction scores on contested vs. uncontested slots

### 3d. Rejection Recovery (First Creation)
When a user rejects a significant portion of the first itinerary during the initial reveal (swaps 2+ slots in the first 60 seconds), this is a signal that the initial generation missed. ML doesn't have enough signal to self-correct. LLM can look at what was rejected and reason about why.

**Trigger:** `first_creation AND swap_count >= 2 AND time_since_reveal < 120s`
**HLLM path:** Log all rejected slots' features → LLM analyzes rejection pattern → generates hypothesis about what was wrong → passes hypothesis as context to re-rank remaining candidates
**This is the one case where LLM reasoning about its own failure is valuable.** It can see that both rejected slots were "cultural/museum" and course-correct the remaining slots before the user has to manually fix everything.

---

## 4. Subflow Recommendation Systems — The Full Map

The main pipeline (BPR → Two-Tower → SASRec) handles the core ranking use case: warm user, planning a trip, fill slots in order. But there are 7 distinct subflows that have different enough signal structures to warrant their own models or at minimum their own feature sets. Some need full separate models. Some just need separate feature engineering feeding the same model.

---

### Subflow A — Group Dynamics Ranking

**Why it's different:** Individual ranking optimizes for one user's preferences. Group ranking has multiple objective functions that conflict. You can't just average persona scores — that produces recommendations that nobody actively dislikes but nobody is excited about either.

**The model:** Pareto Group Ranker. For each candidate, compute:
- `min_score` across all members (floor — prevents anyone hating it)
- `variance_score` across all members (lower = more consensus)
- `max_score` across all members (ceiling — at least someone loves it)

Weighted combination: `0.5 × min_score + 0.3 × (1 - variance) + 0.2 × max_score`

The 0.5 weight on min_score is intentional — avoiding the worst outcome for any member is more important than maximizing the best outcome for one. This can be tuned per group once you have enough group trip data.

**Training signal:** Per-member post-trip ratings on shared slots. If member A rates a slot 5/5 and member B rates it 1/5, that slot was not a good group recommendation regardless of the average. The training label is `min(member_ratings)`, not `mean(member_ratings)`.

**What you don't build yet:** Don't build this from scratch. Use Two-Tower with a modified loss function (margin loss on min_score instead of user score) once you have enough group trips. Rough threshold: 50 completed group trips with post-trip feedback.

---

### Subflow B — Group Split Detection and Routing

**Why it's different:** Some slots should be split — not compromised. If Marcus wants to visit a sumo training session and Sarah has zero interest, the right answer isn't to find something both like less. The right answer is to route them to different activities and sync back for dinner.

**The model:** Binary split classifier. Inputs:
- `preference_delta` on the contested slot (how far apart are their scores)
- `slot_category` (some categories split more gracefully: solo museums vs. group dinners)
- `time_of_day` (mid-morning splits work, dinner splits don't)
- `remaining_together_slots` (don't split if only 2 slots left in the day)
- `prior_split_accepted` (has this group split before and re-synced without friction)

Output: `recommend_split: bool` + two independent slot suggestions for the split period + a sync-back suggestion.

**Training signal:** When you surface a split suggestion, log whether the group accepts it. Split accepted → positive label for that feature combination. Split rejected → negative. You don't need many examples — this is a low-frequency high-stakes decision. Start with 20+ accepted splits before training; use heuristics until then.

**Heuristic until trained:**
- `preference_delta > 0.6` AND `slot_category in [museum, sports, nightclub, spa]` AND `time_of_day in [morning, afternoon]` → recommend split

---

### Subflow C — Offline / Pre-Computation Ranking

**Why it's different:** Offline alternatives need to be computed at trip generation time, not at swap time. The model is the same (Two-Tower or SASRec), but the serving context is different:
- No real-time user signals — the persona snapshot from trip generation is the only input
- Must cover the range of possible mood states, not just the current one
- Must be diverse — 3 alternatives for a slot should span energy levels, not just be the next 3 highest-scored candidates

**The offline diversification rule:**
When generating the pre-computed alternative pool, enforce:
- At least 1 alternative with `energy_score < current_slot_energy - 0.3` (lower energy option)
- At least 1 alternative with `energy_score ≈ current_slot_energy ± 0.1` (same vibe, different venue)
- At least 1 alternative with different primary `vibe_tag` than the original slot (categorical diversity)

This is a post-processing rule on ML output, not a separate model. Apply it at trip generation time.

**Training signal:** Which pre-computed alternative the user actually chose when pivoting offline. Over time this tells you which of the three alternative types (lower energy / same vibe / different category) is chosen most often in each context. Retrain the diversification weights from this.

---

### Subflow D — On-The-Fly Addition

**Why it's different:** On-the-fly add is not a swap and not a pivot. The user found something themselves and wants to insert it into an existing itinerary. The recommendation system isn't choosing the venue — the user already chose it. What the system needs to do is:

1. Suggest *where* in the day to insert it (slot positioning)
2. Suggest *what to remove or reschedule* if the day is already full
3. Update the persona immediately (manual addition = 1.5× confidence weight)

**The model:** A lightweight slot-fitting ranker. Inputs:
- The new venue's features (category, duration, location, energy score)
- The current day's slot sequence (what's confirmed, what's flexible)
- The time of day right now
- Geographic proximity (venues close together are better candidates to keep; far venues are candidates to reschedule)

Output: `insert_after_slot_id` + `optional_reschedule_slot_id` + `reason`

**This doesn't need ML at trip 1.** Use a deterministic rule: insert after the current active slot, reschedule the lowest-scored slot if full. Train a model once you have 200+ manual addition events with confirmed acceptance of the positioning suggestion.

**Key behavior:** After the user adds something manually, don't immediately offer alternatives. They found something on their own — that's the product working as intended. Log it, insert it, update persona. No drawer, no suggestions, no "you might also like." Get out of the way.

---

### Subflow E — First-Creation Rejection Recovery

**Why it's different from a normal swap:** When a user swaps 1 slot, they're correcting one recommendation. When they swap 2+ slots in the first 90 seconds after first reveal, they're telling you the initial generation was systematically wrong. The correction signal is about the whole itinerary, not one slot.

**The recovery model:** A context-correction LLM call (this is the HLLM case 3d from above). Input:
- Features of all rejected slots (category, vibe_tags, energy_score, local_score)
- Features of all retained slots
- The rejection pattern (what do the rejected slots have in common)

Output: A `correction_context` JSON object injected into the re-ranking prompt for remaining unconfirmed slots:

```json
{
  "rejection_pattern": "cultural_heavy",
  "observed": "2 of 3 rejected slots were museum/temple",
  "correction": "reduce cultural_depth weight, increase food + local_scene weight",
  "confidence": 0.72
}
```

The re-ranking isn't a full regeneration. It re-scores the existing candidate pool using the corrected weights. Faster, cheaper, and preserves the slots the user already accepted.

**Training signal:** Does the correction hold? Log acceptance rate on re-ranked slots vs. baseline. A correction that fires with 72% confidence but produces 40% acceptance is wrong — the pattern detection is off. Log `correction_confidence` and `post_correction_acceptance_rate` as a paired signal to improve the pattern detection over time.

---

### Subflow F — Itinerary Alteration (Returning to an Existing Plan)

**Why it's different:** A user who comes back and edits an existing itinerary is revealing time-shifted preferences. The plan was built, they thought about it, and now they want it different. This is higher-signal than a real-time pivot because it's not impulsive.

**Three distinct alteration types — each has different ML treatment:**

**Type 1 — Date/duration change:** User extends or shortens the trip. Pure scheduling: extend by adding slots from the pre-ranked candidate pool, shorten by removing lowest-scored slots. No ML update needed — no preference signal revealed.

**Type 2 — Slot replacement (pre-trip):** User swaps a slot before the trip starts. This is the clearest preference signal: cold, deliberate, no in-context mood pressure. Weight this at 1.3× vs. in-trip swap. Update persona dimensions immediately.

**Type 3 — Category shift:** User replaces 2+ slots in the same category (swaps two dinner slots for lunch + street food, removes both museum slots). This is a structural preference signal — the initial generation got a category wrong. 
- Update `vibe_tag_affinity` for the removed category (negative weight)
- Update for the added category (positive weight)
- Tag this as `itinerary_restructure` in the signal log — separate from regular swap signals

**What to build:** No separate model needed for alterations. What you need is a signal tagging system that distinguishes alteration type in the `behavioral_signals` table and applies the right confidence multiplier before training. One new column: `signal_context: enum('in_trip', 'pre_trip_alteration', 'post_trip_alteration', 'itinerary_restructure')`.

---

### Subflow G — Repeat City / Familiar User

**Why it's different:** A user who returns to a city they've already visited with Overplanned has a completely different discovery profile. They've been to the beginner spots. They want what they missed, not what's safe.

**The returning visitor model:**
- Exclude all previously accepted venues from the candidate pool for this city
- Boost `novelty_score` weight by +0.4 (more aggressive long-tail discovery)
- Reduce `cross_ref_confidence` threshold by 0.15 (willing to surface lower-consensus venues that locals know)
- Increase `local_score` minimum threshold (no tourist-adjacent options at all)

This isn't a new model — it's a modified feature set fed into the same Two-Tower model. But it has to be triggered correctly: detect returning visitor by checking `user_id × city` against completed trip history before generating candidates.

**Training signal:** Compare acceptance rates for returning visitors vs. first-time visitors on the same city's candidate pool. If returning visitors accept at lower rates, the exclusion filter is correct but the replacement pool quality needs work. If they accept at higher rates, the model is serving novelty well.

---

## 5. The Full Model Registry (Updated)

What we actually need to build and when, including all subflows:

| Model | Subflow | Training Signal | Build When |
|---|---|---|---|
| LLM Ranker | Core / cold-start | None — runs immediately | Day 0 |
| BPR | Core / warm | Accept/skip pairs | 200 users, 2K signals |
| Two-Tower | Core / warm | Co-occurrence + BPR features | 500 users |
| SASRec | Core / sequential | Accept sequences, energy arc | 500 users |
| HLLM Trigger Classifier | Hybrid arbitration | Shadow disagreement records | 12K disagreement events |
| Pareto Group Ranker | Group dynamics | Per-member trip ratings | 50 group trips |
| Split Detector | Group split | Split accept/reject | 20 accepted splits |
| Slot Fitter | On-the-fly add | Positioning acceptance | 200 manual add events |
| Rejection Pattern Detector | First-creation recovery | Post-correction acceptance | 100 recovery events |
| Offline Diversifier | Offline pivot | Alternative choice type | 300 offline pivots |
| Repeat City Boost | Familiar user | Returning visitor acceptance | 100 repeat city trips |

Most of these never graduate to ML at early scale. For the first 12 months, all subflows except Core run on deterministic heuristics with signal logging active. The models get trained when the thresholds are hit — not before.

---

## 6. Signal Tagging for Subflow Attribution

The current `behavioral_signals` schema needs one new field to make subflow training work:

```sql
ALTER TABLE behavioral_signals 
ADD COLUMN subflow VARCHAR(40);
-- Values:
-- 'core_ranking'
-- 'group_ranking'
-- 'group_split'
-- 'offline_pivot'
-- 'onthefly_add'
-- 'first_creation_rejection'
-- 'itinerary_alteration_pre'
-- 'itinerary_alteration_restructure'
-- 'repeat_city'
-- 'hllm_rerank'  -- when HLLM path was taken
```

And one new field for confidence context:

```sql
ADD COLUMN signal_weight FLOAT DEFAULT 1.0;
-- Multipliers by context:
-- in_trip swap: 1.0
-- pre_trip alteration (slot): 1.3
-- post_trip confirmation: 1.8
-- post_trip correction: 1.8
-- itinerary_restructure (category shift): 1.4
-- on_the_fly_add: 1.5
-- group_vote: 1.2
-- first_creation_rejection: 0.7 (ambiguous)
-- synthetic (bootstrap): 0.3
```

These two fields make the nightly training extraction job trivial — `WHERE subflow = 'group_ranking' AND signal_weight > 1.0` is a complete training dataset selector.

---

*Last updated: February 2026*
*Owner: Kevin*
*Next: UI render for subflow model map + HLLM trigger visualization*
