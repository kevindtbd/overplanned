# Overplanned â€” Product & Design Philosophy

*Last updated: February 2026 (v2 â€” expanded from design session)*

---

## The Core Idea

**Warm, calm surface. Intelligent underneath. The app does the work; you do the traveling.**

Most travel apps are loud. Badge counts, aggressive CTAs, maps crammed with pins, ratings everywhere. They're high-stimulation because they lack confidence â€” they compensate for weak recommendations with visual noise.

Overplanned is the inverse. The surface is quiet because the system is confident. When the recommendations are genuinely right, you don't need to shout.

---

## Why We Exist

Overplanned exists to eliminate the cognitive load of travel planning. The cross-referencing, the tab overload, the "is this place actually good or just well-marketed" anxiety, the logistics coordination across a group â€” all of it. We take that burden and give back time, confidence, and better trips.

We make money directly from users. They pay us to think for them. That's the contract. No ads, no sponsored placements, no travel industry partnerships that compromise the quality of what we surface â€” unless an acquisition offer changes the company's trajectory entirely. At that scale, everything is a conversation. Below that threshold, quality is the only currency that matters.

We are not a discovery platform. We are not a booking engine. We are the intelligence layer between "I want to go somewhere" and "that was the best trip I've ever taken."

---

## Who We're Building For

Overplanned serves three distinct users with the same engine, different emotional needs:

### The First-Timer
Someone who doesn't yet know how to travel well. Overwhelmed by options, unsure what "good" looks like, anxious about making the wrong choices. For them, Overplanned is a confidence machine. It removes the anxiety of not knowing, replaces it with a plan that feels considered and specific, and teaches â€” through the quality of the experience itself, not through tutorials â€” what great travel actually feels like. The goal: they come back from their first real trip having leveled up permanently.

### The Regular Traveler
Travels a few times a year. Knows what they like. Has opinions. Wants those opinions respected and reflected back in the recommendations. For them, Overplanned is a taste-matching tool â€” it gets them faster, suggests things they wouldn't have found on their own, and handles the logistics so they can focus on being there. The goal: every trip is better than it would have been without us.

### The Time-Poor High Earner
Household income 150k+, no human concierge, deeply busy. Doesn't lack money or taste â€” lacks time. Wants concierge-quality output with zero back-and-forth. One tap, great plan, done. The active-travel layer (real-time pivots, mid-trip intelligence) is where they feel the premium â€” because their time mid-trip is the most expensive thing they have. The goal: the app earns their trust so completely that they stop second-guessing it.

All three users are valid. The product doesn't compromise for any of them â€” the intelligence layer is deep enough to serve all three. The differentiation is in what they feel, not in what they get.

### Contextual Quality Escalation

The algo reads the occasion, not just the person. Trip context overrides individual persona signals when it comes to quality tier.

A one-night city stay doesn't need the Ritz unless the group's signals say so. A bachelor party with high-energy, high-spend signals gets best-in-range surfaced across the board â€” hotels, restaurants, experiences. A budget traveler on a special anniversary gets the one splurge that's actually worth it surfaced prominently. An unseasoned traveler gets guardrails that build confidence, not options that overwhelm.

The system captures spending signals and vibe signals behaviorally â€” through choices made, not forms filled out. Quality recommendations emerge from that read naturally. We don't upsell artificially. We don't surface the Michelin restaurant to someone who's never signaled for it. But we don't hide it from someone whose trips say they'd love it. The intelligence does this work silently. That's the point.

There is no separate "premium mode" for quality. The recommendation system handles quality escalation automatically based on who the person is and what the trip calls for. We can't book the Michelin restaurant for them â€” that's on the user. But we can tell them it's worth it and exactly why.

---

## The Business Model

**Direct consumer revenue. Simple.**

- Free tier: two trips. Real value, real product, not a teaser. Enough to feel what Overplanned is.
- Paid tier: group trips (trip creator pays, members never pay), offline mode, additional concurrent trips, active-travel intelligence layer.
- Pay-per-trip option for infrequent travelers who don't want a subscription.

The paywall sits at natural inflection points â€” adding a group member, activating offline mode before departure, requesting real-time pivots mid-trip. Never mid-planning, never before the user has seen what the product can do.

The active-travel layer â€” real-time pivots, mid-trip intelligence, offline access â€” is the premium differentiator. The planning layer is strong enough free to hook users. The active layer is what makes them pay and stay.

---

## The Three Pillars

### 1. Data-forward intelligence, invisible to the user

The behavioral graph, persona engine, local source intelligence, and group dynamics tracking are doing constant work in the background. The user never sees a pipeline. They see a recommendation with a single line explaining why it's right for them â€” and it *is* right, because the system actually knows them.

This is the Stripe principle applied to travel: make the complex feel controlled. The sophistication shows in the quality of output, not in UI complexity.

Key architectural commitments:
- ML handles scoring, ranking, matching, classification
- LLMs handle input interpretation and output narration only â€” never decisions
- Local sources always over tourist aggregators â€” this is the secret sauce, not the marketing message
- Behavioral signals override stated preferences when they conflict
- Explainability is a feature: "we suggested this because you tend to prefer X"
- The source intelligence is never named publicly until the user is inside the product

### 2. Photography does the warmth work

The UI chrome is warm-neutral and restrained. The world provides the color.

Kyoto in autumn brings the oranges. Santorini brings the blues. The app steps back and lets the destination take over â€” exactly what Airbnb does at its best, but without the branded warmth that makes Airbnb feel like Airbnb.

Our warmth is:
- `#FAF8F5` off-white base in light mode â€” linen, not paper
- `#100E0B` near-black with brown undertones in dark mode â€” not blue-black
- `#C96848` dusty terracotta accent â€” muted, not saturated. Film photography, not travel brochure
- Full-bleed destination photography inside cards doing emotional heavy lifting

### 3. Open, capable, calm â€” the Notion quality

The layout breathes. Content isn't competing for attention. The user feels capable, not overwhelmed.

This maps directly to the product reality: the itinerary is complex (group splits, energy curves, local intel, real-time pivots) but the surface exposes exactly what you need at each moment and nothing more.

One primary action visible per component. Everything else revealed on interaction.

---

## The "This Gets Me" North Star

Every design decision runs through this filter. Not "does this look good?" but "does this feel like it knows me?"

The moments where this lands:
- The **"why this" line** on every itinerary slot â€” casual, specific, references the group. Never generic.
- **Tags driving today** in the sidebar â€” showing which of *your own choices* shaped the plan. Transparent, not evaluative.
- The **group poll** that feels like a group chat, not a form
- The **real-time pivot** that feels like a tap on the shoulder from a friend, not a system alert

The moments to avoid:
- Telling users what you think they are ("you're a night owl") â€” show it through the quality of what you surface
- Surveillance-adjacent language ("we notice you tend to...") â€” frame through their choices, not our observations
- Gamification â€” no streaks, no badges, no progress bars for their own sake

---

## Product Scope â€” Where Overplanned Lives

Overplanned sits at **research â†’ pre-trip prep â†’ active travel**. That's the arc.

- **Research phase:** destination discovery, inspiration, "should I go to Kyoto or Tokyo?" â€” we help here, but lightly. We're not a travel magazine.
- **Pre-trip prep:** this is the core. Trip planning, itinerary building, group coordination, logistics. This is where Overplanned earns its keep.
- **Active travel:** the premium layer. Real-time pivots, offline access, mid-trip intelligence. The cherry on top â€” the thing paid users get that makes them feel the price was worth it.
- **Post-trip:** saving the itinerary as a memory, shareable for other users to import. That's the artifact. The post-trip experience is the saved trip, not a separate product.

We are not trying to own the full travel lifecycle. We own the thinking and the doing. Booking, flights, hotels â€” those live elsewhere. We integrate or link where it helps, but we don't need to own them.

---

## Group Travel Philosophy

Group travel is fundamentally an **organization problem**, not a consensus problem.

Overplanned organizes. The humans decide. We don't try to mediate between someone who wants luxury and someone who wants hostels â€” that's a human negotiation that exists outside our product. Our job is to make the logistics not suck, surface what everyone voted for, and present options clearly.

Group dynamics in Overplanned:
- **Small groups and couples:** the product does real coordination work â€” polls, shared itinerary, real-time updates across members
- **Groups with a dominant decision-maker** (bachelor/bachelorette, family trip with a planner): the organizer uses Overplanned as a tool, the group gets visibility without friction
- **Generic friend groups with divergent preferences:** we do our best. We surface the options, run the polls, show the compromise. We can't fix a group where two people fundamentally disagree about travel â€” that's not a product failure, that's life.

The fairness tracker and affinity matrix exist to surface information, not enforce outcomes. We show who's compromised most. We don't penalize or correct. That's the group's call.

---

## Failure Philosophy

We will get recommendations wrong. Venues close. Data goes stale. The persona model misreads someone. That's real.

When we get it wrong, the principles are:

**No overcompensation.** If someone had a bad hike, we soften the weight on hiking. We don't eliminate hiking from their universe. We don't infer that one bad experience means a category is off-limits. Unless they tell us explicitly â€” then we listen completely.

**Post-trip is the feedback loop.** The clearest signal we can get is post-trip: what they didn't like, what surprised them, what they'd do differently. This feeds the algo without requiring mid-trip interruption.

**Generic safety rules, not identity-based filtering.** We don't ask users to declare their identity to get safe recommendations. We build generic rules that protect everyone â€” neighborhoods with documented safety issues get flagged regardless of who's asking, venues with patterns of hostile behavior get downweighted in the authority model. The protection is systemic, not personalized. This is both the ethical and the practical approach.

**Graceful degradation over confident wrongness.** When the system doesn't know â€” new city, sparse data, novel persona â€” it says so through the quality of its confidence signal, not by faking certainty. Better to surface three strong options than ten weak ones.

The refund and recovery policy, and the specific interface for "this recommendation was wrong," are unresolved and need a dedicated deep dive.

---

## Privacy Philosophy

GDPR compliance and all applicable regional frameworks are non-negotiable minimums, not aspirational goals. We build to comply from day one.

The principles beyond compliance:

**Minimize PII collection.** If we don't need to know your name to give you a good recommendation, we don't need your name. Behavioral heuristics over personal data at every decision point.

**The persona belongs to us, the memories belong to you.** The behavioral graph â€” what the system has learned about how you travel â€” is Overplanned's intelligence asset. It's not exportable, it's not portable, it's not yours to take. What IS yours: every trip you've taken, every itinerary you've built, every note you've made. Those are memories. Export them anytime, in full, forever.

**Train on patterns, not people.** The ML models train on behavioral heuristics and anonymized patterns, not on personal data. A user's specific behavioral graph never becomes training data. What becomes training data: aggregate patterns â€” "users with this vibe profile tend to prefer these activity types" â€” stripped of any individual identity.

**No surveillance language, no surveillance framing.** We know things about how you travel. We earned that knowledge through use. We surface it as taste and preference, never as observation or monitoring.

---

## Competitive Positioning

We don't explain our sources on the marketing site. We don't say "we use Tabelog instead of TripAdvisor." We show the output and let it speak.

The implicit promise: this recommendation is different from what you'd find on Google Maps. It's what people who actually live there think, filtered through what we know about you. We don't need to explain the mechanism. The quality is the argument.

Inside the product, once someone is a user, source attribution is a feature â€” "via Tabelog, 847 local reviews" builds trust. Outside the product, it's our method. We keep it.

---

## Design System Foundations

**Typeface:** Sora (geometric, clean, slightly rounded) + DM Mono for all data/labels

**Color philosophy:** Two themes, one token system
- Light: warm off-white base, terracotta accent reads muted and intentional
- Dark: warm brown base, same accent with a slight glow on key anchors

**Icon system:** Stroke-based SVG icons, color-coded by category
- Terracotta â†’ Food & drink
- Blue â†’ Sightseeing & culture
- Green â†’ Pace & style
- Amber â†’ Activities

**Elevation:** Exactly two shadow levels â€” surface and float. No decorative shadows.

**Spacing:** 8px base system throughout. Generous negative space is a feature.

---

## References & What We Take From Each

| Reference | What we take |
|-----------|-------------|
| **Airbnb** | Photography warmth, card language, map-itinerary split, group social surfaces |
| **Stripe** | Data discipline, mono type for stats, information hierarchy, dashboard rigor |
| **Notion** | Openness, breathing room, the sense that you can do anything here |
| **Spotify Daylist** | Persona reveal language â€” casual, specific, slightly surprising. The "we know you" feeling without surveillance |
| **Linear** | Dark mode discipline, fast feel, itinerary and scheduling surface language |

---

## What's Built vs. What's Next

**Built (v3 design system):**
- Token system (light + dark, one source of truth)
- Trip creation flow with tag system (cold start mechanic)
- Itinerary day view with slot types, energy bar, group poll, sidebar
- Icon system replacing all emoji

**Design surfaces still to solve:**
- **Discovery / pre-trip browse** â€” the emotionally crucial moment before a trip is started
- **Real-time pivot UI** â€” needs to feel like a calm suggestion, not an alert
- **Group social surface** â€” full group dynamics view, subgroup splits
- **Motion & feedback** â€” how slots resolve, how tags flow in, how the day rebuilds
- **Onboarding / persona build** â€” should feel like planning, not profiling
- **Activity card browse** â€” full recommendation surface with source attribution

---

## The Spa Read â€” Why It's Right

The observation that this reads like a spa site is actually the clearest signal that the design philosophy is working.

Spa sites are calm because they're confident. They know what they offer is good, so they don't need to shout. The restraint *is* the communication.

Overplanned should feel the same way. The system knows where you should eat tomorrow night. It doesn't need to prove it with a busy UI. It just needs to tell you â€” quietly, specifically, warmly â€” and be right.

That's the whole thing.
