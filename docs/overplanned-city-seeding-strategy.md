# Overplanned — City Seeding Strategy

*Internal Reference · February 2026*

---

## Philosophy

Don't pre-seed every city. Let user demand tell you where to invest. Pre-seed only cities with high confidence of early traffic. Everything else is covered by on-demand Tier 2/3 fallback at near-zero cost.

International cities are seeded **on demand via admin tooling only** — no upfront international spend until US demand is proven.

---

## Initial Seed List (Pre-Launch)

### Tier 1 Core US — High Traffic Probability

| City | Rationale |
|---|---|
| New York | Highest US travel destination by volume |
| Los Angeles | Second highest, diverse activity types |
| Chicago | Major domestic travel hub |
| Miami | High seasonal traffic, distinct vibe profile |
| San Francisco | Tech-adjacent early user base |
| New Orleans | Strong persona signal density (food, culture, nightlife) |
| Nashville | Fastest growing US travel destination |
| Austin | Strong local vs. tourist divergence — good ML signal |
| Las Vegas | High intent trips, clear activity taxonomy |

### Tier 1 Outliers — PNW + Oregon

| City | Rationale |
|---|---|
| Seattle | Major PNW hub, strong Reddit local signal |
| Portland | High local source density, distinct food/culture scene |
| Tacoma | Small enough to validate overrated detector accuracy |
| Bend | Tight venue set — ideal quality canary for pipeline health |

**Total: 13 cities**

---

## Cost Estimate

| Item | Detail | Cost |
|---|---|---|
| LLM batch extraction | 13 cities × ~$6 avg (Haiku batch pricing) | ~$78 |
| Cloud Vision validation | ~1,200 nodes/city avg × 13 × $1.50/1K | ~$23 |
| GCS storage | 50K nodes × 80KB = ~4GB | ~$0.08/mo |
| **Total one-time** | | **~$100–115** |

Outlier cities (Tacoma, Bend) have smaller node counts and lower extraction costs — they pull the average down.

---

## City Tier Model

| Tier | What it is | Coverage | Cost |
|---|---|---|---|
| **Tier 1 — Pre-seeded** | Full LLM extraction, vibe embeddings, local/tourist divergence, persona scoring | 13 launch cities | $6–13 per city, one-time |
| **Tier 2 — On-demand** | Live Places API + deterministic scoring + rule-based vibe tags. Stored on first request. | Any city a user requests | ~$0.02 per city |
| **Tier 3 — True unknown** | Pure Places fallback, minimal scoring, fewer candidates | Rural areas, tiny towns | ~$0.01 per city |

---

## On-Demand Seeding (Post-Launch)

All cities outside the initial 13 — including all international cities — are seeded on demand through admin tooling. A Tier 2 city graduates to Tier 1 either:

- **Organically** — via monthly graduation query (50+ nodes, 10+ user requests threshold)
- **Manually** — admin triggers `graduate_city_to_tier1(city)` directly for a friend's trip or anticipated demand spike

No re-fetching required. Raw platform data is preserved in GCS logs at Tier 2/3 collection time. LLM batch extraction reads from those logs, not from live APIs.

---

## Quality Canary: Tacoma & Bend

Small cities with tight venue sets serve as pipeline health indicators. If Bend recommendations feel authentic and local, the pipeline is working. If tourist-trap venues surface at the top, the overrated detector or cross-reference scoring needs tuning. Check these before any major city launch.

---

## Graduation Query (Run Monthly Starting Month 4)

```sql
SELECT city,
  COUNT(DISTINCT activity_node_id) AS nodes,
  COUNT(DISTINCT request_count)    AS user_requests
FROM city_tier_events
WHERE tier IN (2, 3)
  AND vibe_confidence < 0.5
GROUP BY city
HAVING COUNT(DISTINCT activity_node_id) >= 50
   AND COUNT(DISTINCT request_count)    >= 10
ORDER BY user_requests DESC;
-- Top results = backfill queue. Submit batch job. City graduates silently.
```

---

*Overplanned Internal · February 2026*
