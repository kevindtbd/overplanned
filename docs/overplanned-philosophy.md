# [Working Title: Overplanned] — Product & Design Philosophy

*Last updated: February 2026*
*Note: Company name is unsettled. "Overplanned" is a working title only — nothing locked.*

---

## The Core Idea

**Warm, calm surface. Intelligent underneath. The app does the work; you do the traveling.**

Most travel apps are loud. Badge counts, aggressive CTAs, maps crammed with pins, ratings everywhere. They're high-stimulation because they lack confidence — they compensate for weak recommendations with visual noise.

This app is the inverse. The surface is quiet because the system is confident. When the recommendations are genuinely right, you don't need to shout.

The clearest articulation of this: it should read like a spa site. Spa sites are calm because they know what they offer is good. The restraint *is* the communication. The system knows where you should eat tomorrow night. It just needs to tell you — quietly, specifically, warmly — and be right.

---

## The Three Pillars

### 1. Data-forward intelligence, invisible to the user

The behavioral graph, persona engine, local source intelligence, and group dynamics tracking are doing constant work in the background. The user never sees a pipeline. They see a recommendation with a single line explaining why it's right for them — and it *is* right, because the system actually knows them.

This is the Stripe principle applied to travel: make the complex feel controlled. The sophistication shows in the quality of output, not in UI complexity.

Key architectural commitments:
- ML handles scoring, ranking, matching, classification
- LLMs handle input interpretation and output narration only — never decisions
- Local sources (Tabelog, Naver, Dianping, Reddit) always over tourist aggregators
- Behavioral signals override stated preferences when they conflict
- Explainability is a feature: "we suggested this because you tend to prefer X"

### 2. Photography does the warmth work

The UI chrome is warm-neutral and restrained. The world provides the color.

Kyoto in autumn brings the oranges. Santorini brings the blues. The app steps back and lets the destination take over — exactly what Airbnb does at its best, but without the branded warmth that makes Airbnb feel like Airbnb.

Our warmth is:
- `#FAF8F5` off-white base in light mode — linen, not paper
- `#100E0B` near-black with brown undertones in dark mode — not blue-black
- `#C96848` dusty terracotta accent — muted, not saturated. Film photography, not travel brochure
- Full-bleed destination photography inside cards doing emotional heavy lifting

### 3. Open, capable, calm — the Notion quality

The layout breathes. Content isn't competing for attention. The user feels capable, not overwhelmed.

This maps directly to the product reality: the itinerary is complex (group splits, energy curves, local intel, real-time pivots) but the surface exposes exactly what you need at each moment and nothing more.

One primary action visible per component. Everything else revealed on interaction.

---

## The "This Gets Me" North Star

Every design decision runs through this filter. Not "does this look good?" but "does this feel like it knows me?"

The moments where this lands:
- The **"why this" line** on every itinerary slot — casual, specific, references the group. Never generic.
- **Tags driving today** in the sidebar — showing which of *your own choices* shaped the plan. Transparent, not evaluative.
- The **group poll** that feels like a group chat, not a form
- The **real-time pivot** that feels like a tap on the shoulder from a friend, not a system alert

The moments to avoid:
- Telling users what you think they are ("you're a night owl") — show it through the quality of what you surface
- Surveillance-adjacent language ("we notice you tend to...") — frame through their choices, not our observations
- Gamification — no streaks, no badges, no progress bars for their own sake

---

## Design System Foundations

**Base file:** `overplanned-design-v4.html` — locked, all new screens build on this

**Typeface:** Sora (geometric, clean, slightly rounded) + DM Mono for all data/labels

**Color philosophy:** Two themes, one token system
- Light: `#FAF8F5` warm off-white base, `#B85C3F` terracotta accent
- Dark: `#100E0B` warm brown base, `#C96848` terracotta accent with subtle glow on anchors

**Icon system:** Stroke-based SVG icons, color-coded by category. No emoji anywhere.
- Terracotta → Food & drink
- Blue → Sightseeing & culture
- Green → Pace & style
- Amber → Activities

**Photography:** Full-bleed Unsplash photography in destination hero cards, activity cards, and anchor slot thumbnails. Warm gradient overlays (brown-black, never cool-black).

**Elevation:** Exactly two shadow levels — surface and float. No decorative shadows.

**Spacing:** 8px base system throughout. Generous negative space is a feature.

---

## References & What We Take From Each

| Reference | What we take |
|-----------|-------------|
| **Airbnb** | Photography warmth, card language, map-itinerary split, group social surfaces |
| **Stripe** | Data discipline, mono type for stats, information hierarchy, dashboard rigor |
| **Notion** | Openness, breathing room, the sense that you can do anything here |
| **Spotify Daylist** | Persona reveal language — casual, specific, slightly surprising. The "we know you" feeling without surveillance |
| **Linear** | Dark mode discipline, fast feel, itinerary and scheduling surface language |

---

## What's Built

**v4 design system (locked base):**
- Token system — light + dark, one source of truth
- Destination hero card with full-bleed photography
- Activity card grid — photo top, colored category icon, one "why" line, source badge, local/overrated signal
- Slot photo thumbnails on anchor-type itinerary slots
- Trip creation flow with tag system (cold start mechanic)
- Itinerary day view — slot spine, energy bar, group poll, stat boxes, route list, sidebar
- SVG icon system with category colors applied throughout

**Screens built:**
- `overplanned-pivot-ui.html` — real-time reactivity layer, mid-trip drawer, system + user-initiated pivots unified
- `overplanned-group-social.html` — mid-trip group surface, four states (harmony / tension / split / solo), vote chips + trajectory dot + energy strip

---

## Full Design Backlog

### Priority 1 — Core App Screens

**Day view + slot card (build next)**
The foundation everything else extends from. Currently a sketch in v4 base — not built as a proper interactive screen. The slot card is the emotional core: it's where the "why this" line lives. Must design for two modes: solo and group. Solo is personal and quiet. Group has vote chips and group context baked into the card.

The "why this" line needs its own design thinking:
- Solo: "you gravitate toward standing bars over sit-down — this one gets busy by 8"
- Group: "you and SL both swipe past tourist-heavy spots — this is where locals actually go"
- One line maximum. Specific, casual. Never generic. Frames through their behavior, not our observation.

The local source / overrated signal also lives here. Pipeline C is a core differentiator with no design language yet. Source attribution probably does more work than any explicit flag: "via Tabelog, 847 local reviews" says everything without saying anything.

**Individual itinerary view**
Solo travel is a distinct mode. Different emotional register — more personal, quieter, no poll layer. Energy tracking is simpler (one curve). Pivot logic identical underneath but the surface is more intimate. Needs its own design pass — don't just strip the group layer out of the group view.

**Map view**
Table stakes. Not built. The question is when it appears — we don't want a pin-covered map as default. Probably: map surfaces contextually on slot tap, day view has a subtle strip not full-screen. Desktop gets a persistent panel. Mobile gets it as a revealed layer.

**Group planning mode (pre-trip)**
Architecturally and emotionally distinct from mid-trip group surface. Pre-trip is anticipation — proposing days, debating, building rough consensus before anyone's on the ground. Affinity matrix is seeding, not live. Poll design is more open (propose vs. vote, not just vote). Start fresh — don't extend the mid-trip surface.

Key open questions: how does proposal become vote become locked slot? Where does the budget vibe question live? Day-level vs. slot-level planning granularity?

---

### Priority 2 — States & Flows

**Onboarding / persona cold start**
First-run. Tag selection seeding the behavioral graph. Must feel like planning a trip, not filling out a profile. Tag cloud → destination affinity → travel style framed as "what sounds good right now" not "describe yourself."

**Empty states**
First time in the app, blank slate, post-pivot recompute. Calm and specific beats generic. "We're finding spots that fit how you travel" not a spinner.

**Loading / skeleton states**
The system is doing real work. Skeleton screens with photography already loading. Progress language that's specific: "checking what's open tonight" not a progress bar.

**Error states**
Venue closed, no signal, transit disrupted. Same tone as everything — calm, specific, forward-facing. "Fushimi's closed for a private event — here's what we'd swap in" not "error fetching venue data."

**Notifications / ambient layer**
The system detects things when the user isn't in the app. Push notification design: one clear thing, one action, never more. Same language register as in-app moments.

---

### Priority 3 — Platform Split

**Mobile (primary)**
Mid-trip experience lives here. Everything built so far is mobile-first. Touch targets generous. One action visible at a time. Bottom-anchored primary actions.

**Desktop / web (secondary)**
Planning mode is the desktop use case. Sitting down the week before a trip, building the itinerary, coordinating. Different layout entirely: persistent map panel right, itinerary spine left, group activity feed in sidebar. Linear-style density — not mobile-sparse. More information is appropriate when the user has time and attention.

Key desktop-specific surfaces:
- Trip dashboard — all upcoming/past trips, group members across trips
- Planning workspace — pre-trip group planning at full desktop width
- Map + itinerary split — persistent map with interactive slot pins

**Responsive approach**
Design system tokens are already platform-agnostic. Layout grid shifts significantly between mobile and desktop; components (cards, chips, vote chips, energy strips) carry across without redesign — just recomposed at different density.

---

### Priority 4 — Marketing & Web Presence

**Landing page**
High risk of overselling. The temptation is feature screenshots; the better move is showing the *output* — a beautiful, specific itinerary for a real-feeling trip, and let people wonder how it got made.

Core sections:
- Hero — single value prop, destination photography, one CTA. No feature list above the fold.
- "How it knows you" — the behavioral graph in plain language. A story, not a tech explainer.
- Group travel — the warmth differentiator told through a moment, not a feature list.
- Local intelligence — Pipeline C as a user-facing differentiator. "We go to Tabelog, Naver, Xiaohongshu, Reddit. Not TripAdvisor."
- Pricing / waitlist CTA — depends on go-to-market.

Design direction: warmer and more editorial than the app. More photography, more white space, slightly more expressive type. App is functional-warm; landing page can be aspirational-warm.

**App store presence**
Screenshots framed around moments not features. "The pivot." "The group vote." "Why this restaurant." App store copy is its own craft.

**Waitlist / early access flow**
Confirmation email, what happens next, referral mechanic. Email design matches app visual language — Sora, warm tokens, no corporate template.

**Blog / content layer**
Eventually. Travel content demonstrating local intelligence philosophy doubles as SEO and brand. Not a priority now but plan for it.

---

## Open Design Questions

1. **Solo vs. group as modes or products?** Probably modes within one app — but a solo traveler's mental model may differ significantly from a group traveler's. Needs validation.

2. **The map problem.** When does map appear? Need a strong point of view before building day view.

3. **Overrated signal design.** Badge risks preachy. No signal wastes the differentiator. Source attribution probably does the work implicitly — needs a design decision.

4. **"Why this" at cold start.** LLM-generated, but what does it say for a first-time user with no behavioral history? Needs a graceful fallback.

5. **Planning mode granularity.** Day-level ("temples on day 2") vs. slot-level ("three specific places, vote on one"). The transition from loose planning to locked itinerary is a key flow.

6. **Desktop navigation architecture.** Mobile has bottom nav. Desktop needs sidebar or top nav. What's the primary nav structure for the planning workspace?

7. **Monetization surface.** Where is the paywall if any, and what does crossing it feel like? Don't design as an afterthought.

---

## Build Order

1. **Day view + slot card** — foundation. Solo first, group layer second.
2. **Group planning mode** — pre-trip, desktop-first, separate screen family.
3. **Onboarding** — cold start, tag selection, feels like planning not profiling.
4. **Landing page** — editorial-warm, one hero value prop, shows output not features.
5. **Map view** — contextual not default. Mobile layer + desktop panel.
6. **Empty / loading / error states** — polish pass across all screens.
7. **Desktop trip dashboard** — full planning workspace at desktop density.
8. **App store assets** — screenshots framed around moments, not features.
---

## Booking System — Deferred to Phase 2

*Noted February 2026 — revisit after core app screens are built*

The logical completion of the value prop. If the system knows where you should eat, knows the group, knows the time — it should be able to handle the booking too. Architecturally sound, commercially strong (commission or premium tier), and closes the recommendation-to-reality feedback loop with richer signal than behavioral inference alone.

**The right framing:** Not "automatic booking" — **confirmable booking**. The system does the preparation work (finds availability, pre-fills details, knows group size and time) and surfaces one tap to confirm. Same pattern as the pivot drawer. User is never surprised by a booking they didn't explicitly approve.

**Three tiers:**
- Tier 1 — Deep links + pre-fill. No API needed, works everywhere, meaningful friction reduction.
- Tier 2 — Integrated booking via OpenTable, Resy, GetYourGuide. Seamless but skews toward tourist-heavy venues — exactly what Pipeline C deprioritizes. Tension to manage.
- Tier 3 — Native booking with honest concierge fallback. The Kyoto kappo counter can't be booked programmatically. The app either uses a human concierge layer or flags it clearly: "this one you'll need to call." That honesty is a differentiator.

**Hard problems to solve later:** Regional fragmentation (Japan especially), group booking authority (who confirms, who cancels), trust calibration (one wrong booking collapses it), activity cancellation policies with real money attached.

**Design implication for now:** The slot card needs booking states regardless — booked, bookable, needs action, not bookable. Design these states into the day view now. Wire up real booking in Phase 2 once venue data pipeline is proven. No rework needed.

**Build order impact:** None. Proceed with day view as planned.