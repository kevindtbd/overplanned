# Overplanned — Trust & Failure Recovery

*Last updated: February 2026*
*Status: All three threads resolved — data failure, accountability/refund, algo misread.*

---

## The Core Position

Overplanned is a paid product making confident recommendations. Confidence requires accountability. We are the first travel recommendation product with a stated quality commitment and a clear recovery path when that commitment breaks.

The honest contract with users: **we stand behind the accuracy of our data. We cannot guarantee you'll love everything we surface — taste is yours. But if we send you somewhere that doesn't exist, is materially wrong, or has fundamentally changed from what we described, we make it right.**

That distinction — data failure vs. experience mismatch — is the foundation of the entire system. Everything flows from it.

---

## Two Failure Categories. Two Different Responses.

### Category 1 — Data Failure
The venue was closed. The address was wrong. The place is now a completely different type of establishment. The information Overplanned had was objectively incorrect at the time of the trip.

This is verifiable. Overplanned can own it. We compensate.

### Category 2 — Experience Mismatch
The place was open. The data was current. The user didn't enjoy it, had an off night, or it wasn't quite their vibe.

This is subjective. Overplanned cannot own this and shouldn't try. We don't compensate — but we listen, and we learn. The user gets demonstrably better recommendations next time. That's the honest trade.

**This distinction must be communicated clearly in the product** — not buried in terms of service, but surfaced naturally in the moment when a user flags something. The UI language at the flag moment should make the distinction feel fair, not defensive.

---

## The Four-Tier Recovery Model

### Tier 1 — Data Failure, Auto-Verifiable
**What it is:** Venue closed and confirmed by external signal (Google Places API, Foursquare, Pipeline C status).

**How it's flagged:** One-tap on the slot card — available both mid-trip and post-trip. "This place was closed" or "Something was wrong here." No form, no explanation required.

**What happens:** System auto-validates against Google Places + Pipeline C status. If confirmed closed: credit issued within 24 hours, no human review needed.

**Credit:** $5 account credit or 20% off next trip purchase — whichever is more relevant to the user's subscription tier. Applied automatically.

**Free tier users:** Credit applies toward first paid upgrade. Turns a failure into a conversion moment, not a loss.

---

### Tier 2 — Data Failure, Not Immediately Verifiable
**What it is:** External signals show the venue as open, but the user reports something materially wrong — wrong address, completely different type of place, closed for private event, fundamentally misrepresented.

**How it's flagged:** Same one-tap flag, but without auto-validation.

**What happens:** Flag goes to a 48-hour review queue. Pipeline C schedules a targeted recrawl of that ActivityNode. If confirmed within 48 hours: credit issued same as Tier 1. If not confirmed: user gets an honest response — "we're looking into it, here's what we found so far" — no credit, but the flag is logged and weighted in the data quality model.

**No credit without confirmation.** This is where the system stays honest — we don't pay out on unverifiable claims, but we take them seriously as data quality signals.

---

### Tier 3 — Experience Mismatch
**What it is:** Place was open, accurate, but the user didn't like it. Bad meal, off night, wrong vibe, overcrowded.

**How it's flagged:** Post-trip feedback capture only — not a mid-trip flag. The prompt is forward-looking, not accusatory: "Anything we should know for next time?" Never "what went wrong?"

**What happens:** Signal captured, weighted in Pipeline A (persona update). The algo softens weight on that category/vibe combination — it does not eliminate the category. No credit, no refund.

**The response in-product:** "Thanks for telling us — we'll use this to tune your next trip." Warm, brief, never dismissive. The implicit promise is next trip is better.

**Never:** A star rating prompt, a form, an apology that implies Overplanned failed when it didn't, or any compensation.

---

### Tier 4 — Broken Trip
**What it is:** Three or more verified Tier 1 failures in a single trip, OR the anchor activity — the primary reason the user took this trip — failed due to bad data.

**How it's flagged:** User contacts support directly. This doesn't happen through the one-tap system — it requires reaching out because it requires human judgment.

**What happens:** Manual review. Prorated refund of that trip's purchase price if the failures are verified. Not account credit — actual refund.

**Threshold is intentionally high.** One bad slot is a credit. A broken trip is a refund. The distinction matters both financially and philosophically — we're not making users fight for reasonable recovery, but we're also not treating every disappointment as a broken product.

---

## Anti-Abuse Architecture

The friction isn't in the claim process — it's in the verification layer. Claiming is easy. Gaming is hard.

**Signal triangulation, not bureaucracy:**

- **External validation first.** Before any Tier 1 credit is issued, Google Places API and Pipeline C status are checked automatically. A venue flagged as open by external signals gets queued for review, not instant credit.

- **Network effect validation.** Multiple users flagging the same ActivityNode in a short window auto-validates each other. Legitimate failures cluster — gaming attempts typically don't. Three independent flags in 48 hours means the credit queue jumps to auto-approve.

- **Claim history tracking.** First claim on an account: full benefit of the doubt, fastest path to credit. Third claim in 6 months: manual review regardless of external signals. High-frequency claimers are flagged — not punished, but watched. The threshold for manual review is set high enough to not penalize users who genuinely have bad luck, and low enough to catch systematic abuse.

- **Free tier cash removal.** Free tier credits apply toward paid upgrades only — never cash, never free-tier perpetuation. Removes the cash-out incentive entirely. The only way to extract value from a credit is to become a paying user, which is the right outcome anyway.

- **Same ActivityNode, multiple claimers.** If User A and User B both flag the same venue in the same trip window, their claims validate each other and both get credit faster. This is the honest version of crowdsourced quality control.

---

## The One-Tap Flag — Design Principles

Available in two places: the slot card during an active trip, and the trip review surface post-trip.

**Mid-trip:** Discreet — not a prominent affordance that invites casual tapping. Accessible via long-press or a secondary action on the slot card. The user who needs it will find it. It shouldn't be the first thing someone sees on a slot card.

**Post-trip:** More prominent. Part of the natural trip review flow. This is where the majority of flags will come from, and it should be easy.

**The language at the flag moment matters.** Two options presented:
- "This place was closed or wrong" → routes to Tier 1/2 data failure path
- "This wasn't quite right for me" → routes to Tier 3 experience mismatch path

The second option should never feel like a consolation prize. The framing: "Tell us what missed — we'll fix your next trip." The action should feel valuable, not punitive.

---

## Credit Model — Full Spec

| Scenario | Credit Type | Amount | Expiry | How Issued |
|---|---|---|---|---|
| Tier 1 verified data failure | Account credit | $5 or 20% next purchase | 12 months | Automatic, 24hr |
| Tier 2 confirmed after review | Account credit | $5 or 20% next purchase | 12 months | Manual, 48-72hr |
| Tier 4 broken trip | Cash refund | Prorated trip purchase | N/A | Manual, support |
| Free tier Tier 1 claim | Upgrade credit | Equivalent value toward paid | 12 months | Automatic, 24hr |

**12-month expiry on all credits.** Long enough to not feel punitive. Short enough to not become a liability. Credits don't stack into cashable amounts — they're applied at next purchase, period.

**20% vs $5 — which applies:** Whichever is more valuable to the user at the moment of redemption. For a $8/month subscriber, 20% = $1.60, so $5 flat wins. For a $50 annual subscriber buying a second trip package, 20% = $10, so percentage wins. System picks automatically.

---

## What We Don't Do

- We don't make users argue for compensation they're owed. If verification confirms a failure, credit is automatic.
- We don't compensate for taste. The system learns from experience mismatch, but doesn't pay out.
- We don't issue cash refunds except for broken trips via Tier 4. Credits keep the relationship alive.
- We don't run complex claims processes for small failures. The operational overhead of reviewing a $5 claim should be lower than the $5 itself.
- We don't penalize users for flagging. A flag is always a gift to the data pipeline, even if it doesn't result in compensation.

---

## Data Freshness — The Prevention Layer

The best trust recovery is a failure that never happens. The freshness model is the prevention layer.

**Confidence decay by source type:**

| Source | Decay rate | Notes |
|---|---|---|
| Google Places API status | Real-time | Always checked at trip activation |
| Tabelog aggregate score | Slow (monthly check) | Living platform, continuously updated |
| Local forum/Reddit thread | Fast (6-month half-life) | Point-in-time opinion, degrades quickly |
| Blog post | Fast (6-month half-life) | Timestamp matters — 2019 blog post is nearly zero weight |
| Cross-reference confidence | Medium (recalculated on new signal) | More sources = slower decay |

**ActivityNode status field:**
- `active` — in recommendation pool
- `unconfirmed_closed` — flagged by user or signal, suppressed from recommendations, Pipeline C crawl queued
- `temporarily_closed` — removed from active trips, retained in data model
- `permanently_closed` — suppressed permanently, ActivityNode archived

Venues in any non-`active` status are suppressed from recommendations immediately, regardless of quality scores. A perfect score on a closed venue is worthless.

**Anomaly-triggered refresh:**
Normal venues: periodic low-frequency refresh (weekly for popular, monthly for long-tail).
Anomaly signals (user flag, sentiment shift in new reviews, check-in failure spike): immediate targeted Pipeline C recrawl regardless of normal refresh schedule.

**Tourist/local divergence as drift signal:**
If a venue's `tourist_score` was 0.2 two years ago and is now 0.7, the venue's character has changed even if its aggregate rating hasn't. This triggers a confidence review — not suppression, but a flag for human review and a softening of the quality signal weighting until fresh local source data confirms current state.

---

## Thread 1 — Algo Misread

The third failure category: the data was accurate, the venue exists, the information was current — but the recommendation was wrong for this specific user. Persona misread, vibe mismatch at the model level, or the trip context wasn't read correctly.

No compensation here. The honest trade: the system learns and next trip is better. But the feedback mechanism and the correction model need to be deliberate.

---

### The Distinction From Data Failure

This matters at the product level because the user-facing response is completely different. Data failure = we got the facts wrong, we owe you. Algo misread = we got the facts right, we misread you. The product should never conflate these — treating an algo misread as a data failure invites compensation for subjectivity, treating a data failure as an algo misread dismisses a legitimate grievance.

The one-tap flag on the slot card offers two paths explicitly:
- "This place was closed or wrong" → data failure path (Tier 1/2)
- "This wasn't quite right for me" → algo misread path (no credit, feedback loop)

The second option is never a consolation prize. The framing matters: "Tell us what missed — we'll fix your next trip." The signal is valuable to the system. The user should feel that.

---

### Signal Timing — Mid-Trip and Post-Trip, Differently Surfaced

**Mid-trip:** A quiet thumbs-down on the slot card. Discreet — not the first thing visible, accessible via secondary action. It logs the signal immediately but doesn't interrupt the day. No acknowledgment in the moment — the user is traveling, not filling out forms. The signal is absorbed silently and the current day continues unchanged.

Mid-trip misread signals are intentionally low-weight in isolation. A single mid-trip thumbs-down is a whisper — the system notes it but doesn't act on it yet. Context is missing: maybe they were tired, maybe it was an off moment, maybe they ended up loving it. The signal gains weight in combination with post-trip confirmation.

**Post-trip:** The fuller signal. Part of the natural trip review flow, more prominent than the mid-trip option. The prompt is open and forward-looking: "Anything we should know for next time?" — never "what went wrong?" The framing positions feedback as building something, not filing a complaint.

Post-trip is where the user can be more specific if they want — not through a form, but through the input bar. "The food spots were too fancy" or "we wanted more active stuff" are natural language inputs that the NLP layer classifies into persona dimension adjustments.

---

### The Weight-Softening Model

**One negative signal:** Softened silently. No acknowledgment, no visible change. The category weight decreases slightly in the persona model. The system continues to surface that category but less prominently and only when other signals are strong.

**Two to three negative signals in the same category within one trip window:** This is the threshold for acknowledgment. One quiet in-product moment — a single line, not a modal, not a notification: *"Noted — we'll adjust your recommendations."* That's it. The line appears once, in context, and disappears. It confirms the signal was received without making a production of it.

That acknowledgment moment is also the implicit invitation: if the user wants to go further — full suppression of a category — they can say so in the input bar right then. "No more hiking, ever" or "skip anything like this" triggers explicit category suppression. If they ignore the acknowledgment line, softening continues silently.

**Explicit removal — the only path to full suppression:** The user has to say it in plain language. Repeated signals alone never fully suppress a category — they only soften it progressively. Full removal requires intent. This protects against the system overcorrecting from a single bad experience, a bad day, or a trip context that won't recur.

---

### No Persona Layer Surfaced to the User

The user never sees a profile of what the system knows about them. No "your pace preference," no persona tags shown back, no Spotify Daylist-style reveal. That register is wrong for Overplanned — it's surveillance-adjacent and makes the intelligence feel like a product feature rather than a natural quality of the recommendations.

The "this gets me" feeling comes through the output, not through showing the user a mirror. The system getting them is demonstrated by the next recommendation being better — not by narrating the adjustment it made.

The one acknowledgment line ("noted — we'll adjust") is the only moment the system references its own learning. Everything else is invisible. That's the design constraint: **show intelligence through quality, not through transparency about the machinery.**

---

### What the Algo Misread Thread Does NOT Warrant

- No credit, no compensation of any kind
- No star rating prompt
- No apology that implies the product failed — a mismatch is not a failure
- No aggressive follow-up or re-engagement prompt ("tell us more about what went wrong")
- No permanent record surfaced to the user of what was adjusted

The system absorbs the signal, adjusts, and delivers. The user experiences the result on the next trip. That's the complete loop.

---

## Status — All Three Threads Resolved

| Thread | Status | Recovery |
|---|---|---|
| Thread 1 — Algo misread | ✅ Resolved | Weight softening, mid + post-trip signal, explicit-only suppression, one quiet acknowledgment |
| Thread 2 — Data wrong | ✅ Resolved | Four-tier model, credit $5/20%, anti-abuse signal triangulation |
| Thread 3 — Accountability | ✅ Resolved | Clear rules, no cash except Tier 4, 12-month expiry, free tier credit toward upgrade |

*Last updated: February 2026*
