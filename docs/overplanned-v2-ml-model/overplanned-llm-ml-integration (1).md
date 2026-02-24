# LLM–ML Integration: Corpus Constraint, Tourist Correction & Behavioral Feedback Loop

Overplanned Internal · February 2026  
Extends: overplannedmlarchitecturedeepdive.pdf, overplanned-bootstrap-deepdive.md

---

## The Core Problem

LLMs trained on internet text have a systematic bias: their "local favorite" and "hidden gem" outputs are heavily influenced by which venues dominate English-language travel writing. A place like Ichiran Ramen is technically a Japanese chain beloved by locals — but it's also the most-written-about ramen shop in the English internet. The LLM surfaces it constantly. Our `tourist_local_divergence` score on the ActivityNode already knows it skews tourist. Without a correction mechanism, the LLM confidently surfaces tourist traps while calling them local gems.

There are two distinct failure modes to address:

1. **Venue identity bias** — the LLM names specific places from its training weights rather than our curated corpus
2. **Missing behavioral feedback** — LLM-served recommendations don't write back to ActivityNodes, so our ML models train on scraped quality signals but not on real user acceptance data

Both are solvable. They require different mechanisms.

---

## Part 1 — The Right Frame: Constrain Inputs, Don't Patch Outputs

The instinct to "merge LLM output with ML data" leads toward post-hoc patching — checking what the LLM said, then correcting it. This is brittle. The LLM's output is already served; you're in damage control mode.

The cleaner architectural principle: **the LLM never wins on venue identity**. It wins on ranking logic.

In the target architecture, the LLM does not name specific venues from its training knowledge. Its job is to reason about what *kind of thing* fits a slot — expressed as a ranked scoring of candidates handed to it from our ActivityNode corpus. The two-tower retrieval layer pulls 200 candidates from Qdrant ANN. The LLM receives those 200 candidates with their feature vectors and ranks them. It never invents a venue the retrieval layer didn't surface.

This means the tourist correction happens upstream, not downstream:
- Ichiran may appear in the candidate set
- Its `tourist_score` and `tourist_local_divergence` are features the DLRM scoring head sees explicitly
- For a user with high `local_vs_tourist_bias`, those features appropriately discount it
- The LLM never had the chance to hallucinate it into pole position

In Phase 3 (Month 9+), this is handled structurally by U-SASRec + DLRM. No correction function needed.

---

## Part 2 — Phase 1 Tourist Correction (Band-Aid, Not Architecture)

During Phase 1, when the LLM is serving directly without a trained ML ranker, the corpus constraint above isn't fully enforced — the LLM may still weight its own priors heavily. A lightweight deterministic correction prevents the worst failures.

This is explicitly a Phase 1 mechanism. It should be removed or disabled when U-SASRec + DLRM goes live.

```python
def apply_tourist_correction(
    llm_ranked_ids: list[str],
    user_persona: dict,
    activity_nodes: dict[str, ActivityNode],
    tourist_threshold: float = 0.65
) -> list[str]:
    """
    Phase 1 only.
    
    Demotes LLM top picks that have high tourist_score for users
    who've signaled local preference via persona dimensions.
    
    Does NOT remove touristy venues from results — demotes them.
    Users who want touristy things (local_vs_tourist_bias < 0.55) 
    are untouched.
    
    Remove this function when U-SASRec + DLRM goes live in Phase 3.
    """
    local_bias = user_persona.get('local_vs_tourist_bias', 0.5)
    
    # Only apply correction for users who've signaled local preference
    if local_bias < 0.55:
        return llm_ranked_ids
    
    corrected = []
    demoted = []
    
    for activity_id in llm_ranked_ids:
        node = activity_nodes[activity_id]
        if node.tourist_score > tourist_threshold:
            demoted.append(activity_id)
        else:
            corrected.append(activity_id)
    
    # Touristy venues sink to the bottom, not disappear
    # User still sees them if they scroll; they just don't lead
    return corrected + demoted
```

### Thresholds

| Parameter | Value | Rationale |
|---|---|---|
| `tourist_threshold` | 0.65 | Captures clear tourist traps. Below this, venues have enough local signal to justify their ranking. |
| `local_bias` trigger | > 0.55 | Slightly above neutral. Don't penalize users who haven't expressed a strong preference either way. |

### What This Does Not Handle

- Venues not yet in our ActivityNode corpus (LLM hallucinates them entirely) — these are filtered by the corpus constraint at the retrieval layer; if a venue isn't in Qdrant, it can't be in the candidate set
- Users with neutral or tourist-leaning personas — intentional, they may genuinely want the popular spots
- Quality signal errors in ActivityNode itself — if our scraping got `tourist_score` wrong, the correction misfires; this is a data quality problem, not a logic problem

---

## Part 3 — Behavioral Write-Back: Closing the Feedback Loop

### The Gap

The existing `RankingEvent` logging schema captures what the LLM served and what the user did with it. This is sufficient for training the ranker (BPR pairs are constructable from `accepted_id` vs `rejected_ids` within the same session).

What's not happening: those user actions don't write back to the ActivityNode itself. The node's quality signals are static — set at scraping time by Pipeline C. A venue that our Reddit corpus loved but users consistently skip is signaling something. A venue with thin scraped data but high acceptance rate is a hidden gem our pipeline missed. Neither signal reaches the ActivityNode without an explicit write-back job.

### Schema Changes

```sql
ALTER TABLE activity_nodes
  ADD COLUMN IF NOT EXISTS impression_count      INT     DEFAULT 0,
  ADD COLUMN IF NOT EXISTS acceptance_count      INT     DEFAULT 0,
  ADD COLUMN IF NOT EXISTS llm_served_count      INT     DEFAULT 0,
  ADD COLUMN IF NOT EXISTS ml_served_count       INT     DEFAULT 0,
  ADD COLUMN IF NOT EXISTS behavioral_quality_score FLOAT,
  ADD COLUMN IF NOT EXISTS behavioral_updated_at TIMESTAMPTZ;

-- behavioral_quality_score definition:
-- smoothed acceptance rate = (acceptance_count + 1) / (impression_count + 2)
-- Laplace smoothing prevents division by zero for new nodes
-- Recomputed nightly by the write-back job
```

`behavioral_quality_score` becomes a first-class feature in the DLRM scoring head alongside `tourist_score` and `quality_score` (scraped). It represents ground truth from real users — no scraping pipeline can match it.

### Nightly Write-Back Job

Runs after the existing training data extraction job. Reads `behavioral_signals` for the previous day, aggregates per `activity_id`, and upserts back to `activity_nodes`.

```python
def behavioral_writeback_job(date: date):
    """
    Nightly job. Runs after extract_training_data(). ~2-5 min at Tier 1 scale.
    
    Aggregates impression and acceptance counts from behavioral_signals
    and writes them back to activity_nodes. Also tracks which model arm
    (LLM vs ML) served the activity.
    """
    
    # Aggregate from yesterday's ranking events
    agg = query("""
        SELECT
            payload->>'activity_id'     AS activity_id,
            COUNT(*)                    AS impressions,
            SUM(CASE WHEN signal_type = 'card_viewed_then_accepted' THEN 1 ELSE 0 END) AS acceptances,
            SUM(CASE WHEN payload->>'model_used' = 'llm' THEN 1 ELSE 0 END) AS llm_impressions,
            SUM(CASE WHEN payload->>'model_used' != 'llm' THEN 1 ELSE 0 END) AS ml_impressions
        FROM behavioral_signals
        WHERE occurred_at >= %(date_start)s
          AND occurred_at < %(date_end)s
          AND signal_type IN ('card_viewed_then_accepted', 'card_skipped', 'card_dismissed')
        GROUP BY payload->>'activity_id'
    """, {'date_start': date, 'date_end': date + timedelta(days=1)})
    
    for row in agg:
        execute("""
            UPDATE activity_nodes SET
                impression_count  = impression_count + %(impressions)s,
                acceptance_count  = acceptance_count + %(acceptances)s,
                llm_served_count  = llm_served_count + %(llm_impressions)s,
                ml_served_count   = ml_served_count  + %(ml_impressions)s,
                -- Laplace-smoothed acceptance rate
                behavioral_quality_score = (acceptance_count + %(acceptances)s + 1.0)
                                         / (impression_count + %(impressions)s + 2.0),
                behavioral_updated_at = NOW()
            WHERE id = %(activity_id)s
        """, row)
```

### How behavioral_quality_score Gets Used

Once the DLRM scoring head is live (Phase 3), `behavioral_quality_score` is a feature input alongside scraped signals:

```python
# Feature vector for DLRM scoring head (simplified)
activity_features = {
    'tourist_score':             node.tourist_score,           # Pipeline C signal
    'quality_score':             node.quality_score,           # Scraped aggregate
    'behavioral_quality_score':  node.behavioral_quality_score, # Real user signal
    'impression_count_log':      log1p(node.impression_count), # Log-scaled for stability
    'cross_ref_confidence':      node.cross_ref_confidence,    # Source agreement
    'source_authority_weighted': node.source_authority_score,  # Pipeline C authority
}
```

The DLRM interaction head then computes pairwise dot products between these and user persona embedding dimensions — including the critical `local_vs_tourist_bias × tourist_score` interaction that two-tower dot product misses.

### What This Catches Over Time

| Signal Pattern | Interpretation | Action |
|---|---|---|
| High scraped quality, low behavioral acceptance | Pipeline C over-estimated. Local blog hype didn't translate to real user satisfaction. | `behavioral_quality_score` suppresses future ranking. Flag for manual review in admin tooling. |
| Low scraped data, high behavioral acceptance | Genuine hidden gem. Pipeline C missed it (thin online presence = authentic). | `behavioral_quality_score` elevates future ranking. Trigger deeper Pipeline C re-scrape. |
| High LLM-served count, low acceptance | LLM popularity bias confirmed on this venue. | Increases arbitration layer's weighting toward ML arm for this venue type. |
| High ML-served count, high acceptance | ML signal validated behaviorally. | Confidence in ActivityNode features for this venue's category. |

---

## Part 4 — Integration with Arbitration Layer

The `arbitration_events` table (from the ML deep dive) already logs which arm won per slot and whether the user accepted. With `behavioral_quality_score` now on ActivityNodes, the arbitration layer gains a new rule:

```python
def check_behavioral_signal(
    candidate: ActivityNode,
    ml_confidence: float
) -> ArbitrationSignal:
    """
    If the ML arm is proposing a venue with strong behavioral history,
    trust it over the LLM even if LLM confidence is high.
    
    Behavioral ground truth outweighs LLM priors.
    """
    if (candidate.impression_count > 50 and
        candidate.behavioral_quality_score > 0.65 and
        ml_confidence > 0.5):
        return ArbitrationSignal.TRUST_ML_BEHAVIORAL
    
    if (candidate.impression_count > 50 and
        candidate.behavioral_quality_score < 0.25):
        return ArbitrationSignal.DISTRUST_CANDIDATE
    
    return ArbitrationSignal.NO_SIGNAL  # not enough data, let other rules decide
```

The minimum impression threshold (50) prevents the signal from firing on noise. Below 50 impressions, `behavioral_quality_score` is too unstable to trust over LLM priors.

---

## Summary: What Changes and When

| Phase | Mechanism | What It Fixes |
|---|---|---|
| Phase 1 (now) | `apply_tourist_correction()` post-LLM filter | Worst-case tourist trap promotion for local-bias users |
| Phase 1 (now) | Behavioral write-back nightly job | Starts accumulating `behavioral_quality_score` on ActivityNodes |
| Phase 2 (Month 5–9) | `behavioral_quality_score` as SASRec feature | Warm users get behaviorally-validated rankings |
| Phase 3 (Month 9+) | `behavioral_quality_score` in DLRM feature interaction head | Full integration; tourist correction function removed |
| Phase 3 (Month 9+) | Arbitration rule: `TRUST_ML_BEHAVIORAL` | ML arm wins on venues with strong behavioral history |

The write-back job should start immediately — every day it doesn't run is behavioral signal lost that can't be reconstructed later.

---

*Overplanned Internal · February 2026*  
*Related: overplannedmlarchitecturedeepdive.pdf, overplanned-bootstrap-deepdive.md, overplanned-admin-tooling.md*
