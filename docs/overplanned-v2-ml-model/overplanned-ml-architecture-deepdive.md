# Overplanned — ML Architecture Deep Dive
## Cross-Referenced Model Proposals vs. Current Two-Tower Approach

*February 2026 · Internal*
*Extends: architecture.html, bootstrap-deepdive.md, product-ml-features.md*

---

## Framing: Why This Matters Now

The current architecture treats the LLM→BPR→Two-Tower→LightGCN progression as a clean sequential handoff. That framing has a hidden assumption: that our ML models are eventually competing with or replacing the LLM's judgment.

The more accurate framing, based on how the field has actually moved: **LLMs and ML models are not sequential stages — they are complementary functions that should run in parallel, with explicit cross-referencing logic between them.** The LLM's errors are systematic and learnable. Our trained models can catch them. Our trained models' blind spots (cold start, novel vibes, context drift) are exactly what the LLM covers well. The question is how to wire them together decisively rather than defaulting one over the other.

This document evaluates five architectures:

1. **Two-Tower (current plan)** — baseline reference
2. **SASRec / Sequential Transformer** — sequence-aware user modeling
3. **DLRM (Meta)** — feature interaction depth at scale
4. **HLLM (ByteDance)** — hierarchical LLM-native recommendation
5. **Hybrid Arbitration Stack (proposed)** — Overplanned-specific synthesis

---

## Part I — The Two-Tower Model: What It Actually Does and Where It Fails

### Architecture

The two-tower model (also called dual encoder) produces two independent embedding towers:

- **User tower:** takes persona dimensions, behavioral history, trip context → outputs 64-dim user embedding
- **Item tower:** takes ActivityNode features (vibe tags, category, source scores, quality signals) → outputs 64-dim item embedding

At inference: cosine similarity between user embedding and item embeddings in Qdrant. Top-K candidates retrieved via ANN (approximate nearest neighbor search). Fast: ~2ms for 10K candidates.

### Where It's Strong

- **Speed.** ANN retrieval at serving time is essentially free. The compute happens at training time and embedding storage time. This is why YouTube, Pinterest, and Airbnb all use it as the retrieval layer.
- **Scalability.** Adding 100K new ActivityNodes doesn't slow serving — just add vectors to Qdrant.
- **Cold start on the item side.** A new venue can get an embedding from its features alone (vibe tags, category, location) before anyone has interacted with it.

### Where It Fails

**The independence assumption is the core problem.** The two towers never talk to each other during training. User embedding and item embedding are trained to be close together in the end but they learn completely independently. This means:

- **Cross-feature interactions are invisible.** "This user likes hidden gems AND they're traveling with a partner AND it's evening" is a compound signal. The two-tower model can't learn that the intersection of these three things predicts a specific type of bar over a restaurant, because that triple interaction is never explicitly modeled — only the dot product of the final vectors is.
- **Static user representation.** The user tower produces one embedding per user state. It doesn't model *sequence* — the fact that the user started the day at a museum and is now pivoting toward something quieter is lost. Only the persona snapshot at trip creation time is encoded.
- **Temporal context blindness.** Day 1 of a trip and Day 3 of a trip should produce different recommendations even for the same user. The two-tower model as designed doesn't differentiate these unless day number is explicitly a feature in the user tower.
- **The tourist-local divergence problem.** Cross-source quality signals (`tourist_local_divergence`, `cross_ref_confidence`) exist on ActivityNodes but the two-tower model's item tower has to reduce them to a fixed-dim vector. The nuanced interaction between "this user scores high on local_vs_tourist_bias" AND "this venue has high divergence" requires the model to learn a specific cross-feature interaction that the dot-product similarity may not adequately capture.

### The honest assessment

Two-Tower is correct as a **retrieval layer** — fast ANN to get 50-200 candidates from 50,000 possible activities. It is not suitable as the sole **ranking layer**. The existing architecture uses it for both, which is a common oversimplification. The right use of Two-Tower is: retrieve a candidate set, then apply a separate re-ranker that models cross-feature interactions explicitly.

---

## Part II — SASRec / Sequential Transformer

### What It Is

SASRec (Self-Attentive Sequential Recommendation) treats the user's interaction history as a sequence and uses a causal transformer (like GPT's decoder) to model it. BERT4Rec uses bidirectional attention. Both are well-validated in production RecSys.

The core insight: **the order of interactions matters.** A user who went: coffee shop → art museum → quiet lunch → bookstore is different from one who went: crowded market → bar → loud restaurant → nightclub, even if they ended up accepting the same number of activities. The sequence encodes energy trajectory and preference momentum.

### What It Does That Two-Tower Can't

```
Input sequence:
  [morning: espresso bar, slow, local]
  [midday: bookstore / zine shop, cultural]
  [afternoon: small gallery, low-traffic]
  → NEXT: [predict] ???

SASRec output: high probability → intimate wine bar, quiet neighborhood, post-6pm
Two-Tower output: whatever the user embedding's nearest neighbors are (order-blind)
```

The transformer reads the trajectory. It doesn't just know "this user likes quiet places" — it knows "this user has been building toward a quiet evening and the sequence says they want to stay in that register for the next slot."

This is directly applicable to Overplanned's mid-trip pivot problem. When a user pivots at 3pm on Day 2, the best replacement is not just "similar activity" — it's "the next beat in the energy curve they've been building." SASRec models that.

### BERT4Rec vs SASRec: Which One

SASRec is the right choice for Overplanned, not BERT4Rec.

- SASRec uses causal (left-to-right) attention — it predicts the *next* item given what came before. This matches the travel use case: we're always predicting the next slot, not filling a gap.
- BERT4Rec uses bidirectional attention trained on masked item prediction. Better for understanding sequences holistically but less natural for next-item prediction at serving time.
- Research reviews (RecSys 2022) show BERT4Rec's reported superiority over SASRec isn't consistently reproducible — SASRec is the safer production bet.

### Personalization Gap

The original SASRec has **no explicit user embedding** — it assumes the sequence itself represents the user. This creates a "dimensional collapse" problem for cold-start users: two users with short, similar sequences look identical.

The fix is U-SASRec: inject a learned user embedding via cross-attention into the sequence model. This is a ~20 line change that makes the sequence model persona-aware. This is the version Overplanned should target.

### Data Requirements

SASRec needs sequences of at least 3-5 interactions to produce meaningful predictions. Below that, it degrades to popularity-based recommendations. At launch this is fine — cold users use the LLM, warm users (3+ trip interactions) activate SASRec.

Minimum viable: ~500 behavioral sequences of 5+ interactions. This is achievable by Month 3-4 per the bootstrap timeline.

### Relationship to Two-Tower

These aren't competing. The right stack is:

```
Two-Tower: retrieval (fast ANN, 50K → 200 candidates)
SASRec: re-ranking (sequence-aware scoring on the 200 candidates)
```

They do different jobs. Don't choose between them.

---

## Part III — DLRM (Meta's Deep Learning Recommendation Model)

### What It Is

DLRM combines embedding-based representations (like two-tower) with explicit pairwise feature interaction modeling via dot products between all pairs of embedding vectors. It sits between simple embedding similarity and a full deep cross network.

The key innovation: rather than just computing dot product between user embedding and item embedding, DLRM computes dot products between *all pairs* of feature embeddings and concatenates them as interaction features into a final MLP.

```
Features:
  user.pace_preference (dense)
  user.food_adventurousness (dense)
  item.vibe_embedding (64-dim → embedding lookup)
  item.tourist_score (dense)
  item.source_authority (dense)

DLRM: compute all pairwise dot products between embedding vectors
      + bottom MLP for dense features
      → concatenate interaction features
      → top MLP → probability score
```

### What It Adds Over Two-Tower

**Explicit second-order feature interactions.** Instead of hoping the model learns that `local_vs_tourist_bias=high` × `tourist_local_divergence=high` predicts acceptance, DLRM explicitly models that cross-term as an input feature to the top MLP.

For Overplanned this is valuable because the local source signal architecture is built around *cross-referencing* quality signals from multiple sources. DLRM is architecturally designed to exploit exactly that kind of feature interaction.

### Where It Falls Short for Overplanned

DLRM was designed for ads CTR prediction: single-timestamp binary classification (click/no-click) on hundreds of features. It has no sequential modeling. It doesn't capture trajectory, momentum, or context drift mid-trip. For a single ranking call in isolation it's powerful; for understanding a user's trip arc over multiple days it's insufficient.

### The Right Role for DLRM-Style Interaction Modeling

Use the DLRM feature interaction layer as a **scoring head** on top of SASRec's sequence output. SASRec encodes the user's behavioral trajectory as a vector; then explicit cross-feature interactions (from DLRM's dot-product interaction layer) enhance the final ranking score for each candidate. This is sometimes called DLRM+sequential or a two-stage ranker.

---

## Part IV — HLLM (Hierarchical LLM, ByteDance 2024)

### What It Is

HLLM is the most relevant recent architecture for what Overplanned is actually trying to build. ByteDance published this in 2024 for their recommendation stack. The core idea: use a small LLM (7B parameters, not a full GPT-4) to model *both* item representations and user behavior sequences, organized hierarchically.

```
Item LLM: takes item text descriptions → generates rich item embeddings
User LLM: takes sequence of user-item interactions → generates user state embedding
Both embeddings feed into a final scoring layer
```

### Why This Is Directly Relevant to Overplanned's Dilemma

The problem we've been circling is: LLMs have world knowledge about venues (Overplanned's local source corpus is a subset of what models like Sonnet already know), but they don't have user-specific behavioral signal. DLRM and Two-Tower have behavioral signal but no world knowledge. HLLM wires them together structurally.

For Overplanned, the HLLM insight translates to: the item tower should use LLM-generated embeddings (not just feature-engineered vibe tags), and the user sequence model should interact with those richer item representations rather than compressed feature vectors.

In practice at Overplanned's scale: you don't need a 7B parameter model. A fine-tuned sentence-transformer (e.g., `all-MiniLM-L6-v2`, 22M params) running on CPU can generate item embeddings from ActivityNode text descriptions in <5ms. This is the "LLM as teacher, small model as student" pattern already in the bootstrap docs — just applied more aggressively to both towers.

### The Production Hierarchy

```
Phase 1 (now - Month 5):
  Item embeddings: LLM (Haiku batch) → extract text features → store on ActivityNode
  User state: LLM ranker (Sonnet) → serves directly

Phase 2 (Month 5-9):
  Item embeddings: fine-tuned sentence-transformer (distilled from Phase 1 LLM outputs)
  User state: SASRec on behavioral sequence (replaces LLM ranker for warm users)

Phase 3 (Month 9+):
  Item LLM tower: fine-tuned MiniLM on Overplanned corpus with local source signals
  User tower: U-SASRec (sequence + persona embedding, cross-attention)
  Scoring head: DLRM-style feature interaction layer
  LLM: arbitration and edge case handling only
```

---

## Part V — The Proposed Architecture: Hybrid Arbitration Stack

This is the synthesis. Rather than sequential model replacement (LLM → BPR → Two-Tower → LightGCN), Overplanned should run a **parallel scoring stack with explicit arbitration logic** between ML and LLM.

### Core Insight: LLMs Make Systematic, Learnable Errors

LLM recommendation errors fall into predictable categories:

1. **Popularity bias.** LLMs trained on internet text over-represent popular venues. Their "hidden gem" output is often just "medium-popular venue with a good blog post." Our cross-reference signal corrects this.
2. **Temporal blindness.** LLMs don't know it's evening Day 3 of a trip and the user is tired. Sequential models do.
3. **False personalization.** LLMs can simulate personalization from a compressed persona prompt but they don't actually weight features the way behavioral data does. A user who has accepted 8 outdoor activities in a row should get more outdoor suggestions — the LLM might not weight that as heavily as a trained model would.
4. **Context collapse in groups.** LLMs struggle with multi-person compromise modeling. The group affinity matrix (built from individual persona vectors) is something a trained model handles far better.
5. **Novel local venues.** Venues that emerged after the LLM's training cutoff, or that were never indexed in English-language sources, are invisible to the LLM. Our Pipeline C corpus may have them; the LLM doesn't.

These errors are **measurable**. For each one, we can define a detector. The arbitration layer is a set of those detectors.

### Architecture Diagram

```
User request (trip slot to fill)
        │
        ▼
┌─────────────────────────────────────────────────────┐
│              Candidate Retrieval                      │
│  Two-Tower ANN → 200 candidates from ActivityNode DB  │
└─────────────────────────────────────────────────────┘
        │                         │
        ▼                         ▼
┌─────────────────┐    ┌───────────────────────┐
│  ML Scoring     │    │  LLM Scoring           │
│                 │    │                        │
│  U-SASRec       │    │  Sonnet (compressed    │
│  sequence score │    │  persona + candidates) │
│                 │    │                        │
│  + DLRM feature │    │  Output: ranked list   │
│  interaction    │    │  + confidence signal   │
│  score          │    │                        │
│                 │    │  Run in parallel,      │
│  Output:        │    │  NOT sequentially      │
│  ranked list    │    └───────────────────────┘
│  + confidence   │              │
└─────────────────┘              │
        │                        │
        └──────────┬─────────────┘
                   │
                   ▼
     ┌─────────────────────────┐
     │   Arbitration Layer     │
     │                         │
     │  Agreement → ML output  │
     │  Disagreement → check:  │
     │    • cold user? → LLM   │
     │    • high LLM conf +    │
     │      low ML conf? → LLM │
     │    • popularity bias    │
     │      detected? → ML     │
     │    • sequence momentum  │
     │      signal? → ML       │
     │    • novel venue? → ML  │
     └─────────────────────────┘
                   │
                   ▼
          Final ranked list
```

### The Arbitration Layer — Decision Rules

```python
class RankingArbiter:
    """
    Explicit decision logic for ML vs LLM ranking disagreements.
    This is deterministic, not learned — explainable and debuggable.
    """

    def arbitrate(
        self,
        ml_ranking: list[str],
        llm_ranking: list[str],
        context: ArbitrationContext
    ) -> list[str]:

        agreement_score = self._rank_correlation(ml_ranking, llm_ranking)

        # High agreement: ML wins (it has behavioral signal the LLM doesn't)
        if agreement_score > 0.75:
            return ml_ranking

        # Cold user: LLM wins (no behavioral signal for ML to use)
        if context.user_trip_count < 3:
            return llm_ranking

        # Popularity bias detected in LLM output
        if self._popularity_bias_detected(llm_ranking, context):
            return ml_ranking

        # Strong sequence momentum signal (user has built a clear trajectory)
        if context.sequence_momentum_score > 0.7:
            return ml_ranking  # SASRec sees the pattern; LLM doesn't

        # Group trip with multi-person conflict
        if context.is_group_trip and context.group_conflict_score > 0.4:
            return ml_ranking  # Group affinity model is purpose-built for this

        # Novel venue in ML top-3 (post-LLM training cutoff)
        if self._novel_venue_in_top(ml_ranking, n=3, context=context):
            return ml_ranking  # LLM can't score what it doesn't know

        # Default: ML for warm users, LLM for cold
        return ml_ranking if context.user_trip_count >= 3 else llm_ranking

    def _popularity_bias_detected(self, ranking, context) -> bool:
        """
        LLM tends toward popular venues when persona says local-first.
        Detect: top LLM pick has high tourist_score AND user has
        high local_vs_tourist_bias persona dimension.
        """
        top_activity = self._get_activity(ranking[0])
        return (
            top_activity.tourist_score > 0.7
            and context.persona.local_vs_tourist_bias > 0.6
        )

    def _rank_correlation(self, r1, r2) -> float:
        """Spearman rank correlation on top-10"""
        ...
```

### Why Deterministic Arbitration, Not a Learned Meta-Model

The instinct might be to train a meta-model on top of the two rankers. Don't — not yet. Reasons:

- At pre-500-user scale, you don't have enough data to train a reliable meta-ranker.
- Deterministic rules are debuggable. When the wrong venue gets served, you can trace exactly which rule fired. A learned meta-ranker is a black box on top of two other black boxes.
- The error categories above (popularity bias, sequence momentum, cold start) are well-defined enough that rules work. Only when the rules consistently fail in a pattern should you consider learning the arbitration logic.
- LLMs make systematic errors, not random ones. Rules are appropriate for systematic errors.

### Logging Requirements for Arbitration

Every arbitration decision must be logged. The log is the data source for eventually improving the rules:

```sql
CREATE TABLE arbitration_events (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID,
    trip_id          UUID,
    slot_id          UUID,
    ml_top3          UUID[],          -- ML ranker's top 3
    llm_top3         UUID[],          -- LLM ranker's top 3
    arbitration_rule VARCHAR(50),     -- which rule fired
    served_activity  UUID,            -- what was actually served
    accepted         BOOLEAN,         -- did user accept it?
    agreement_score  FLOAT,           -- rank correlation at decision time
    context_snapshot JSONB,           -- compressed ArbitrationContext
    occurred_at      TIMESTAMPTZ DEFAULT NOW()
);
```

Over time, this table lets you answer: "When rule X fires and we serve ML output, does the user accept at a higher rate than when we serve LLM output?" That's the data to eventually learn the arbitration rather than hardcode it.

---

## Part VI — Architecture Comparison Summary

| Dimension | Two-Tower (current) | SASRec | DLRM | HLLM | Hybrid Arbitration |
|---|---|---|---|---|---|
| **Sequential context** | ✗ None | ✓ Core capability | ✗ None | ✓ Via LLM | ✓ Via U-SASRec |
| **Cross-feature interaction** | ✗ Only dot product | ✗ Sequence only | ✓ Explicit pairwise | ✓ Via LLM reasoning | ✓ DLRM scoring head |
| **World knowledge** | ✗ Learned features only | ✗ | ✗ | ✓ Native | ✓ LLM arm |
| **Cold start** | ~ Partial (item features) | ✗ Needs sequence | ~ Feature-based | ✓ LLM zeros in | ✓ LLM arm handles |
| **Local source advantage** | ~ Feature encoding only | ~ Feature encoding | ~ Feature encoding | ✗ LLM is the bias | ✓ ML arm corrects bias |
| **Group dynamics** | ✗ Not modeled | ✗ | ✗ | ~ Poor | ✓ Dedicated module |
| **Explainability** | ~ Embedding similarity | ~ Sequence weights | ~ Feature scores | ✗ LLM black box | ✓ Arbitration rule log |
| **Data efficiency** | ✓ Good | ~ Needs sequences | ✓ Good | ✓ LLM compensates | ✓ Best of both |
| **Latency** | ✓ Fast ANN | ~ Medium | ~ Medium | ✗ LLM latency | ~ Parallel adds ~50ms |
| **Complexity to implement** | Simple | Medium | Medium-High | High | Medium (builds on both) |
| **Scale needed to train** | 500+ interactions | 500+ sequences | 1,000+ interactions | None (LLM) | 500+ for ML arm |

---

## Part VII — Implementation Sequence (Updated)

This replaces the clean sequential LLM→BPR→Two-Tower→LightGCN progression. The new sequence:

**Now → Month 5: Foundation logging**
- All current logging stays. Add arbitration event table.
- Run LLM ranker as before but log ML-equivalent features alongside every decision.
- This creates the training data for Month 5+ models without changing what users see.

**Month 5-7: Parallel ML arm comes online**
- Train U-SASRec on accumulated behavioral sequences (need 500+ sequences of 5+ interactions).
- Run in shadow mode: LLM still serves, U-SASRec computes ranking in parallel.
- Log agreement scores — are they typically high (good) or low (investigate)?
- Arbitration layer enters shadow mode: it would have fired X% of the time, would have chosen ML/LLM in each case.

**Month 7-9: Arbitration goes live**
- Arbitration layer begins making real decisions for warm users (3+ trips).
- Cold users still go to LLM directly.
- Monitor: per-rule acceptance rates. Kill any rule that performs worse than LLM alone.
- Add DLRM-style feature interaction scoring head to re-ranker.

**Month 9-12: Item tower enrichment**
- Fine-tune sentence-transformer on ActivityNode text + local source corpus.
- Replace hand-engineered vibe tag features with learned text embeddings in item tower.
- This is the HLLM insight applied at Overplanned's scale: LLM-quality item representations without LLM serving costs.

**Month 12+: Learned arbitration**
- By now ~1,500+ arbitration events logged with outcomes.
- Train a small gradient-boosted classifier on arbitration features → predict which ranker to trust.
- Replace rule-based arbitration with this classifier.
- LightGCN enters shadow mode against Two-Tower+SASRec for high-density users.

---

## Part VIII — The Decisive Transformer Position

To directly address the philosophical question: what does it mean for Overplanned to be a "better transformer" than a general LLM?

The LLM's weakness as a travel recommender is not knowledge — it knows more than our corpus. Its weakness is **decisive personalization under constraints**:

- It can't confidently say "given that this specific user has consistently rejected busy morning venues and it's 9am on Day 4 of their trip, I'm 87% confident they want Option A not Option B."
- It hedges. It generates plausible-sounding options without strong conviction ranking.
- Its tourist-weighted training prior fights against local-first recommendations even when explicitly prompted against it.
- It can't model the difference between what this user *said* they wanted (persona tags) and what they *revealed* they wanted (behavioral signals).

The ML layer is decisive where the LLM hedges. The trained ranker doesn't generate options — it scores them with calibrated confidence. The arbitration layer is where that confidence either overrides or defers to LLM judgment.

The goal isn't to out-know the LLM. It's to out-*decide* it, specifically for travel personalization, specifically for users whose behavioral signal makes that decisive ranking possible.

---

*Last updated: February 2026*
*Next: U-SASRec implementation spec, arbitration event schema migration, item tower enrichment pipeline*
