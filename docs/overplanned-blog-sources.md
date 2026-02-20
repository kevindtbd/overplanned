# Overplanned — Blog & Editorial Source Registry

*February 2026 · Internal*
*Owner: Kevin — additions require sign-off. Authority scores reviewed quarterly.*

The seed list is the foundation of Pipeline C's content advantage. The goal is not volume — it's independence. Ten sources that independently name the same venue is signal. One source repeated ten times is noise. Every source here was evaluated against the authority model: temporal depth, specificity, low affiliate density, local authorship proximity, and cross-reference frequency with known-good platforms.

**SEO spam ratio in travel content is ~85:15 junk:signal.** This list represents the 15. Do not expand it by scraping discovery — expand it only when a source is cited by 3+ existing seeds or appears independently in Reddit recommendations.

---

## Authority Score Model (quick reference)

| Signal | Weight |
|---|---|
| Temporal depth (posts span 3+ years in same region) | 0.30 |
| Specificity (names streets, timing, seasonal details) | 0.25 |
| Local authorship / residency proximity | 0.20 |
| Cross-reference frequency with known-good sources | 0.15 |
| Affiliate link density (penalty) | −0.10 |

Scores run 0–1. Sources below 0.60 are not added regardless of name recognition. A high-profile source with heavy affiliate content (Thrillist, most "best of" listicles) scores low and stays out.

---

## US Cities

### Food & Dining (highest signal for restaurant ActivityNodes)

**The Infatuation** · `infatuation.com` · Authority: 0.91
Coverage: NYC, LA, Chicago, SF, Miami, DC, Seattle, Austin, Boston, Portland, Denver, Vegas, Atlanta, Houston, Philadelphia. Expanding. RSS available per city.
Why it's in: explicitly no affiliate links (stated policy), reviews name specific dishes and best times of day, calls out overrated explicitly ("skip it"), resident-authored teams per city. Scores extremely well on specificity and local proximity. The overrated signal alone justifies inclusion.
Extract: vibe tags, price signal, time-of-day recommendation, overrated flag, dish-level specificity.

**Eater** (city editions) · `eater.com` · Authority: 0.82
Coverage: NYC, LA, Chicago, SF, Miami, DC, Seattle, Austin, Boston, Portland, Denver, Vegas, Atlanta, Houston, Philadelphia, New Orleans + 20+ more US cities via Vox Media network.
Why it's in: editorial heatmaps are high-specificity, local editors per city, "where to eat right now" content has strong recency signal, explicit "overrated" and "underrated" editorial content.
Penalty: some affiliate links in hotel/travel content — apply penalty only to non-food content. Food reviews are clean.
Extract: heatmap mentions, neighborhood clustering, recency signal (heatmap date), overrated/underrated flags.

**Grub Street (NY Mag)** · `grubstreet.com` · Authority: 0.88
Coverage: NYC primary, national food news secondary.
Why it's in: zero affiliate model (NY Mag editorial), extremely high specificity (dish-level, table-level), Platt and team are resident NYC writers. The "best of" content here is substantively different from SEO farms — it names specific items and explains why.
Extract: dish-level signals, NYC neighborhood clustering, critic consensus signals.

**Bon Appétit city guides** · `bonappetit.com/travel` · Authority: 0.74
Coverage: 40+ global cities, US-heavy.
Why it's in: BA staff are food professionals, guides have genuine local research, less affiliate-dense than competitors. Specificity is good — names neighborhoods and specific items.
Penalty: parent company (Condé Nast) has some affiliate relationships — apply 0.10 affiliate penalty. Still above threshold.
Extract: neighborhood-level clustering, vibe tags (BA has a strong aesthetic voice that maps cleanly to our vocabulary).

**Tasting Table** · `tastingtable.com` · Authority: 0.71
Coverage: national, US city guides.
Why it's in: editorial food content with genuine research, minimal affiliate density in city guide content specifically.
Note: decline in editorial quality post-2022 acquisitions — apply recency filter, posts before 2022 weighted down.

---

### General Travel & Lifestyle (activity ActivityNodes beyond food)

**Curbed** (NY Mag) · `curbed.com` · Authority: 0.81
Coverage: NYC, LA, SF, Chicago, DC, and national urban coverage.
Why it's in: neighborhood-level specificity that no other source matches, resident-authored, zero affiliate model. "Best neighborhoods" and urban exploration content maps directly to our `urban-exploration` and `hidden-gem` tags.
Extract: neighborhood characterization, `hidden-gem` signals, `locals-only` signals, urban texture.

**The Stranger** (Seattle) · `thestranger.com` · Authority: 0.83
Coverage: Seattle primary.
Why it's in: alt-weekly editorial, zero affiliate, brutally honest, deeply local. The exact profile we want for a specific city. Staff are Seattle residents.
Note: model for what we want per city — find equivalents (Village Voice archive, LA Weekly archive, Chicago Reader, SF Weekly archive).

**City-specific alt-weeklies** (general category) · Authority: 0.78–0.85
The alt-weekly format — independent editorial, resident staff, no affiliate model — is the closest US analog to the local Japanese forum signal.
Seed list:
- Chicago Reader · `chicagoreader.com`
- LA Weekly · `laweekly.com` (quality declined post-2017, apply recency filter aggressively)
- SF Weekly archive · use archive.org for pre-2020 content
- Boston Phoenix archive · `archive.org`
- Village Voice archive · high-specificity NYC content pre-2018
- Austin Chronicle · `austinchronicle.com` (still active, high quality)
- Portland Mercury · `portlandmercury.com`
- Nashville Scene · `nashvillescene.com`

---

## Global / International

### Japan

**Tokyo Cheapo** · `tokyocheapo.com` · Authority: 0.82
Why it's in: resident-authored (expats long-term Tokyo), strong specificity, covers non-food activity nodes well, updated actively.

**LiveJapan** · `livejapan.com/en` · Authority: 0.79
Why it's in: bilingual editorial with genuine local sourcing, covers seasonal timing signals well.

**Time Out Tokyo** · `timeout.com/tokyo` · Authority: 0.76
Why it's in: local editorial team, covers nightlife and arts well (fills gaps Tabelog doesn't touch).
Penalty: Timeout global has some affiliate content — Tokyo edition is cleaner. Apply 0.05 penalty.

**Tokyo Weekender** · `tokyoweekender.com` · Authority: 0.77
Why it's in: expat-local hybrid voice, high specificity on neighborhood texture, covers things Tabelog doesn't (non-food experiences, art, culture).

**Metropolis Japan** · `metropolisjapan.com` · Authority: 0.72
Why it's in: long-running (25+ years), genuine local authorship, covers cultural experiences beyond food well.

**Savvy Tokyo** · `savvytokyo.com` · Authority: 0.70
Why it's in: women-focused travel content with genuine local residency, strong on neighborhood-level specificity.

**Deep Kyoto** · `deepkyoto.com` · Authority: 0.85
Why it's in: single-author long-form content, resident author (Mark Robinson, 20+ years Kyoto), extreme specificity, zero affiliate. Exactly the profile we want — authority earned through depth, not SEO.

**Japan Talk** · `japantalk.org` · Authority: 0.68
Why it's in: covers lesser-known regions, rural specificity that no other English source has. Lower authority but fills coverage gaps.

---

### Korea

**10 Magazine Korea** · `10mag.com` · Authority: 0.74
Why it's in: Seoul-based editorial, English-language local coverage, covers arts/culture/nightlife well.

**Korea Tourism Organization official blog** · `english.visitkorea.or.kr` · Authority: 0.62
Note: government tourism source — high coverage, lower authenticity signal. Apply tourist_score adjustment (high-tourist content by definition). Use for structural data (hours, location, category) not vibe signal.

**Groove Korea** · `groovekorea.com` · Authority: 0.71
Why it's in: expat-local editorial, strong Seoul neighborhood coverage.

---

### Southeast Asia

**Coconuts** (city editions) · `coconuts.co` · Authority: 0.78
Coverage: Bangkok, Singapore, Jakarta, Bali, Manila, Saigon.
Why it's in: local editorial teams per city, resident journalists, covers urban texture and nightlife well, strong overrated signal (explicitly calls out tourist traps).

**Time Out Singapore / Bangkok / KL** · Authority: 0.72–0.74
Local editorial teams in each market. Same Timeout affiliate caveat — apply 0.05 penalty.

**Migrationology** · `migrationology.com` · Authority: 0.83
Why it's in: Mark Wiens — SE Asia food authority, 15+ years content, extreme specificity (dish-level, stall-level), zero affiliate in food content. Covers Bangkok particularly well.
Extract: street food signals, `street-food` and `locals-only` vibe tags, stall-level specificity.

**Eating Asia** · `eatingasia.typepad.com` · Authority: 0.86
Why it's in: Robyn Eckhardt — one of the most credible food writers in SE Asia, resident-adjacent, zero affiliate model. Long-running, deep specificity.
Note: lower posting frequency post-2019 — use archive for signal depth, weight recent posts higher.

---

### Europe

**Hidden Europe** · `hiddeneurope.co.uk` · Authority: 0.89
Why it's in: printed magazine + web, hyper-specific (covers trains, slow travel, lesser-known regions), zero affiliate, strong `slow-burn` and `off-the-beaten-path` signal.
Extract: `hidden-gem`, `offbeat`, `slow-burn` tags, temporal depth signals (many posts cover obscure seasonal events).

**Messy Nessy Chic** · `messychic.com` · Authority: 0.84
Coverage: Paris-centric but covers Europe broadly.
Why it's in: quirky, highly specific (covers hidden rooms, unusual history), resident Paris author, zero affiliate. Strong `offbeat` and `deep-history` signal.

**The Spaces** · `thespaces.com` · Authority: 0.77
Why it's in: design/architecture lens on cities — covers spaces other sources ignore. Strong `contemporary-culture` and `minimalist` aesthetic signal.

**Atlas Obscura** · `atlasobscura.com` · Authority: 0.80 (already Tier 2 source — treat blog content as Tier 1)
The editorial blog content (distinct from the user-submitted database) has genuine research and local sourcing. Covers offbeat and unusual experiences exclusively — no overlap with mainstream sources.

**Spotted by Locals** · `spottedbylocals.com` · Authority: 0.88
Why it's in: structural premise is correct — only locals can submit, vetted by city editors. Amsterdam, Barcelona, Berlin, Brussels, Copenhagen, Florence, Hamburg, Istanbul, Lisbon, London, Lyon, Madrid, Marseille, Milan, Naples, Nice, Paris, Porto, Prague, Rome, Rotterdam, Seville, Stockholm, Valencia, Vienna, Zurich.
This is the closest European analog to Tabelog — structurally local.
Extract: `locals-only`, `hidden-gem`, neighborhood specificity, `locals-routine`.

**Mr & Mrs Smith** · `mrandmrssmith.com` · Authority: 0.69
Coverage: global hotels + experiences.
Why it's in: high-end editorial with genuine curation, `splurge-worthy` and `date-night` signal. Lower authority due to commercial relationships with properties — apply 0.10 affiliate penalty. Still above threshold for luxury activity segment.

**Monocle travel guides** · `monocle.com/travel` · Authority: 0.87
Why it's in: Monocle's city guides are the gold standard for quality signal — independently researched, no affiliate model, strong aesthetic voice, covers retail/culture/food in an integrated way that maps well to our vibe vocabulary. Their "quality of life" framing aligns directly with the Overplanned product philosophy.
Penalty: paywalled. Use Monocle's free content (Monocle 24 radio transcripts, free web content) and their annual Quality of Life supplement where accessible.

---

### Latin America

**Matador Network** (curated subset) · `matadornetwork.com` · Authority: 0.64
Note: quality is highly variable — heavy SEO content mixed with genuinely good local-authored pieces. Filter aggressively: only posts with bylined local authors, 1500+ words, 3+ years old (proven staying power). Apply 0.10 affiliate penalty.

**Gastronomika** (Mexico/Colombia) · regional food editorial · Authority: 0.73
Coverage: Mexico City, Medellín, Bogotá, Lima, Buenos Aires.
Why it's in: Spanish-language food editorial with genuine local authorship.
Note: requires DeepL translation pass in extraction pipeline.

**Cultura Colectiva** · `culturacolectiva.com` · Authority: 0.70
Coverage: Mexico City primary.
Why it's in: local Mexican editorial, covers arts/culture/neighborhoods well.

---

## Sources Explicitly Excluded and Why

**TripAdvisor blog content** — algorithmically generated, affiliate-heavy, zero editorial voice. Not a source.

**Thrillist** — affiliate density is disqualifying (0.35+ affiliate ratio on most city content). Strong brand, weak signal. Excluded.

**Lonely Planet blog** — publisher has shifted to affiliate-first model. Guide books retain value as structural data (hours, categories) but blog content is SEO. Use LP as metadata source only, never as vibe signal source.

**Nomadic Matt** — authority score 0.58. Single-perspective budget travel voice, high affiliate density, broad coverage at the expense of specificity. Excluded.

**The Points Guy / The Broke Backpacker** — affiliate models disqualify both. These exist to convert, not inform.

**Culture Trip** — collapsed editorially post-Series B. Content is now AI-assisted SEO. Explicitly excluded.

**Fodor's / Frommer's blog content** — SEO content, no local authorship. Use as structural metadata only.

---

## Expansion Criteria

A source can be added to the seed list if it meets two of three criteria:
1. Cited independently by 3+ existing seed sources (cross-reference signal)
2. Named by 5+ Reddit posts in regional subreddits as a trusted recommendation (community validation)
3. Manually evaluated by Kevin against the authority model and scores ≥ 0.70

Sources discovered via Reddit recommendation are the highest-quality discovery channel. When r/JapanTravel users repeatedly cite a specific blog, that's the authority model working in real time.

---

## Crawl Cadence

| Content type | Crawl frequency | Rationale |
|---|---|---|
| Active editorial (Infatuation, Eater) | Weekly new posts | High recency value |
| Established archives (Deep Kyoto, Eating Asia) | Monthly | Low posting frequency, archive stable |
| Alt-weekly (The Stranger, Austin Chronicle) | Weekly | Event/nightlife content has short freshness window |
| Monocle, Hidden Europe | Quarterly | Low posting frequency, content ages well |
| Archived sources (Village Voice, SF Weekly) | One-time bulk import | Historical signal only |

RSS-first wherever available. Full-site crawl only where RSS is absent or truncated. Rate limit all crawlers to 1 request/2 seconds. Respect robots.txt. Store raw content hash on first fetch — skip re-processing on unchanged content (SHA256 check before any LLM extraction).

---

*Overplanned Internal · February 2026*
