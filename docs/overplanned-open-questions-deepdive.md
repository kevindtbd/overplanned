# Overplanned â€” Open Questions Deep Dive
*Research Â· Brainstorm Â· Architecture Â· Agent Review*
*Covers all unresolved items from the build list and design philosophy docs*

---

## How to Use This Doc

Each open question gets four sections:
- **Research** â€” what's known, reference patterns, relevant prior art
- **Brainstorm** â€” options to consider, tradeoffs, directional thinking
- **Decision / Architecture** â€” what we're committing to (fill in per session)
- **Agent Review** â€” security, devops, UX/product critique of each option

---

---

# 1. Energy Curve Calibration

## Research

The energy curve is one of the most architecturally interesting problems in the whole system â€” it's not just "morning person vs. night owl." It's a multi-dimensional fatigue model across a trip arc:

- **Intraday energy**: people flag mid-afternoon (post-lunch dip is universal, ~2â€“4pm)
- **Interday accumulation**: day 3 of a packed trip hits differently than day 1
- **Activity-specific drain**: a temple visit is light; a 4-hour hike is heavy; a long dinner is medium but mentally restorative
- **Novelty fatigue**: decision fatigue from too many new experiences compounding
- **Weather/climate interaction**: heat drains energy; jet lag offsets the curve by hours

Prior art:
- Spotify Daylist uses time-of-day + day-of-week as primary context axes. Simple but effective â€” "your monday morning energy" vs. "your friday evening energy"
- Fitbit/health apps track subjective fatigue via sleep quality + resting HR â€” proxies we could someday tap via HealthKit/Google Fit
- Package tour operators empirically calibrate this: "never book a major site on day 1 (jet lag), peak cultural experience on day 2â€“3, leisure day 4â€“5, shopping day 6 (decision fatigue sets in)"

The existing architecture has `energy_curve_model` on `TripNode` but leaves calibration unspecified. The `MAX_PIVOT_DEPTH` context drift guard partially handles it â€” but that's a guardrail, not a model.

## Brainstorm

**Option A: Heuristic-first, ML-refined later**
Define a default energy curve template per trip_length + trip_type. Apply simple decay functions. Let behavioral signals (pivot accept/dismiss, pace of activity completion, mood signal frequency) update the curve. This is the right move for v1 â€” you don't have training data yet.

Default templates:
- `weekend_getaway` (2â€“3 days): high-high-medium. No meaningful decay.
- `one_week` (5â€“7 days): medium-high-high-medium-low-medium-low. Classic arc.
- `two_week` (8â€“14 days): two sub-arcs separated by a midpoint rest day.
- `open_ended` (14+ days): slow burn. Low initial pace assumption, user adjusts up.

**Option B: User-declared energy style at onboarding**
"Are you a go-hard-rest-hard traveler or a steady-pace traveler?" This is low friction and gives immediate calibration signal before any trip data. Maps to a `pace_burst_vs_steady` dimension. Risk: self-reporting bias (people say burst, actually want steady).

**Option C: Activity cost model**
Assign an energy cost to each `ActivityNode` category:
```
energy_cost = {
  'multi-hour-hike': 0.8,
  'museum': 0.35,
  'restaurant': 0.1,       // restorative, actually negative
  'walking-tour': 0.45,
  'beach-lounge': -0.2,    // recovery
  'theme-park': 0.7,
  'bar-crawl': 0.3,        // medium cost, late-night timing multiplier
}
```
Itinerary generator sums daily energy cost, enforces a daily budget per day of trip. This is deterministic and explainable.

**Option D: GPS + time-spent as passive calibration**
If user spent 45 minutes at a venue that was slotted for 2 hours, that's a signal. If they stayed 2.5 hours, that's engagement/energy. Over time, this calibrates the energy cost model per user type. This is the richest signal but requires real usage to accumulate.

**Recommended approach**: A + C immediately. B as part of onboarding. D as a long-term refinement layer.

## Decision / Architecture

*TBD â€” fill in after design session*

```
EnergyModel {
  trip_template: 'one_week' | 'weekend' | 'two_week' | 'open_ended'
  daily_budget: float[]           // per-day energy budget (0â€“1 scale)
  activity_cost_map: {}           // category â†’ energy cost
  remaining_budget: float         // current day, updates as slots added
  pace_style: 'burst' | 'steady'  // from onboarding signal
  jet_lag_offset_hours: float     // from origin timezone delta
  weather_drain_modifier: float   // from weather API
}
```

## Agent Review

**Security / Privacy**: Energy data is passive behavioral data. GPS-derived time-spent is implicit location tracking â€” must be session-scoped, not persisted beyond the active trip. Never transmit raw dwell time without aggregation.

**DevOps**: Energy curve recomputation is cheap (arithmetic). Should happen client-side or edge-side, not in a backend roundtrip. Pre-compute curve at trip generation; update as day progresses. No ML inference needed here until calibration phase.

**UX/Product**: The energy bar in the existing UI is a strong visual â€” but the current design shows it as informational. The bigger opportunity: make it *actionable*. When daily energy budget is low, the system proactively surfaces break slots or lower-cost alternatives without the user asking. The bar is a promise. The system has to keep it. Also: never show a raw percentage. "Light afternoon ahead" beats "42% energy remaining."

---

---

# 2. Blogger Authority Model

## Research

The Pipeline C architecture handles major review platforms well (Tabelog, Dianping, Naver) but the design doc calls out travel bloggers as a distinct content type â€” curated, region-specific, high-signal for hidden gems â€” without defining the authority model.

The problem: travel blogs span a huge quality range, from SEO spam farms ("20 best things to do in Kyoto!") to deeply credible long-form writers who've spent years in a city. The difference between them matters enormously for our use case.

Signals that distinguish credible bloggers from SEO content:
- **Citation velocity**: is this blog cited by other credible blogs or forums?
- **Temporal depth**: posts span multiple years in the same region, not single-trip coverage
- **Specificity**: mentions specific streets, seasonal events, insider timing (not just "go to X")
- **Cross-referencing**: the same hidden gem appears independently on multiple bloggers = high confidence signal
- **Language**: writes in the local language or clearly local-resident authored content
- **No affiliate link density**: "best hotels" posts with 20 affiliate links = low authority

Prior art:
- Google's PageRank concept applied to content: link authority flows from credible sources
- Academic citation network analysis: h-index style scoring for travel content
- Reddit karma + age-of-account as proxy for trustworthiness â€” not perfect but directional

## Brainstorm

**Option A: Curated seed list, human-maintained**
Start with a manually curated list of ~50â€“100 high-quality travel bloggers per major region. Crawl only those. Expand via recommendation (if blogger X links to blogger Y approvingly, evaluate Y). This is pragmatic for v1 and avoids the noise problem entirely.

**Option B: Authority score computed from signals**
Build a `BloggerAuthorityScore` model with features:
- Domain age + posting frequency (consistency signal)
- Average post length and specificity (depth signal)
- Cross-reference frequency with known-good sources
- Inbound links from forums (reddit, local forums)
- Local language usage ratio

**Option C: Use the activity cross-reference as the signal**
Don't try to score bloggers directly. Instead: when a specific venue/activity appears in both a high-authority review platform AND multiple independent blog posts, that cross-reference itself is the signal. Blogger quality is irrelevant if the convergence pattern is strong. This sidesteps the authority modeling problem entirely.

**Recommended**: A + C. Curated seed list for volume and precision. Cross-reference convergence as the quality signal for any given recommendation. Don't build a general blogger ranking system â€” it's a complexity trap.

## Decision / Architecture

```
BlogSource {
  domain: string
  region_focus: string[]
  language: string
  seed_status: 'curated' | 'discovered'
  discovery_source: string     // which curated source linked here
  post_count_indexed: int
  last_crawled: timestamp
  avg_specificity_score: float // computed from mention density per post
}

CrossReferenceSignal {
  activity_id: string
  blog_mentions: int
  forum_mentions: int
  review_platform_mentions: int
  independent_source_count: int   // key metric: how many distinct sources
  convergence_score: float        // weighted by source independence
}
```

## Agent Review

**Security**: RSS feed crawling is relatively safe, but full-site crawling needs rate limiting and robots.txt compliance. Blog sites may have ToS restrictions. For curated seed list: get explicit permission or ensure crawl is within fair use scope.

**DevOps**: Blog content changes infrequently â€” crawl cadence can be monthly for established posts, weekly for recent posts. Storage is cheap. The cross-reference computation is a batch job, not real-time. Run after each Pipeline C refresh cycle.

**UX/Product**: The "via Tabelog, 847 local reviews" attribution in the activity card is already doing the right work. For blog-sourced signals, attribution matters even more â€” "mentioned by 3 independent local food writers" is a much stronger trust signal than any badge. Don't invent a new UI pattern; extend the existing source attribution line.

---

---

# 3. Onboarding / Persona Cold Start UX

## Research

The architecture has the cold start mechanism well-defined (preset templates â†’ tag selection â†’ behavioral graph seeding). The design philosophy doc says it "should feel like planning a trip, not filling out a profile." That's the right instinct but needs unpacking.

The core tension: the system needs structured data (persona dimension values) but users respond to narrative/emotional framing, not taxonomies. 

Reference patterns:
- **Spotify's genre quiz at signup**: fun, fast, never feels like a form. But Spotify has the advantage that music taste is immediately fun to express. Travel preferences are more situational.
- **Airbnb's "what kind of trip?" onboarding**: destination-first, filters-second. Works because destination is the primary unit of excitement.
- **Headspace's onboarding**: goal-framed. "Why are you here?" before "tell me about yourself." Outcome-oriented entry.
- **Duolingo**: makes the product itself feel like the onboarding. You're not filling out a profile â€” you're doing the first lesson.

The Duolingo model is closest to the right approach: make the first trip planning session the onboarding. The tag selection IS the first act of planning. 

## Brainstorm

**Frame 1: "What sounds good right now?"**
Not "describe your travel style." Not "which type of traveler are you." The entry is aspirational and present-tense: show 6â€“8 visually rich scenario cards. "Late nights and street food in a city that never sleeps." "Slow mornings, good coffee, a few perfect restaurants." "Hike something hard, earn a great view." User taps 1â€“3. These map to preset persona seeds.

**Frame 2: Destination-first**
"Where are you thinking?" is the most natural first question. Skip persona setup entirely on first session â€” go straight to destination input. Collect persona signal implicitly as the user browses and builds. First trip = onboarding.

**Frame 3: Trip context-first**
"Who's going with you?" before anything else. Solo / partner / small group / big group is the highest-variance variable in the whole system and it changes everything downstream. Getting this first is architecturally sound. It also feels natural â€” it's the first thing anyone asks when planning a trip.

**Frame 4: Progressive disclosure**
Don't ask anything upfront. Show a rough first itinerary (using destination priors â€” what most people who go to Tokyo enjoy). Let user modify slots. Every modification is onboarding data. Surface the tag cloud as an optional "tune this" action, not a required step.

**Recommended**: Frame 3 â†’ Frame 1 â†’ Frame 4 in sequence.
- "Who's going?" (group structure, group size)
- "What sounds good?" (scenario cards â†’ preset seed)
- Let first browse/modification session do the rest

This is a 2-tap onboarding with implicit continuation. Never asks for age, home city, or demographic data.

## Decision / Architecture

Onboarding event schema:
```
OnboardingSession {
  group_structure: 'solo' | 'couple' | 'small_group' | 'large_group'
  group_size: int
  preset_selected: PresetTemplate.id
  tags_selected: string[]
  destination_intent: string | null   // may be null at onboarding
  time_to_complete_ms: number         // signal: fast = decisive, slow = uncertain
}
```

Tag cloud design rules:
- Max 20 tags visible at once (cognitively manageable)
- Tags are activity descriptors, NOT personality adjectives ("street food markets" not "adventurous")
- No tag is wrong. No validation. No required minimum.
- Selected tags animate in a satisfying way â€” this is the "planning feeling"

## Agent Review

**Security**: No PII collected at onboarding. Group structure and tags are preference data, not identity data. Don't associate with device ID until user creates an account â€” anonymous session first, account creation on first trip save.

**DevOps**: Onboarding data is tiny. Can be held client-side until account creation, then synced. No backend call needed until "save my trip" moment. This also means onboarding works offline.

**UX/Product**: The biggest risk is over-asking. Every extra question is a drop-off risk. The scenario card approach (Frame 1) must be visually stunning â€” if the cards feel generic, users won't engage. Each card needs a real photograph, one evocative sentence, no bullet points. The tag cloud needs to feel like a toy, not a form. Tags should pre-select based on the scenario card choice â€” user arrives at the tag cloud already partially filled in, not blank.

---

---

# 4. Overrated Signal â€” Design Decision

## Research

The architecture defines the `overrated_score` and `tourist_trap_confidence` computations clearly. The open question from the design philosophy doc is: how do we surface this in the UI without being preachy or condescending?

The problem: "this place is overrated" is a judgment that can feel like the app is showing off or being contrarian. The places that get flagged are often beloved by millions of people. If we tell a user "the Eiffel Tower is a tourist trap," we look stupid. If we never surface the signal, we've wasted the differentiator.

The insight from the design philosophy doc: "Source attribution probably does more work than any explicit flag: 'via Tabelog, 847 local reviews' says everything without saying anything."

This is the right direction. The overrated signal should be implicit in the language, not explicit as a label.

## Brainstorm

**Option A: Explicit badge â€” "tourist trap" or "popular but..."**
High contrast. Clear. Users understand immediately. Risk: alienating, preachy, sometimes wrong (some popular places are genuinely good). Also creates reputational risk if a well-loved venue is flagged incorrectly.

**Option B: Hidden gem positive framing only**
Instead of flagging overrated places, only positively surface hidden gems. "87% local crowd." "Less than 5% of visitors to Tokyo find this." This is the same information inverted. It rewards discovery rather than warning about disappointment. Much warmer.

**Option C: Source attribution as the signal**
The activity card's source line does the work:
- High overrated_score: "via TripAdvisor, 12,000 reviews" â€” no local source badge, tourist_score implied
- Low overrated_score: "via Tabelog, 847 reviews" â€” local source badge, trust signal
The user reads the difference. The system never has to say "overrated."

**Option D: Slot language carries the signal**
The LLM narrative layer uses different language for high vs. low tourist_score venues:
- Low tourist score: "almost nobody from outside the neighborhood knows this place"
- High tourist score: "iconic for a reason â€” worth it despite the crowds, go at 8am"
- High overrated signal: "the lines aren't worth it â€” here's what locals go to instead" (only shown as an alternative, never as a primary)

**Recommended**: B + C + D together. Hidden gem positive framing, source attribution as implicit signal, and LLM narrative language that's honest without being condescending. Never an "overrated" badge.

## Decision / Architecture

```
ActivityCard display logic:
  if tourist_score < 0.3 AND source.local_ratio > 0.6:
    â†’ show "local favorite" badge
    â†’ source line: "via [local platform], [N] local reviews"
  
  if tourist_score > 0.7 AND overrated_score < 0.2:
    â†’ show no badge (it's popular AND good)
    â†’ source line: "iconic Â· [N] reviews across sources"
  
  if tourist_score > 0.6 AND overrated_score > 0.3:
    â†’ do NOT surface as primary recommendation
    â†’ may appear as a "skip this, try instead" in pivot alternatives
    â†’ never explicitly labeled "overrated"
```

## Agent Review

**Security**: No issues. This is display logic only.

**DevOps**: The overrated_score is pre-computed in Pipeline C â€” no real-time inference needed at display time. The display logic is client-side conditional. Keep it simple.

**UX/Product**: Option D (LLM narrative language) is where the product voice is most at risk. "The lines aren't worth it" is a strong claim that can backfire â€” if a user ignores it and has a great time, they'll distrust the system. Better default: say what locals do instead of dismissing what tourists do. "Locals skip the queue and grab these instead" is warmer and more actionable than "avoid this." The hidden gem signal should feel like a secret being shared, not a warning being issued.

---

---

# 5. Discovery / Pre-Trip Browse Surface

## Research

The design philosophy doc flags this as "on hold pending brand direction" but describes it as "the emotionally crucial opening moment." This is actually the highest-stakes screen in the product â€” it's where inspiration happens, where users decide whether to trust the app, and where word-of-mouth is earned ("I just opened this app and it somehow knew I'd want to go to Oaxaca").

This is the hardest screen to build because it requires the most data (personalization without a destination), the most emotional design work (inspiration is fragile), and the most alignment with brand voice.

Reference patterns:
- **Pinterest**: infinite scroll of highly visual content, curated by taste graph. The model for browsing without intention.
- **Airbnb Experiences**: editorial-warm, destination agnostic, activity-first discovery
- **Google Trips (RIP)**: destination cards with personalized travel intel. The closest prior product. Failed because it had no social layer and no pre-trip inspiration surface.
- **Sora / AI-generated travel content**: immersive short video of destinations. The emotional register this should aim for, even in still photography.
- **Monocle Travel Guide**: curated, opinionated, specific. The editorial tone.

The core insight: discovery is not browsing a catalog. It's encountering something that makes you think "wait, where is that?" â€” and then wanting to go.

## Brainstorm

**Frame 1: Destination-first card feed**
Full-bleed destination cards, each with a one-line hook. "Kyoto in November when the maples turn." "Oaxaca â€” four hours from New York, feels like a different century." User swipes through, taps to explore. Maps to Pinterest model.

**Frame 2: Activity-first, destination-agnostic**
"You'd like this bar in Lisbon." "This hike in Hokkaido." Not "here are cities to visit" but "here are specific moments that fit how you travel." This is the persona differentiator â€” no other travel app does this. Risk: requires enough persona signal to work; cold start problem is acute here.

**Frame 3: Editorial moments**
Curated "this week in..." type content. Not algorithmic. Human-curated, regularly updated. Low-friction to produce (one editor, one post per week per region). Signals: seasonal events, recently discovered gems from Pipeline C, local happenings. This anchors the discovery surface in time and makes it feel alive.

**Frame 4: Trip report social layer**
Other users' past trips (anonymized, opted-in) as discovery content. "A solo traveler who travels like you just got back from Porto â€” here's what they did." This is the most compelling but requires a user base to work. Not a v1 feature.

**Recommended**: Frame 3 as the v1 discovery surface â€” editorial-led, low algorithmic pressure, easy to produce with one person. Frame 1 as the browsing mode. Frame 2 as the "recommended for you" layer that activates after a user has behavioral history. Frame 4 as a future social layer.

## Decision / Architecture

Discovery surface data requirements:
```
DiscoveryCard {
  type: 'destination' | 'activity' | 'editorial'
  destination: string | null
  headline: string                  // one evocative sentence
  subhead: string | null            // one optional supporting detail
  photo: Unsplash reference         // full-bleed, warm, specific
  persona_affinity: float           // how well this matches current user
  season_relevance: float           // based on current month + destination
  editorial_tag: string | null      // 'local pick' | 'in season' | 'trending locally'
}
```

Recommendation ranking for discovery:
- Pre-persona (cold start): rank by season relevance + editorial weight
- Post-persona: rank by persona_affinity Ã— season_relevance Ã— novelty

## Agent Review

**Security**: Discovery surface has a prompt injection risk via editorial content â€” if editorial copy is partially LLM-generated, ensure it's generated from structured data, not from user-submitted content.

**DevOps**: Discovery content can be heavily cached. Editorial cards are static (change once per week). Persona-ranked ordering is the only dynamic element â€” compute ranking server-side per user, cache for session. Pre-warm discovery cache for DAU users nightly.

**UX/Product**: "On hold pending brand direction" is the right call â€” this surface defines the brand more than anything else. The photography selection is 80% of the work. One wrong photo (corporate-looking, stock-generic, not the specific moment) kills the vibe. Must establish a photo curation standard before building: which Unsplash collections, what framing (people or no people?), what time of day. Also: this screen should never have a search bar visible by default. Search kills the discovery mode. Search is for when you know what you want â€” discovery is for when you don't.

---

---

# 6. Motion & Feedback Design

## Research

The design philosophy doc identifies motion as essential to the "this gets me" feeling. Four specific moments are called out: slot resolution, tag flowing in, day rebuild after pivot, and general kinetic feedback.

Motion in travel apps is underinvested. Most apps use default system animations. The opportunity: motion that makes the system feel intelligent and alive, not mechanical.

Reference patterns:
- **Linear**: fast, purposeful micro-animations. State transitions that feel instant but communicate completion. Not decorative.
- **Stripe**: loading states that feel like work is happening. Progress is specific ("verifying..." â†’ "approved"), not generic.
- **Lottie + Airbnb**: pioneered Lottie for micro-animation. Their booking confirmation animation ("you're going") is a product moment that users remember.
- **iOS SpringBoard**: physics-based animations. Overshoots and settles. Makes UI feel tangible.

The key principle for this product: motion should always carry information. If something moves for purely decorative reasons, cut it.

## Brainstorm

**Slot resolution** (after pivot is accepted, slot changes state):
- The slot card doesn't just swap â€” it "settles" into the new activity. Brief outward scale â†’ snap to final state. Duration: 180ms. Like a card being placed on a table.
- The suggestion lines on the new slot stagger in at 20ms intervals â€” the system revealing the new context in sequence, not all at once.

**Tag flowing in** (onboarding tag selection):
- Selected tag detaches from cloud, scales up briefly, and settles in a "selected" tray at the bottom. The tray grows as more tags are added. This makes the selection feel like collecting, not checking boxes.
- Unselected tags don't disappear â€” they dim. The user always sees the full space.

**Day rebuild after pivot**:
- Unchanged slots stay fixed. Affected slots blur briefly and then re-resolve.
- A subtle timeline "knit" animation runs down the slot spine â€” like a seam stitching closed â€” indicating the day is whole again.
- Duration: 300ms total. Not a "loading" state â€” a "resolving" state.

**Energy bar update**:
- When a high-energy slot is added, the bar fills with a brief overshoot past the new value then settles back. Physics metaphor: adding weight.
- When a break slot is added, the bar gently depletes and breathes.

**Poll result reveal** (group feature):
- Votes appear as they come in, one per member. Staggered 150ms apart.
- The winning option visually grows to fill the slot. The non-winning options don't disappear â€” they compress. Group's decision, not deletion of alternatives.

## Decision / Architecture

Motion token system (extend the existing design token set):
```
motion_tokens = {
  duration_snap: '120ms',
  duration_resolve: '180ms',
  duration_reveal: '300ms',
  duration_slow: '500ms',
  easing_settle: 'cubic-bezier(0.34, 1.56, 0.64, 1)',    // slight overshoot
  easing_resolve: 'cubic-bezier(0.16, 1, 0.3, 1)',        // ease-out expo
  easing_snap: 'cubic-bezier(0.4, 0, 0.6, 1)',            // ease-in-out
}
```

Implementation: CSS transitions for simple state changes. Framer Motion (React) or Reanimated (React Native) for sequenced or physics-based animations. Lottie reserved for celebratory moments only (booking confirmed, trip complete).

## Agent Review

**Security**: No concerns. Motion is display-only.

**DevOps**: Animations should be GPU-accelerated (transform, opacity â€” never layout-triggering properties like width/height/top/left). On lower-end devices, respect `prefers-reduced-motion` media query â€” all animations should have static fallbacks. Performance budget: no animation should trigger a layout recalculation. Test on mid-range Android, not just iPhone Pro.

**UX/Product**: The biggest risk is animation overdose â€” building all of these and finding the app feels like a demo rather than a tool. Rule: implement motion in one place at a time, use in production for a week, then assess. The slot resolution animation is highest priority because it's mid-trip and emotionally loaded. The poll reveal is second â€” it's a social moment that motion can make feel shared. Tags are third. Everything else can wait until post-launch polish.

---

---

# 7. Solo vs. Group as Modes â€” Architecture Decision

## Research

The design philosophy doc resolved this at the product level ("probably modes within one app") but the architecture implications are significant. The data model, the UX surface, and the recommendation pipeline all branch based on this.

Key differences between solo and group mode:
- Group: affinity matrix, polls, fairness tracker, subgroup splits, conflict detection
- Solo: none of the above. Simpler. More intimate.
- Energy model: solo has one curve. Group has N curves that must be balanced.
- Pivot logic: identical underneath, but surface language changes (no "the group agrees")
- Itinerary slot: `group_subset[]` field is either empty (solo) or populated (group)

The risk: building "solo mode" as a stripped-down group mode. This is the wrong approach. Solo travel has a fundamentally different emotional register â€” quieter, more personal, more about self-discovery. The surfaces should be designed independently even if the backend is shared.

## Brainstorm

**Architecture option: Trip-level mode flag**
```
TripNode.mode: 'solo' | 'group'
```
Group-specific fields are null when mode = solo. This is the clean approach. The rendering layer uses mode to determine which components appear.

**UX separation**:
- Solo: no poll component in slot cards. Energy bar is personal, not balanced. Pivot language is "you might prefer..." not "everyone's thinking..."
- Group: all group features active. Group size drives which features are shown (2-person trip doesn't need subgroup split logic).

**Transition between modes**:
A user might start planning a solo trip and later add a travel companion. Or a group trip where one member drops. The mode transition must be graceful:
- Solo â†’ Group: create GroupNode, link user, initialize affinity matrix from single-member seed (nothing to compare yet, matrix seeds on first poll)
- Group â†’ Solo: archive group, detach from GroupNode, preserve travel history attribution

## Decision / Architecture

```
TripNode {
  ...existing fields...
  mode: 'solo' | 'group'
  group_id: string | null   // null when mode='solo'
}

// Solo trip creation: group_id is null, no GroupNode created
// Group trip creation: GroupNode created, affinity matrix initialized
// Mode change: handled as a TripNode mutation event, logged to behavioral signals
```

Rendering layer:
```
if (trip.mode === 'solo') {
  hide: [GroupPollComponent, FairnessBar, SubgroupSplitCard, GroupAffiniityPanel]
  show: [SoloMoodBar, PersonalEnergyTracker, SoloRecommendationCard]
}
```

## Agent Review

**Security**: No issues. Mode is a trip attribute. Ensure group_id is validated server-side â€” a solo user should not be able to request group-specific features by crafting a request with a group_id.

**DevOps**: Mode switch events should be queued as trip mutations, not deletions. If a user switches from solo to group, the existing itinerary must be preserved. Don't delete and recreate. Migration function: `migrate_trip_to_group(trip_id, new_members[])`.

**UX/Product**: The design philosophy doc is right that solo mode needs its own design pass. The immediate opportunity: solo mode's home screen should be warmer and more personal â€” "your Tuesday in Kyoto" not "the itinerary." Typography can be slightly more editorial. The energy bar in solo mode might be presented differently â€” not a progress bar but a gentle ambient indicator. The biggest product question: is solo mode the default or does the app ask upfront? Recommendation: ask "who's going?" as the first question in trip creation (it's the most natural), not as a settings choice.

---

---

# 8. Map View â€” When and How

## Research

The design philosophy doc says: "don't want a pin-covered map as default." This is the right instinct. Most travel apps lead with a map and it creates immediate cognitive overload â€” 47 pins covering a city makes no decisions easier.

The map's job is not discovery (the discovery surface handles that) and not decision-making (the slot list handles that). The map's job is spatial orientation â€” "I understand where I am going and in what order."

Reference patterns:
- **Google Maps**: the default. So ubiquitous that most patterns here are trained behavior.
- **Citymapper**: contextual map â€” shows only the current route, not everything. Reduces to one decision at a time.
- **Things to Do in Airbnb**: map appears after filtering, not before. The list narrows; then the map shows what's left.
- **Wanderlog**: map-first product. Works for pre-trip planning but overwhelms mid-trip.
- **Paper maps**: radically simple. One view, no interaction, spatial context only. The mental model to aim for.

## Brainstorm

**When map appears (triggered modes, not default):**
- Tapping a slot card â†’ map zooms to that venue + nearby alternatives
- Tapping "route" in the day view â†’ map shows the full day's path in sequence
- Desktop: persistent right-panel showing day's route (never pins-only)
- iOS widget: compact map strip showing next 2 stops

**What the map shows (minimum viable):**
- Current day's slots in order, numbered
- Transit lines between them (walking: line, transit: dashed)
- Radius highlighting: 10-minute walk zone from current location
- No: restaurant categories, photos, other days' activities, POI density

**What the map never shows by default:**
- All activities in the city (the temptation to show everything must be resisted)
- Ratings or review data overlaid on map pins
- Competitor venues not in the itinerary
- Search functionality (that's a different mode entirely)

## Decision / Architecture

Map trigger events:
```
MapTrigger {
  trigger: 'slot_tap' | 'route_view' | 'day_overview' | 'desktop_panel'
  scope: 'slot' | 'day' | 'trip'
  zoom_target: ActivityNode.location_geo
  show_alternatives: boolean    // only for slot_tap
  show_route: boolean           // only for route_view
}
```

Map component rendering rules:
- Pins: numbered by slot sequence, not color-coded by category
- Route: polyline in brand color, not Google's blue
- Transit segments: dashed line with transit icon
- Max pins visible at once: 8 (one day's worth). More than that â†’ hide future days

## Agent Review

**Security**: Map API key exposure â€” Google Maps/Mapbox API keys must be server-proxied or domain-restricted. Never expose a billing-enabled map key client-side without restriction.

**DevOps**: Map tile loading is expensive on mobile data. Tile caching for the active trip's city should happen at trip generation time (when on WiFi), not on-demand mid-trip. Consider Mapbox offline tiles for active trip days. Also: map component is a heavy bundle â€” lazy load it. Don't include map JS in the initial app bundle.

**UX/Product**: The mobile implementation should anchor the map in a bottom sheet, not a full screen. User sees their list, taps a slot, map slides up showing spatial context. Tapping outside the map dismisses it. This way map is always one tap away but never in the way. The numbered pin approach (1, 2, 3...) is critical â€” it makes the day legible as a sequence, not a cloud of options. Also: the map should show walking time between stops, not just distance. "7 min walk" is a decision-making input. "0.4 miles" is not.

---

---

# 9. Pre-Trip Group Planning Mode

## Research

The architecture addendum calls this out as "architecturally and emotionally distinct from mid-trip group surface." The design philosophy doc adds: "Pre-trip is anticipation â€” proposing days, debating, building rough consensus before anyone's on the ground. Affinity matrix is seeding, not live."

This is a fundamentally different product problem than the mid-trip experience. Pre-trip planning is collaborative and deliberate. Mid-trip is reactive and fast. The UI surfaces, the language, and the interaction model all need to be different.

Key open questions from the design philosophy doc: how does proposal become vote become locked slot? Where does the budget vibe question live? Day-level vs. slot-level planning granularity?

## Brainstorm

**Proposal â†’ Vote â†’ Lock flow:**

Stage 1 â€” Propose (loose): Group members can add activities to a "pile" â€” not assigned to days, not ordered. Think Pinterest board or a Figma sticker wall. Low commitment.

Stage 2 â€” Organize (day-level): Someone (the trip organizer or anyone) drags activities into day buckets. "Day 2 has: sake brewery, ramen at Ichiran, Nishiki market." No times yet. The group can see, comment, vote thumbs on day compositions.

Stage 3 â€” Detail (slot-level): Once day composition is agreed, assign times. This is where the constraint solver runs and the actual ItinerarySlots are created. This is where booking states activate.

Stage 4 â€” Lock: Locked slots are immutable to casual edits. Changes require explicit "propose a change" action which surfaces to the group.

**Budget vibe question:**
Not a form field. A single card: "How are you all feeling about spending?" with three choices expressed as scenarios:
- "We're here once â€” let's do it properly"
- "Good value, no need to splurge"
- "Mix it up â€” some nice, some local cheap"

Each member answers independently. Group's aggregate creates a budget_mix_signal that feeds the constraint solver. Never asks for specific dollar amounts.

**Granularity:**
Day-level planning as default. Slot-level unlocked on demand ("build out Day 2 in detail"). This matches how people actually plan â€” rough shape first, then fill in. Don't start with empty time slots on day one.

## Decision / Architecture

Pre-trip group planning is a distinct app surface with its own data model:

```
TripDraft {
  trip_id: string
  status: 'draft' | 'planned' | 'active' | 'complete'
  proposal_pile: ActivityNode.id[]    // unassigned, unordered
  day_compositions: {
    day_number: int,
    proposed_activities: ActivityNode.id[],
    group_votes: { member_id: 'yes' | 'no' | 'neutral' }[],
    locked: boolean
  }[]
  budget_vibe: { member_id: string, signal: 'splurge' | 'value' | 'mix' }[]
}
```

Proposal pile never disappears â€” even when activities get assigned to days, they remain in the pile (greyed out) in case the group wants to refer back or reassign.

## Agent Review

**Security**: Group planning mode has multi-user write access to the same TripDraft. Require optimistic locking â€” last-write-wins on proposal pile additions is fine; last-write-wins on day composition edits is not. Two people editing the same day simultaneously must be handled with a merge or conflict resolution pattern. WebSocket real-time sync preferred over polling.

**DevOps**: Real-time collaboration requires a WebSocket connection or SSE channel per TripDraft. At small scale (2â€“8 people per trip), a simple broadcast pattern works. Persist TripDraft state after every change â€” no "save" button. Event sourcing model preferred (log every change as an event, reconstruct state from log) â€” gives you undo, history, and conflict resolution for free.

**UX/Product**: The proposal pile is the most delicate UX decision here. It could feel like a dumping ground. The key: it must have a clear visual relationship to the day compositions. Not a separate tab â€” visible alongside the day view, as a sidebar or bottom area. Activities drag from the pile INTO days. The days don't drag activities from anywhere â€” they receive them. This directional clarity (pile â†’ day) keeps the mental model clean. Also: "lock" is the wrong word for users. "Finalized" or "confirmed" â€” something that feels like agreement, not restriction.

---

---

# 10. Desktop Navigation Architecture

## Research

The design philosophy doc notes: "Mobile has bottom nav. Desktop needs sidebar or top nav. What's the primary nav structure for the planning workspace?"

Desktop is the planning surface â€” sitting down before a trip, organizing days, coordinating with the group. The mental model is closer to a project management tool (Notion, Linear) than a consumer app (Instagram, Spotify).

The use cases on desktop that don't exist or are secondary on mobile:
- Multi-day overview at a glance
- Side-by-side group member comparison
- Persistent map panel
- Detailed activity editing (notes, booking details, confirmations)
- Export / share (calendar sync, PDF packing list)

## Brainstorm

**Layout architecture options:**

Option A: Sidebar + main panel (Linear model)
Left sidebar: trip list, group members, settings. Main area: itinerary with persistent map panel on the right. This is the most productive layout for power users. Risk: too tool-like, loses the warmth of the travel context.

Option B: Top nav + full-width content (Notion model)
Top nav with trip name + day selector. Full-width content area that changes based on what you're doing. Map is a tab, not a persistent panel. More editorial feel. Risk: loses the spatial map context.

Option C: Hybrid â€” top nav for mode, sidebar for trip structure
Top nav for primary mode (planning vs. active vs. review). Left sidebar for the trip tree (days, slots). Right panel contextual â€” shows map when a slot is selected, group affinity when a member is selected, detail panel otherwise. This is the most capable but most complex to build.

**Recommended**: Option A for v1. Linear-style sidebar + map panel. The density matches the use case. The trip list in the sidebar provides context across multiple trips. The persistent map panel is the key differentiator from mobile.

## Decision / Architecture

Desktop layout structure:
```
[Sidebar 240px] [Main content flex] [Context panel 320px conditional]
     â†“                  â†“                         â†“
Trip list +        Itinerary day           Map (default)
Group members      view, multi-day         Member detail
Settings           overview,               Activity edit
                   group board             Booking info
```

Responsive behavior:
- 1440px+: all three panels visible
- 1200â€“1440px: sidebar + main only. Context panel as floating drawer.
- Below 1200px: mobile layout. No desktop panel logic.

## Agent Review

**Security**: Desktop planning surface may handle booking details (confirmation numbers, reservation details). These should never be stored in plain text â€” encrypt at rest. Clipboard operations (copying booking refs) should not trigger autofill vulnerability patterns.

**DevOps**: Desktop is a web app. The same React codebase can serve mobile web and desktop with responsive layout. Don't build a separate desktop app. The sidebar and context panel are additive â€” they require more state management (which panel is active, what is selected) but no new API endpoints. WebSocket connection for group planning real-time sync is more reliable on desktop (persistent tab) than mobile (background app termination risk).

**UX/Product**: The context panel is the most powerful design decision here. When nothing is selected, show the group affinity summary â€” a warm "your group's travel chemistry" view. This turns idle time on the planning screen into an engaging moment. When a slot is selected, the context panel shows the activity deep-dive: source reviews, crowd intel, booking options, LLM tip. This is where the "via Tabelog, 847 local reviews" depth can live â€” it doesn't have to fit on the card. The sidebar trip list should use photography as thumbnails â€” not icons, not generic flags. Seeing the destination photo in the sidebar makes every session start with a spark.

---

---

# Summary Table â€” Open Questions Status

| Question | Status | Next Action |
|---|---|---|
| Energy curve calibration | Architecture drafted above | Design session: confirm heuristic templates + token set |
| Blogger authority model | Architecture drafted above | Implementation: curated seed list first |
| Onboarding / cold start UX | Architecture + frames drafted | Design session: scenario card visual design |
| Overrated signal design | Decision made: no badge | Implement display logic in activity card |
| Discovery / pre-trip browse | Framing drafted | On hold until brand direction set â€” Frame 3 (editorial) can start immediately |
| Motion & feedback | Token set drafted | Implement slot resolution animation first |
| Solo vs. group modes | Architecture decision made | Code the mode flag + rendering branch |
| Map view | Trigger model defined | Design session: bottom sheet interaction on mobile |
| Pre-trip group planning | Draft data model defined | Design session: proposal pile UX |
| Desktop navigation | Layout decision made | Design session: context panel behavior |

---

*Last updated: February 2026*
*Next session priority: energy curve calibration design session + onboarding scenario card visual design*
