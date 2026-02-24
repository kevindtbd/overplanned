# Overplanned — City Seed List
*February 2026 · Internal*

## ML Bootstrap Starter Set — Seed These First

Before anything else, these 7 cities should be seeded together. They're chosen not because they're the most interesting cities on the list, but because together they give the embedding models the **vibe diversity** needed to learn a meaningful 64-dim space. If you only seed similar cities, the geometry collapses and the embeddings become useless outside a narrow band.

| City | What it contributes to the embedding space |
|---|---|
| **Austin, TX** | High energy, food + nightlife + outdoor mix, urban density, strong local/tourist divergence. Best single city for signal diversity. |
| **New Orleans, LA** | Slow burn, deep food culture, music-first, walkable neighborhoods. Fills the opposite end of the energy spectrum from Austin. |
| **Seattle, WA** | PNW outdoor + urban tech culture, one of the most locally-active large subreddits in the US. Dense node count, strong category mix. |
| **Asheville, NC** | Intimate local, farm-to-table, arts, anti-chain. Fills the "small city, no tourists, real locals" corner of the space. Good overrated detector training — locals vocal about what's changed. |
| **Portland, OR** | Strongest local food criticism culture on the list. DIY, neighborhood-first, slower pace. Distinct vibe from Seattle despite proximity. r/Portland enormous and locally protective. |
| **Mexico City, MX** | Only international city in the starter set. Neighborhood-level divergence is enormous. Expat corpus is dense and honest. Adds cultural geometry the US-only set can't provide. |
| **Bend, OR** | Tight venue set (~500 nodes) but extremely high signal quality. Canary city — if embeddings are working, Bend recommendations will show it. If something's broken, you'll see it here first. |

**Together these cover:** high vs. low energy, urban vs. small town, food-dominant vs. outdoor-dominant, domestic vs. international, large corpus vs. clean tight corpus. Enough geometry for the item tower to learn before behavioral data arrives.

**Add at Month 2–3** once early behavioral signal exists: Nashville and Chicago — high node density and strong divergence, but seed them once co-occurrence patterns can start training immediately.

**Estimated bootstrap cost for starter set:** ~$90–130 total one-time.

---

## Selection Criteria

A city qualifies when it has **corpus depth without aggregator saturation**. Specifically:

- Active, locally-oriented subreddit (locals talking to locals, not tourists asking tourists)
- Passionate outdoor, food, or expat community that produces English-language text obsessively
- High tourist/local divergence — the "real" version is meaningfully different from what Google Maps shows
- Not already dominated by SEO-optimized listicles (eliminates NYC, SF, Chicago, LA)
- Atlas Obscura density as a proxy for underdocumented interesting things

The goal is not small cities. It's cities where **our Pipeline C can surface something no aggregator has**.

---

## Tier 1 — Seed First (Highest corpus quality + demand signal)

These have the best combination of passionate local community, active Reddit presence, and high tourist/local divergence. Start here.

### US Outdoor / Adventure Towns

| City | State | Why It Qualifies |
|---|---|---|
| **Bend** | OR | Poster child. r/Bend is locally-focused, obsessive brewery + trail culture, locals actively resent tourist recommendations. 300+ miles of trail systems documented by residents not tour operators. |
| **Asheville** | NC | Strong farm-to-table food culture, independent music scene, r/asheville (50k+) is locally active. Meaningfully different from what TripAdvisor shows. UNESCO City of Gastronomy adjacent. |
| **Missoula** | MT | University town with extraordinary outdoor culture. Fly fishing, hiking, and arts communities produce dense local text. Low tourist saturation relative to the richness of local intel. |
| **Flagstaff** | AZ | Grand Canyon gateway but deeply its own city. Strong NAU community, outdoor culture, stargazing obsessives. Less dominated by tourist traffic than its proximity to major parks would suggest. |
| **Bozeman** | MT | Fastest-growing outdoor town in the US. Passionate local community, Yellowstone proximity, Gallatin Valley food culture emerging rapidly. Locals vocal about what's changed vs. what's stayed local. |
| **Durango** | CO | San Juan Mountains, obsessive mountain biking community, strong food scene for its size. Less covered than Telluride or Aspen. r/Durango is active and locally focused. |
| **Moab** | UT | High tourist volume but extremely divergent local vs. tourist layer. Locals know entirely different trails, restaurants, timing. The gap between Yelp and r/Moab is substantial. |
| **Taos** | NM | Art community + ski culture + Native American history + food scene. Deeply local, deeply opinionated, largely invisible to aggregators outside ski season. |
| **Sedona** | AZ | Massive tourist volume, extremely high local/tourist divergence. Locals have entirely separate recommendations from the vortex-tour-and-trolley-car circuit that visitors see. |
| **Hood River** | OR | Best wineries and breweries in PNW, kitesurfing culture, Columbia River Gorge access. Small enough that locals know everything. Underrepresented online relative to quality. |
| **Truckee** | CA | Sierra Nevada base camp, year-round, not just a Tahoe suburb. Locals produce obsessive trail and food intel. Distinct identity from the resort towns around it. |
| **Mammoth Lakes** | CA | Year-round mountain town, not just a ski resort. Local community produces dense seasonal intel most aggregators miss entirely. |

### US Mid-Size Cities with Hidden Depth

| City | State | Why It Qualifies |
|---|---|---|
| **Portland** | ME | Compact, walkable, extraordinary food scene per capita. r/portlandme is locally focused and distinct from r/Portland (Oregon). Seafood and craft cocktail culture well-documented by locals. |
| **Burlington** | VT | Lake Champlain town with strong local food, arts, and outdoor culture. Community-centric by nature — locals share aggressively. |
| **Tucson** | AZ | UNESCO City of Gastronomy. Sonoran food culture, Sichuan scene, farm-to-table deeply embedded. Criminally underrepresented online relative to its actual food depth. |
| **Madison** | WI | Farm-to-table was a way of life here before it was a trend. Farmers market culture, Taiwanese food, excellent ramen. r/madisonwi is active. |
| **Fort Collins** | CO | Rocky Mountain brewery culture, farm-to-table emergence, trails. Underrated relative to Boulder/Denver. Strong local food writing community. |
| **Durham** | NC | Research Triangle food scene, James Beard nominees, strong local blog culture. Emerging fast but still under-aggregated. |
| **Columbus** | OH | Outsized food scene for a Midwest city. Short North neighborhood, strong local critic culture, diverse cuisine. Often overlooked because Ohio. |
| **Detroit** | MI | Eastern Market, Corktown revival, soul food traditions, resilience narrative. Locals are extremely vocal and proud — dense local text. High tourist/local divergence. |
| **Pittsburgh** | PA | Strip District, Andy Warhol Museum, underrated Eastern European food legacy, craft beer. Locals push back hard on Pittsburgh being overlooked. r/pittsburgh is active. |
| **Greenville** | SC | Blue Ridge foothills, brewery scene, Falls Park. Punching above its weight on food, locals document it well. |
| **Charleston** | SC | Lowcountry food culture is deep and locally protected. Locals are extremely opinionated about tourist restaurants vs. the real thing. High divergence. |
| **New Orleans** | LA | Already known, but the local/tourist divergence layer is enormous. Locals know neighborhood spots that never appear on any list. Worth including for that gap alone. |

---

## Tier 1b — Known Cities, Real Friction (Famous but the good stuff requires local knowledge)

These are well-trafficked, well-known cities where Google gives you *something* — but the tourist layer and the local layer are genuinely different cities. Aggregators cover the surface. We cover what's underneath. The user already knows the name; they don't know what locals actually do there.

The friction here is not obscurity — it's **signal-to-noise ratio**. These cities have enormous amounts of data, but most of it is tourist-weighted. Our value is cutting through it.

| City | Country/State | The Friction Gap |
|---|---|---|
| **Austin** | TX | Every aggregator covers 6th Street, Franklin BBQ, and Rainey Street. The real Austin is neighborhood taquerias on East Cesar Chavez, the dive bars that survived the tech boom, the swimming holes locals go to instead of Barton Springs on weekends. r/Austin is enormous but also locally protective — dense signal once you separate locals from newcomers. |
| **Mexico City** | Mexico | One of the world's great food cities. The tourist layer (Polanco, Roma Norte Instagram spots) and the local layer (neighborhood mercados, tlayuda spots in Iztapalapa, mezcalerias in Tepito-adjacent) are almost entirely non-overlapping. Enormous English-language expat and food-writer community producing honest local intel. |
| **Seattle** | WA | Aggregators push Pike Place, Space Needle, and Capitol Hill. Locals operate in Beacon Hill, Columbia City, Georgetown, Ballard. r/Seattle is one of the most locally-active large city subreddits in the US. Tech worker + outdoor culture produces obsessive documentation of everything. High divergence between tourist Seattle and resident Seattle. |
| **Portland** | OR | Already overrepresented in food media but still meaningfully divergent. The SEO layer pushes Voodoo Doughnuts and Powell's. Locals are in Division Street, Foster-Powell, Montavilla. r/Portland is massive and vocal. Strong food criticism culture — locals push back on hype aggressively. |
| **Denver** | CO | RiNo and LoDo are tourist-saturated. Berkeley, Sunnyside, Overland Park are not. Strong outdoor + food culture, r/Denver active and locally-focused. Growing fast enough that locals are vocal about what's changing vs. what's staying real. |
| **Nashville** | TN | Broadway/honky-tonk strip is tourist monoculture. East Nashville, Germantown, 12South are completely different. Local music scene has almost zero overlap with tourist bar culture. r/Nashville actively hostile to tourist recommendations. High divergence. |
| **New Orleans** | LA | Already in Tier 1 Mid-Size, but worth reiterating here at city scale — Magazine Street, Bywater, Tremé exist in a completely different universe from Bourbon Street. The local/tourist divergence is among the highest of any American city. |
| **Chicago** | IL | Aggregators push Magnificent Mile and deep dish. Locals are in Logan Square, Pilsen, Bridgeport, Rogers Park. Ethnic food corridors (Devon Avenue, Argyle Street, 18th Street) are invisible to tourist coverage despite being world-class. r/Chicago is enormous and food-obsessed. Worth including specifically for the neighborhood depth gap. |
| **Washington DC** | DC | Tourist layer is monuments and Georgetown. Local layer is H Street, Shaw, Petworth, Ethiopian corridor on 18th Street NW. Strong local food writing community, r/washingtondc is active. Proximity to NoVA and MD means food diversity is extraordinary and underdocumented. |
| **Philadelphia** | PA | Aggregators push cheesesteak wars and Reading Terminal. Locals are in Fishtown, South Philly Italian Market, Kensington emerging food scene. BYOB culture unique in America and invisible to aggregators. r/philadelphia is locally focused and food-obsessed. |
| **Boston** | MA | Freedom Trail is tourist. Allston, Jamaica Plain, East Boston (East Boston specifically has one of the best Salvadoran/Latin American corridors in the US), Somerville are not. Strong local food critic culture, r/boston active. |
| **Minneapolis** | MN | Hugely underrated food city with massive Somali, Hmong, and Ethiopian communities. Aggregators completely miss the corridors. East Lake Street is a completely different world from what any tourist sees. r/Minneapolis is locally active. |
| **Los Angeles** | CA | Normally excluded but the divergence argument is too strong. Nobody needs us to find Nobu. But the San Gabriel Valley (best Chinese food outside China), Koreatown, Boyle Heights, Leimert Park are largely invisible to aggregators despite being world-class. Specific use case: LA as regional cuisine guide, not LA as celebrity restaurant guide. |
| **San Antonio** | TX | Gets overlooked because Austin absorbs all the Texas travel interest. But the local food culture — Tex-Mex that's actually local, puffy tacos, menudo spots — is extraordinary and deeply underdocumented. r/sanantonio is active and locally focused. |
| **Miami** | FL | Normally excluded but Wynwood/South Beach tourist saturation coexists with Little Havana, Little Haiti, Hialeah, and the Venezuelan/Colombian corridors that aggregators completely ignore. Worth including specifically for the immigrant food community gap. |
| **Barcelona** | Spain | Tourist layer is Las Ramblas and Sagrada Família adjacent restaurants. Local layer is Gràcia, Poble Sec, Sant Pere. Catalan food culture is deep and locally protective. Strong expat food writing community. |
| **Tokyo** | Japan | Aggregators surface Michelin stars and Shibuya crossing. Locals operate in Shimokitazawa, Koenji, Yanaka, Nakameguro back streets. The gap is enormous. Partially dependent on Japanese-language corpus but English-speaking expat community is large and obsessive. |
| **Bangkok** | Thailand | Khao San Road vs. everything else. Strong English-language expat community documents the real city exhaustively. r/Bangkok, Nomad List forums, long-term expat blogs — all dense with local intel invisible to aggregators. |
| **Istanbul** | Turkey | Tourist layer is Sultanahmet and Beyoğlu. Local layer is Karaköy, Kadıköy, Balat, Beşiktaş. Enormous food culture that expats and food writers document obsessively in English. High divergence, strong English corpus. |
| **Buenos Aires** | Argentina | Palermo Soho is gentrified tourist territory. San Telmo, Boedo, Villa Crespo, Chacarita are not. Enormous expat community, strong food and nightlife writing, r/buenosaires active. |
| **Bogotá** | Colombia | La Candelaria is tourist. Chapinero, Usaquén, La Macarena are local. Growing expat tech community producing dense English documentation. Often overlooked for Medellín but comparable depth. |

---

## Tier 2 — Second Wave (Strong signal, slightly thinner corpus or higher seasonality complexity)

| City | State/Country | Notes |
|---|---|---|
| **Santa Fe** | NM | Art scene, New Mexican cuisine, strong local culture. Seasonality is manageable. |
| **Marfa** | TX | Tiny but extremely high local/tourist divergence. Chinati Foundation crowd produces obsessive local intel. |
| **Fredericksburg** | TX | Texas Hill Country wine and food culture. German heritage, local food writing strong. Underrepresented. |
| **Savannah** | GA | Historic, food culture strong, locals protective of non-tourist layer. |
| **Charlottesville** | VA | Wine trail, UVA culture, strong local food scene. Active local community. |
| **Traverse City** | MI | Cherry country, wine, Lake Michigan. Obsessive local food and outdoor community. Seasonal but manageable. |
| **Saugatuck** | MI | Southwest Michigan beach and food culture. Small but locally documented obsessively. |
| **Eureka Springs** | AR | Quirky Ozarks arts town, underrepresented, passionate local community. |
| **Bentonville** | AR | Walmart HQ pivot to arts capital. Crystal Bridges, mountain biking, emerging food scene. Locals document the transformation actively. |
| **Ogden** | UT | Best kept secret in Utah per local consensus. Outdoor company hub, Snow Basin proximity. Underrepresented vs. SLC and Park City. |
| **Buena Vista** | CO | Arkansas River rafting, mountain town, hip food and music scene. Locals know it; aggregators don't. |
| **Glenwood Springs** | CO | Hot springs, adventure, Hanging Lake. Smaller than Aspen, better local intel. |
| **Ketchum/Sun Valley** | ID | Ski and outdoor culture, Hemingway legacy, strong local food scene for its size. |
| **Whitefish** | MT | Glacier National Park gateway with its own strong local identity. |
| **Steamboat Springs** | CO | Cowboy culture meets ski culture. Locals have strong opinions about what's authentic. |

---

## Tier 3 — International (Expat/Nomad Community with Dense English-Language Local Intel)

These qualify because they have large English-writing communities who document them obsessively — often *better* than the local language sources.

| City | Country | Why It Qualifies |
|---|---|---|
| **Chiang Mai** | Thailand | The original nomad hub. Enormous English-language documentation from expats who've lived there for years, not tourists passing through. ThaiVisa forums, Nomad List, r/chiangmai — all dense with local intel. |
| **Tbilisi** | Georgia | Rapidly growing expat community, East-meets-West character, ancient wine culture, extraordinary food. English-language documentation growing fast and honest. |
| **Medellín** | Colombia | Transformed city, massive expat community, strong local food and nightlife scene. r/medellin and expat forums produce detailed insider content. |
| **Oaxaca** | Mexico | Food capital of Mexico, mezcal culture, indigenous art. Expat food writers and culinary tourists produce extraordinary local content. High tourist/local divergence despite tourist volume. |
| **San Miguel de Allende** | Mexico | Large expat community, strong arts culture, well-documented by long-term residents. |
| **Porto** | Portugal | Smaller than Lisbon, richer local character. Wine culture, local food, expat community growing. Locals vocal about tourism impact — useful divergence signal. |
| **Lisbon** | Portugal | Already tourist-heavy but local/expat documentation of authentic layer is strong. Worth it for the divergence gap. |
| **Tallinn** | Estonia | Medieval city, growing nomad hub, English-language expat community produces good local intel. |
| **Ljubljana** | Slovenia | Under the radar, strong local food and wine culture, small but tight community. |
| **Kotor** | Montenegro | Bay of Kotor, described as a UNESCO World Heritage site that still flies under the radar. Growing nomad winter base. |
| **Hội An** | Vietnam | Expat food and culture community is extensive. Tailor culture, local cuisine, strong English documentation. |
| **Penang** | Malaysia | Street food capital of Southeast Asia, Chinese heritage, obsessive food documentation from locals and long-term expats. |
| **Kyoto** | Japan | Not underrated globally, but the local/tourist divergence is enormous. Tabelog and Japanese local sources surface a completely different city than what tourists see. Corpus access depends on Japanese-language ingestion capability. |
| **Osaka** | Japan | Same as Kyoto — Dotonbori is tourist, the rest of the city is a different world. |

---

## Corpus Scoring Rubric (For Prioritizing Unseeded Cities)

When evaluating a new city for seeding priority, score it on these dimensions:

| Dimension | Signal | Weight |
|---|---|---|
| Subreddit health | Subscribers + posts-per-week + locally-oriented (not tourist Q&A) | High |
| Forum depth | Expat forums, activity-specific forums (MTB, climbing, fishing) | High |
| Atlas Obscura density | Entries per 100k population | Medium |
| Local food blog presence | Independent food writers with 2+ years of content | Medium |
| Tourist/local divergence proxy | Ratio of Yelp top-10 vs. Reddit top-10 overlap | High |
| Seasonality complexity | How much the city changes across seasons | Low (penalty) |
| Aggregator saturation | Is the city already dominated by SEO listicles? | High (penalty) |

---

## What We Are Explicitly Not Doing

- **Pure aggregator monocultures** — NYC Midtown, SF Union Square, Chicago Mag Mile. The parts of famous cities where Google already wins completely. We cover these cities at the neighborhood level, not as a generic city guide.
- **Pure beach resort towns** (Cancun, Myrtle Beach, Panama City Beach) — tourist monoculture with no local layer worth surfacing. Different from coastal cities that have real local communities underneath.
- **Small towns with no English-language community** — corpus too thin for meaningful vibe embeddings even if the place is wonderful.
- **Pre-seeding international cities speculatively** — demand-driven only. Seed when users request it.

### The NYC/SF Position

We don't index "New York" or "San Francisco" as monolithic cities. We index **neighborhoods within them** where the local/tourist divergence is meaningful — Flushing, Sunset Park, Bed-Stuy, the Mission, Outer Richmond, Excelsior. A user planning a trip to NYC who wants what locals actually do will find that. A user who wants the standard tourist checklist already has Google for that.

---

*Cities are seeded on-demand through admin tooling, not pre-loaded speculatively. This list defines priority order when demand triggers seeding, not a pre-seeding roadmap.*
