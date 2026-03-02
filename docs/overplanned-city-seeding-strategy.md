# Overplanned — City Seeding Strategy

*Internal Reference · February 2026*

---

## Philosophy

Seed cities with **corpus depth without aggregator saturation**. Selection criteria:
- Active, locally-oriented subreddit (locals talking to locals, not tourists asking tourists)
- Passionate outdoor, food, or expat community producing English-language text obsessively
- High tourist/local divergence — the "real" version is meaningfully different from what Google Maps shows
- Not already dominated by SEO-optimized listicles (eliminates NYC, SF, LA, Chicago)

Don't pre-seed speculatively. Cities seeded on-demand via admin tooling as demand triggers. This list defines priority order.

---

## Tier 1 — US Outdoor / Adventure Towns

| City | State | Notes |
|---|---|---|
| Bend | OR | Poster child. r/Bend locally-focused, obsessive brewery + trail culture |
| Asheville | NC | Farm-to-table food culture, independent music scene, 50k+ active subreddit |
| Missoula | MT | Fly fishing, hiking, arts communities — low tourist saturation |
| Flagstaff | AZ | Strong NAU community, outdoor culture, stargazing obsessives |
| Bozeman | MT | Fastest-growing outdoor town in US, Yellowstone proximity |
| Durango | CO | Obsessive MTB community, strong food scene, less covered than Telluride |
| Moab | UT | High tourist volume, extremely divergent local layer |
| Taos | NM | Art + ski + Native American history + food. Deeply local, aggregator-invisible |
| Sedona | AZ | Massive tourist volume, extremely high local/tourist divergence |
| Hood River | OR | Best PNW wineries/breweries, kitesurfing culture, locals know everything |
| Truckee | CA | Sierra Nevada base camp, obsessive trail and food intel |
| Mammoth Lakes | CA | Year-round mountain town, dense seasonal intel aggregators miss |
| Jackson Hole | WY | High local/tourist divergence despite massive volume. Locals deeply protective of non-resort layer |
| Telluride | CO | Tight valley community with outsized local pride. Festival culture, ski-to-hike transitions |

---

## Tier 2 — US Mid-Size Cities with Hidden Depth

| City | State | Notes |
|---|---|---|
| Austin | TX | Strong local vs. tourist divergence, obsessive food + music scene |
| Seattle | WA | Major PNW hub, strong Reddit local signal, neighborhood depth |
| Portland | OR | High local source density, distinct food/culture scene |
| New Orleans | LA | Enormous local/tourist divergence — locals know spots that never appear on any list |
| Portland | ME | Extraordinary food scene per capita, distinct from Oregon Portland |
| Burlington | VT | Lake Champlain, strong local food + arts + outdoor culture |
| Tucson | AZ | UNESCO City of Gastronomy. Sonoran food, criminally underrepresented |
| Madison | WI | Farm-to-table before it was a trend, farmers market culture |
| Fort Collins | CO | Brewery culture, farm-to-table emergence, underrated vs. Boulder |
| Durham | NC | James Beard nominees, strong local blog culture, still under-aggregated |
| Columbus | OH | Outsized food scene, Short North neighborhood, often overlooked |
| Detroit | MI | Eastern Market, Corktown revival, soul food — dense vocal local community |
| Pittsburgh | PA | Strip District, Eastern European food legacy, r/pittsburgh active |
| Greenville | SC | Blue Ridge foothills, brewery scene, punching above weight |
| Charleston | SC | Lowcountry food culture deep and locally protected, high divergence |

---

## Tier 2 — Vacation / Mountain Towns (the moat)

| City | State | Notes |
|---|---|---|
| Santa Fe | NM | Art scene, New Mexican cuisine, strong local culture |
| Marfa | TX | Tiny but Chinati Foundation crowd produces obsessive local intel |
| Fredericksburg | TX | Texas Hill Country wine + food, German heritage, underrepresented |
| Savannah | GA | Historic, food culture strong, locals protective of non-tourist layer |
| Charlottesville | VA | Wine trail, UVA culture, strong local food scene |
| Traverse City | MI | Cherry country, wine, Lake Michigan — obsessive local food + outdoor community |
| Saugatuck | MI | Southwest Michigan beach and food culture, small but locally documented obsessively |
| Eureka Springs | AR | Quirky Ozarks arts town, underrepresented, passionate local community |
| Bentonville | AR | Crystal Bridges, mountain biking, emerging food scene |
| Ogden | UT | Best kept secret in Utah per local consensus. Snow Basin proximity |
| Buena Vista | CO | Arkansas River rafting, hip food + music scene |
| Glenwood Springs | CO | Hot springs, Hanging Lake, smaller than Aspen with better local intel |
| Ketchum / Sun Valley | ID | Ski + outdoor culture, Hemingway legacy, strong food scene for its size |
| Whitefish | MT | Glacier NP gateway with strong local identity |
| Steamboat Springs | CO | Cowboy culture meets ski culture, strong local opinions |

---

## Tier 3 — International (Expat / Nomad Dense English Corpus)

| City | Country | Notes |
|---|---|---|
| Mexico City | Mexico | Deep local food scene, bilingual corpus, massive neighborhood divergence |
| Chiang Mai | Thailand | Original nomad hub. ThaiVisa forums, Nomad List, r/chiangmai |
| Tbilisi | Georgia | Rapidly growing expat community, ancient wine culture, extraordinary food |
| Medellin | Colombia | Transformed city, massive expat community, r/medellin detailed insider content |
| Oaxaca | Mexico | Food capital of Mexico, mezcal culture, expat food writers extraordinary |
| San Miguel de Allende | Mexico | Large expat community, arts culture, well-documented by long-term residents |
| Porto | Portugal | Richer local character than Lisbon, wine culture |
| Lisbon | Portugal | Tourist-heavy but strong expat documentation of authentic layer |
| Tallinn | Estonia | Medieval city, growing nomad hub, good English-language expat community |
| Ljubljana | Slovenia | Under the radar, strong local food + wine culture |
| Kotor | Montenegro | UNESCO World Heritage, still under the radar, growing nomad winter base |
| Hoi An | Vietnam | Expat food + culture community extensive, strong English documentation |
| Penang | Malaysia | Street food capital of SE Asia, obsessive food documentation |
| Kyoto | Japan | Enormous local/tourist divergence, Tabelog surfaces a completely different city |
| Osaka | Japan | Dotonbori is tourist — the rest of the city is a different world |

---

## Canary Cities

| City | State | Purpose |
|---|---|---|
| Bend | OR | Pipeline quality canary — tight venue set, validated |
| Tacoma | WA | Overrated detector canary — small enough to verify accuracy |

---

## What We're Explicitly Not Seeding

- NYC, SF, LA, Chicago — aggregator home turf, can't win on corpus quality
- Pure beach resort towns (Cancun, Myrtle Beach) — tourist monoculture, no meaningful divergence
- Small towns with no English-language community — corpus too thin for vibe embeddings
- International cities speculatively — demand-driven only

---

## City Tier Model

| Tier | What it is | Coverage | Cost |
|---|---|---|---|
| **Tier 1 — Pre-seeded** | Full LLM extraction, vibe embeddings, local/tourist divergence, persona scoring | 14 adventure towns + 2 canaries | ~$6-13 per city, one-time |
| **Tier 2 — Priority** | Same as Tier 1, seeded after canary validation | 15 mid-size + 15 vacation/mountain | ~$6-13 per city, one-time |
| **Tier 2 — On-demand** | Live Places API + deterministic scoring + rule-based vibe tags. Stored on first request. | Any city a user requests | ~$0.02 per city |
| **Tier 3 — True unknown** | Pure Places fallback, minimal scoring, fewer candidates | Rural areas, tiny towns | ~$0.01 per city |

---

## On-Demand Seeding (Post-Launch)

All cities outside Tier 1 are seeded on demand through admin tooling. A Tier 2 city graduates to Tier 1 either:

- **Organically** — via monthly graduation query (50+ nodes, 10+ user requests threshold)
- **Manually** — admin triggers `graduate_city_to_tier1(city)` directly

No re-fetching required. Raw platform data is preserved in GCS logs at Tier 2/3 collection time. LLM batch extraction reads from those logs, not from live APIs.

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

*~62 cities total across 4 tiers. Cities seeded on-demand via admin tooling, not pre-loaded speculatively. This list defines priority order when demand triggers seeding.*
