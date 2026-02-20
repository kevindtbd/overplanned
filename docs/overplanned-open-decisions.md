# Overplanned — Open Technical & Product Decisions

*Last updated: February 2026*
*Purpose: Feed into deep-dive sessions. Each item is a decision that Claude Code cannot make — it requires product philosophy, not implementation.*

---

## How to Use This File

Each item has:
- **Status** — unresolved / direction set / needs design / needs deep dive / ✅ RESOLVED
- **What needs deciding** — the actual question, not the implementation
- **Why it matters** — what it blocks or affects downstream
- **Constraints already set** — what we've already decided that narrows the answer

Items are loosely ordered by dependency — earlier items should be resolved before later ones.

---

## ✅ 1. Trust & Failure Recovery System

**Status:** RESOLVED — see `overplanned-trust-failure-recovery.md`

**Summary of decisions:**
- Two failure categories: data failure (compensable) vs. experience mismatch (not compensable, but learned from)
- Four-tier recovery model: auto-verified data failure → unverified data failure → experience mismatch → broken trip
- One-tap flag on slot card, available both mid-trip and post-trip
- Credit: $5 or 20% off next purchase, whichever is higher, 12-month expiry, account credit only (not cash)
- Broken trip refund: prorated, manual review, high threshold (3+ verified failures or anchor activity failure)
- Anti-abuse: signal triangulation (external API validation, network effect validation, claim history tracking), not bureaucracy
- Free tier credits apply toward paid upgrade only — no cash-out path
- Algo misread: weight softening, 2–3 signals triggers one quiet acknowledgment, explicit language only for full suppression, no persona layer surfaced to user

---

## ✅ 2. Premium Tier Definition

**Status:** RESOLVED — captured in `overplanned-philosophy-v2.md`

**Summary of decisions:**
- No separate premium mode for quality — the algo does quality escalation automatically based on behavioral signals
- Trip context overrides individual persona for quality tier (bachelor party → best-in-range; one-night stay → realistic)
- Active-travel layer (real-time pivots, offline, mid-trip intelligence) is the paid differentiator
- We can't book for users — surfacing and recommending is the product, execution is theirs
- High earner and first-timer served by same engine, different emotional output

---

## ✅ 3. Safety Rules — Generic Protection Model

**Status:** RESOLVED (philosophy) — implementation in Pipeline C data sources doc

**Summary of decisions:**
- Protection is systemic, not identity-based — no user disclosure required
- Generic safety rules apply to all users equally: documented unsafe areas, venues with hostility patterns, country-level advisories
- LGBTQ+ safety indexes (Equaldex, ILGA) connected to ActivityNode weighting, not surfaced as explicit flags
- Suppression threshold: documented, consistent pattern of safety incidents → suppress. Single incident or ambiguous signal → downweight only
- Activities with inherent risk (extreme sports, remote hiking) are not suppressed — the risk is part of the activity's character, not a safety failure
- Display language: quiet downweighting preferred. No badges, no warning banners unless the risk is extreme and universal. One-line contextual note at most ("popular with experienced hikers — check conditions beforehand")
- Safety signals maintained by Pipeline C automated crawl + human review queue for edge cases
- Legal posture: Overplanned is a recommendation platform, not an insurer. We make reasonable efforts, we don't guarantee safety.

---

## 4. Monetization Edge Cases

**Status:** Core model set, edge cases unresolved

**What needs deciding:**
- Group billing: what happens when a trip creator's subscription lapses mid-trip? Do group members lose access?
- Pay-per-trip model: is the trip purchase per destination or per trip instance? What if someone plans the same destination twice?
- Free tier: 2 trips means 2 lifetime trips, or 2 concurrent active trips, or 2 trips per year?
- What happens to a user's trips if they cancel their subscription — do they lose access to past itineraries?
- Trial period: does the premium tier have one? How long?

**Why it matters:** These edge cases determine the actual user contract and affect data architecture (what gets gated, how entitlements are tracked).

**Constraints already set:**
- Group members never pay — only the trip creator
- Paywall at natural inflection points, never mid-planning
- Trips as memories are always accessible regardless of subscription state
- Credits apply toward paid upgrades, never cash

---

## 5. Onboarding Flow Design

**Status:** Architecture exists, UX undesigned

**What needs deciding:**
- What is the first question? ("Who's going?" vs. "Where are you going?" vs. "What kind of traveler are you?")
- How many questions before the first itinerary is shown? What's the minimum viable persona seed?
- Do preset templates (couples_slow, group_packed, etc.) come before or after individual questions?
- What does the first generated itinerary reveal look like? What's the loading state? What's the moment?
- Group async onboarding: how long does the system wait for members before generating? What's the partial-state experience?
- What happens if a user skips all questions? Do we let them?

**Why it matters:** Onboarding seeds the persona that determines first-trip quality, which determines retention. The first-timer user segment depends on this experience being excellent.

**Constraints already set:**
- Should feel like planning, not profiling
- Preset templates exist and map to persona dimension seeds
- 6-8 persona dimensions before trip one is the ML target
- The experience should leave the user more excited about their trip than when they started

---

## 6. Search & Discovery Surface

**Status:** Not started

**What needs deciding:**
- Which of three user modes is the primary home screen entry point: (a) destination search, (b) inspiration/vibe-first, (c) contextual/mid-trip?
- What does the destination result look like — generic list, trip template, or editorial "Overplanned's take"?
- Does inspiration mode (vibe → destination) exist at v1, and if so, what's the minimum viable version?
- Is there a browse/editorial surface — curated destinations, seasonal picks, trending? If yes, is that a content operation or an algorithmic one?
- What happens when someone searches before completing onboarding?

**Why it matters:** The home screen is the first thing every returning user sees and the second thing every new user sees (after onboarding). It defines the product's identity more than any other surface.

**Constraints already set:**
- No search bar visible by default on the discovery surface
- Persona-ranked ordering is the only dynamic element — not editorial curation as default
- First-timer needs confidence, not overwhelm

---

## 7. Post-Trip Experience Design

**Status:** Stub exists (notification trigger), product undesigned

**What needs deciding:**
- What does the post-trip screen look like when a user opens the app the day after returning?
- How is post-trip feedback collected without it feeling like a survey? What's the UX?
- What's the format of the trip memory — itinerary printout, highlight reel, something else?
- How explicit is the "your preferences updated" communication? Show the persona evolution or keep it invisible?
- When and how does post-trip transition into next-trip inspiration? What's the re-engagement hook?

**Why it matters:** Post-trip is the highest-quality behavioral signal opportunity AND the retention mechanism. It's also the moment where the first-timer either becomes a loyal user or considers the relationship closed.

**Constraints already set:**
- Post-trip = saved itinerary shareable for other users to import. That's the primary artifact.
- Forward-looking feedback prompt: "anything we should know for next time?" — never a star rating, never a form
- The persona belongs to Overplanned, the memories belong to the user
- Feedback propagates via weight softening, not category elimination

---

## ✅ 8. Data Freshness & ActivityNode Confidence Decay

**Status:** RESOLVED — see `overplanned-trust-failure-recovery.md`

**Summary of decisions:**
- Confidence decay by source type: Google Places (real-time), Tabelog aggregate (slow/monthly), Reddit/forum thread (fast/6-month half-life), blog post (fast/6-month half-life)
- ActivityNode status field: `active` → `unconfirmed_closed` → `temporarily_closed` → `permanently_closed`
- Any non-`active` status: suppressed from recommendations immediately regardless of quality scores
- Anomaly-triggered refresh: normal venues on periodic schedule; flagged venues get immediate targeted Pipeline C recrawl
- Tourist/local divergence as drift signal: if tourist_score shifts significantly, flag for confidence review and soften quality signal until fresh local data confirms
- Conflict resolution: recent negative cluster + old positive score = confidence decay applied, most recent credible signal wins

---

## 9. Group Travel — Organization vs. Consensus Boundary

**Status:** Philosophy set, product implications not resolved

**What needs deciding:**
- The fairness tracker shows who's compromised most — but does it ever *do* anything with that information, or just display it?
- Subgroup splits: when does the system proactively suggest "maybe split for the afternoon" vs. waiting for the group to decide?
- What's the override model in a group with a dominant decision-maker (bachelor party, family trip)? Can the organizer lock decisions without polling?
- What signals indicate a group has irreconcilable preferences vs. normal variation? Does Overplanned flag this or stay silent?

**Why it matters:** The fairness tracker and affinity matrix are architecturally complex. If the philosophy is "we organize, we don't mediate," some of that complexity may be overbuilt.

**Constraints already set:**
- Overplanned organizes, humans decide — we don't mediate travel philosophy differences
- Fairness tracker surfaces information, doesn't enforce outcomes
- Bachelor party / dominant-speaker group: organizer signals drive the experience, group gets visibility not veto
- Generic friend groups: we present options, run polls, show the compromise — and then step back

---

## 10. Industry Partnership Policy

**Status:** Direction set, threshold undefined

**What needs deciding:**
- What is the actual threshold for an industry partnership — dollar figure, or nature of relationship?
- If a hotel pays to be included in the ActivityNode database, does that corrupt the system? What's the disclosure model?
- What's the line between acquisition and partnership?

**Why it matters:** Having a stated position prevents ad-hoc decisions that gradually compromise quality.

**Constraints already set:**
- No industry partnerships unless the number changes the company's trajectory entirely
- Quality is the only currency below that threshold
- Acquisition preferable to partnership as a relationship model

---

## 11. Real-Time Reactivity — Group Complexity

**Status:** Solo reactivity architected, group reactivity unresolved

**What needs deciding:**
- When one group member signals low energy mid-trip, what's the threshold for replanning? Does the whole day shift, or just that person's next slot?
- Does Overplanned poll the group before replanning, or act first and surface the change?
- In a group of 4, if one person has a bad reaction to a recommendation, does that signal affect the group's recommendations or only that person's individual persona?
- What's the UX for "the group split" — subgroup A does X, subgroup B does Y?

**Why it matters:** The reactivity layer is the active-travel premium differentiator. Group trips are a paid feature — under-designing this makes the premium experience feel broken.

**Constraints already set:**
- Context drift guard: MAX_PIVOT_DEPTH=1 default, opt-in for full rebuild
- Cascade evaluation: only surface what changed
- Group trip is an organization tool — system presents options, humans choose

---

## 12. Competitive Moat — Long-Term

**Status:** Not discussed

**What needs deciding:**
- If Google Maps or Airbnb builds a "local intelligence" feature, what does Overplanned have that they don't?
- Is the moat the behavioral graph, the local source network, the group dynamics layer, or something else?
- Does Overplanned need to think about defensibility now, or post-PMF?

**Why it matters:** Architecture decisions made now determine how defensible the product is in 3 years.

**Constraints already set:**
- The persona and behavioral graph are Overplanned's intelligence asset — not portable by users
- Local source authority is a compounding advantage — the model improves as more data arrives

---

## ✅ Thread 1 — Algo Misread

**Status:** RESOLVED — see `overplanned-trust-failure-recovery.md`

**Summary of decisions:**
- Mid-trip: quiet thumbs-down on slot card (secondary action, discreet). Low-weight in isolation — single signal is a whisper, not an action.
- Post-trip: forward-looking prompt "anything we should know for next time?" in natural trip review flow. Input bar accepts plain language for specific feedback.
- 1 negative signal: softened silently, no acknowledgment, no visible change.
- 2–3 negative signals on same category in same trip window: one quiet in-product line — "noted, we'll adjust your recommendations." Appears once, in context, disappears. Never a modal, never a notification.
- Explicit suppression only via plain language in input bar ("no more hiking ever"). Repeated signals alone never fully suppress — only explicit intent does.
- No persona layer surfaced to the user. No profile view, no Spotify Daylist-style reveal. Intelligence shows through output quality, not transparency about machinery.
- No compensation, no apology, no star rating prompt. The trade: feedback captured, next trip better.

---

*✅ Items 1, 2, 3, 8 and Thread 1 fully resolved.*
*Items 4–7 are build-sequence dependencies — resolve before designing the relevant surfaces.*
*Items 9–12 are strategic — important but not blocking near-term development.*

---

## ✅ 6. Search & Discovery Surface — Inspiration Mode

**Status:** RESOLVED

**Summary of decisions:**
- Two states, same surface, transition invisible to user
- **Returning user (behavioral data present):** System leads with one confident destination guess. Single recommendation, one "why this" line, one atmospheric photo. Not a feed — a confident suggestion. "Not feeling it" slides into vibe-first as a refinement layer.
- **New user / cold start (no behavioral data):** Pure vibe-first. Evocative prompts, not form fields. "What are you in the mood for?" style. Loose expressive options (warm + slow, dense + late nights, remote + physical). User's answer seeds a destination shortlist.
- **Destination shortlist size:** Three. Enough for real choice, not enough to recreate paralysis. Each: one atmospheric photo, one line. Tap → into trip planning.
- **Editorial/curation (Model A):** Not a product surface — belongs on the landing page and marketing, not inside the app.
- **Cold-start language:** Never surfaces "you don't have enough data." System delivers whichever experience it can do confidently. The gap is invisible.

---

## ✅ 11. Real-Time Reactivity — Group Complexity

**Status:** RESOLVED

**Summary of decisions:**

**Individual vs. group signal threshold:**
- One member signals low energy → individual signal only. Their next solo slot softens if one exists. Shared slots unchanged. Signal logged, system watches for corroboration.
- Two or more members signal similarly in short window → group signal. System surfaces a gentle suggestion to the group: "a few of you seem to be slowing down — want to ease up the afternoon?" Not automatic, not a unilateral replan.

**Who can trigger a group replan:**
- Anyone can suggest, group confirms. Not organizer-only.
- Any member can raise their hand via input bar or mood signal. System escalates to group for confirmation.
- Nobody unilaterally replans the shared day. Nobody needs organizer permission to suggest a change.
- Distinction: suggest vs. execute. Suggestion is open to all, execution requires group acknowledgment.

**Subgroup split:**
- Fully self-service. Any member can peel off and create their own track at any time, no permission required.
- System detects divergence and quietly offers to plan the solo track.
- Group itinerary continues for whoever stays on it.
- System automatically suggests a reconvene point — usually dinner — as a natural merge.
- Organizer authority applies to shared itinerary decisions, not to physical autonomy. Those are different things.

---

## ✅ 4. Monetization Edge Cases

**Status:** RESOLVED

**Summary of decisions:**

**Free tier cadence:**
- 3 solo trips per year at launch. Planned reduction to 2 per year once paying user base and retention data support it.
- Launch at 3 for acquisition velocity and goodwill. Drop to 2 from a position of strength, not desperation.
- Grandfathering of existing free users at reduction time: future decision with real data.
- Group trips are NEVER free. No exceptions.

**Group trip pricing:**
- Flat group rate for 2–3 members (couples, small groups).
- Per-seat pricing above 4 members — first 4 included in group rate, each additional member adds incremental fee.
- Scales with value delivered. A bachelor party of 10 is worth more than a couple's trip.

**Free users in a group (git branch model):**
- Non-paying member joins via invite link → gets a personal branch of the itinerary for the duration of that trip.
- Full participation within trip context: persona signals, polls, mood/energy flags, itinerary suggestions.
- Trip ends → branch goes stale. Back to free tier constraints, no carry-over group features.
- The organizer's paid trip funded their access. Trip over, access over.
- Conversion moment: "want to vote on tonight's dinner?" → prompt to create account or upgrade.

**Subscription lapse mid-trip:**
- Grace period covers trip duration. Trip stays live for all members until completion.
- Organizer gets payment prompt but access not revoked mid-vacation.
- After trip ends: drops to free tier until payment resolved.

**Past trips on cancellation:**
- Always accessible, always exportable. Trips are memories, memories belong to the user.
- Cancellation drops future capability to free tier. Past itineraries never gated.

**Pay-per-trip unit:**
- Per destination. Plan Tokyo twice, pay twice. Behavioral graph carries over regardless — payment is for the planning service, not the data.

**Trial period:**
- Free tier IS the trial. No separate time-based trial. 3 trips/year is generous enough to feel the product fully.

---

## ✅ 10. Industry Partnership Policy

**Status:** RESOLVED

**Summary of decisions:**
- Affiliate links are acceptable — passive revenue on top of already-good recommendations. We recommend first, monetize the action second. Never the reverse.
- The "tip for our work" model: if a user books a hotel we recommended and we get a cut, that's honest. We didn't change the recommendation to get the cut.
- Sponsored placement — paying to be surfaced — is never acceptable. That corrupts the recommendation.
- Affiliate relationships are invisible to the user. Attribution stays "via Tabelog, 847 local reviews" or equivalent. Never "sponsored" or "partner."
- Acquisition-level partnerships (company trajectory-changing): still open to conversation at that scale. Everything below that threshold: affiliate only, never sponsored placement.

---

## ✅ 12. Competitive Moat

**Status:** RESOLVED — moat is architectural, not a separate product decision.

**The moat:**
- **Behavioral graph:** Starts from zero for any competitor. Compounds with every trip, every signal, every user. Not replicable without time and users.
- **Local source intelligence network:** Tabelog, Naver, Dianping, Reddit scraping infrastructure. The relationships and the extraction quality compound over time. Tourist/local divergence scoring and overrated detector are proprietary outputs of this network.
- **Group dynamics data:** Nobody else is collecting behavioral signals at the group level — affinity matrices, compromise patterns, subgroup split behavior. Unique dataset.

No further decisions needed. The moat is what gets built, not a separate strategic initiative.

---

*✅ ALL ITEMS RESOLVED: 1, 2, 3, 4, 6, 8, 9, 10, 11, 12, Thread 1.*
*Item 5 (onboarding) handled in HTML build thread.*
✅ Item 7 (post-trip experience) RESOLVED.

---

## ✅ 7. Post-Trip Experience Design

**Status:** RESOLVED

**Summary of decisions:**

**The re-engagement moment:**
- Honor what just happened before selling the next thing. First screen after return is the completed trip as a memory artifact, not a "where next?" prompt.
- The day after return is the highest-intent moment in the product lifecycle. Overplanned treats it accordingly.

**Memory artifact — photos + GCS:**
- Users can upload trip photos, tagged to specific slots in the itinerary. "This is us at the ramen place in Shinjuku."
- Storage via GCS buckets. Tagging ties photos to ActivityNodes — passive intelligence signal for the data pipeline.
- A photo of a closed restaurant is data. A packed, vibrant bar confirms venue status. Memory collection doubles as quality signal collection.
- The itinerary becomes a living memory, not just a plan that happened.

**Sharing — three surfaces:**
- **Share to Overplanned user:** Import as a personalized starting point for their own trip to the same destination. Behavioral graph adapts it to them. Social flywheel — good trips seed other good trips.
- **Share via link:** View-only, Overplanned-branded. Signup wall before they can interact, save, or import anything. Acquisition surface.
- **Share to social media:** Native share sheet generates a clean designed visual card — trip name, destination photo, highlights. Not a screenshot, a designed artifact.
- **No document export.** The memory lives in Overplanned intentionally. Trips are memories, memories stay in the product.

**Feedback timing — notification model:**
- Opens app same evening of return → light prompt available immediately, dismissable, no pressure.
- Doesn't open → one push notification timed to mid-afternoon the following day (2–5pm window). Never morning, never buried in overnight notification stack.
- Misses that too → prompt lives in the trip memory view indefinitely, no further pushing. One notification maximum.
- Timing logic reads the return signal and picks the most natural moment. Distinct, calm, intentional — not merged into the noise.

**Feedback sequence:**
- Light sequence, 2–3 taps maximum. Never a survey.
- "How was the overall vibe?" → one word or emoji response.
- "Anything that didn't land?" → open input, optional.
- "Anything we should know for next time?" → optional.
- Framed throughout as "this helps us plan your next trip better." Feedback as investment, not complaint form.
- Feeds Pipeline A (persona update) via weight softening model established in trust & failure recovery doc.
