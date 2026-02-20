# Overplanned â€” Shared Trip Reports & Itinerary Import
*Feature Deep Dive Â· Research Â· Brainstorm Â· Architecture Â· Agent Review*
*Revised: activity-only payload model + commercial protection*

---

## The Core Philosophy (Revised)

"Oh you're going to Thailand? Here's what we did."

A user shares a link to their past trip. The recipient opens it, sees the list of places, and can pull any of it into their own trip. But here's the key architectural decision:

**What gets shared is a list of activity references. Nothing else.**

No timing. No notes. No persona signal. No energy curves. No vibes. No source attribution on the shared page. No logistics. The shared payload is intentionally barebones â€” a sequence of named places and nothing more.

Everything else â€” the scheduling, the "why this," the source intelligence, the persona fit, the timing, the local context â€” gets filled in fresh from **Overplanned's own data** when the importer pulls it into their trip. The system re-hydrates each activity from `ActivityNode` and runs it through the importer's own persona, their own dates, their own group.

This is the right model for three reasons:

1. **The intelligence belongs to Overplanned, not the sharer.** The value isn't what someone else did â€” it's what Overplanned knows about each activity and how it fits you specifically. The sharer provides the list; Overplanned provides the context.

2. **It protects the sharer.** Their timing, budget signals, logistics, private notes, and persona data never leave their account. They're sharing a list of places. That's it.

3. **It closes the commercial exploitation vector.** A tour operator can't use a shared trip to inject their curated narrative, their pricing, their affiliate framing. They can only contribute a list of venue names â€” which Overplanned then re-renders through its own intelligence. Their influence ends at the activity list.

---

## What Gets Shared vs. What Gets Rebuilt

### The Shared Payload (what travels across the link)

```
SharedActivityList {
  token_id: string
  destination: string           // "Bangkok, Thailand"
  trip_length_days: int         // "7 days" â€” no specific dates

  activities: SharedActivity[]
}

SharedActivity {
  activity_id: string           // reference to ActivityNode in Overplanned's World Knowledge
  day_number: int               // relative position only â€” "Day 3", not a calendar date
  slot_sequence: int            // order within the day (1, 2, 3...)
  owner_tip: string | null      // 160 char max, human voice only, no URLs
                                // the ONE piece of human signal that travels
}
```

That's the entire payload. No slot types. No time windows. No booking states. No notes. No persona summary. No source attribution. No cost data. No energy signals. No group member data.

The `activity_id` is a reference into Overplanned's `ActivityNode` â€” the same record that powers every recommendation in the app. The sharer isn't transmitting the activity's data. They're pointing at something that already exists in Overplanned's system.

If an activity in the shared list doesn't exist in Overplanned's `ActivityNode` (a very obscure venue with no Pipeline C coverage), it gets flagged as `unresolved` and either dropped or queued for a Pipeline C crawl. The sharer cannot inject arbitrary activity data â€” the namespace is closed.

### What Overplanned Rebuilds on Import

When the importer pulls in a shared activity list, Overplanned treats each `activity_id` like any other recommendation candidate and runs it through the full pipeline:

```python
for activity in shared_list.activities:

    # Pull from World Knowledge â€” Overplanned's data, not the sharer's
    node = get_activity_node(activity.activity_id)
    if not node:
        mark_unresolved(activity)
        continue

    # Score against importer's persona â€” fresh, not inherited
    persona_match = score_against_profile(node, importer.preference_vectors)

    # Generate fresh narrative from Overplanned's LLM layer
    narrative = llm_generate_slot_narrative(node, importer.persona_tags)

    # Slot type from Overplanned's classification, not sharer's
    slot_type = classify_slot_type(node.category_tags)

    proposal_pile.add(ProposalItem(
        activity_ref:         node.id,
        source:               'shared_import',
        source_token:         token_id,
        day_hint:             activity.day_number,   # suggestion, not locked
        owner_tip:            activity.owner_tip,    # only human signal that survives
        persona_match_score:  persona_match,
        overplanned_narrative:    narrative,             # Overplanned's voice
        slot_type:            slot_type,             # Overplanned's classification
    ))
```

The `day_hint` is a suggestion â€” "the original person put this on day 3." The constraint solver may move it based on the importer's dates, energy curve, and group constraints. It's information, not instruction.

The `owner_tip` is the only human signal that travels. Everything else is Overplanned.

---

## The Shared View Page

The public page at `overplanned.app/s/:token_id` is intentionally minimal.

### What It Shows

```
Bangkok, Thailand Â· 7-day trip

Day 1
  Â· Wat Pho
  Â· Chatuchak Weekend Market     "go to the plant section first, less crowded"
  Â· Thip Samai Pad Thai

Day 2
  Â· Jim Thompson House
  Â· Chinatown â€” Yaowarat Road    "arrive at dusk, the neon hits different"
  Â· Teens of Thailand bar

[ Use this as a starting point ]     [ Add individual places ]
```

No photos on the shared page. No source attribution. No timing. No "built for a slow couple" framing. No persona context. No cost indicators. No slot type chips.

Just the list. Clean, readable, intentionally sparse.

**Why no photos?** Photos are part of Overplanned's rendering layer â€” pulled from `ActivityNode` and displayed inside the app. The public page doesn't surface Overplanned's intelligence. A competitor scraping the shared page gets: venue names. That's all there is to get.

**Why no source attribution?** "via Tabelog, 847 local reviews" is Overplanned's work product. It belongs in the importer's trip, rendered by Overplanned's system. It has no place on a public page that the sharer doesn't own.

The `owner_tip` is the only human-authored content. It renders inline in a distinct type treatment â€” warmer, clearly personal.

### What It Doesn't Show (and Why)

| Field | Why excluded |
|---|---|
| Photos | Overplanned's rendering layer, in-app only |
| Source attribution | Overplanned's intelligence, not the sharer's to give |
| Persona / vibe summary | Sharer's private behavioral data |
| Timing / time windows | Sharer's logistics, irrelevant to recipient |
| Tourist score / local signals | Overplanned's processed intelligence |
| Slot type labels | Overplanned's classification system |
| Energy curve | Sharer's personal data, meaningless without context |
| Cost actuals | Sharer's financial data |
| Notes | Sharer's private operational data |
| Booking details | Obviously private |

The shared page is a list of places. Overplanned is what makes it useful.

---

## Attribution: Everything Points Back to Overplanned

When a shared activity lands inside the importer's trip, all UI attribution is Overplanned's:

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ [Activity photo â€” from ActivityNode]         â”‚
â”‚                                              â”‚
â”‚ Chatuchak Weekend Market                     â”‚
â”‚ "go weekday morning â€” vendors are chattier,  â”‚  â† Overplanned LLM narrative
â”‚  prices softer before tourist hours"         â”‚
â”‚                                              â”‚
â”‚ via Naver Blog Â· 2,341 local reviews         â”‚  â† Overplanned source attribution
â”‚ â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ â”‚
â”‚ Tip from Alex Â· "go to the plant section     â”‚  â† owner_tip, clearly human
â”‚ first, less crowded"                         â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

The `owner_tip` is visually separated and attributed to a person by name. Everything above the divider is Overplanned's. The sharer contributed a place name and a personal note. Overplanned contributed the photograph, the narrative, the local source intelligence, the persona fit, and the scheduling logic.

**The sharer found a good place. Overplanned knows everything about it.**

This isn't an aesthetic choice â€” it's the product truth, and the UI should reflect it accurately.

---

## The `owner_tip` Field

The only human signal that travels. Design it accordingly:

- **160 character hard limit** â€” forces specificity, prevents promotional copy
- **Plain text only** â€” no markdown, no HTML, no URLs
- **URL = instant strip + account flag** â€” enforced at write time on the server, not at display time
- **Never LLM-generated** â€” must be human-authored or absent entirely
- **Immutable after share** â€” it's a snapshot. Owner cannot edit the tip after the link is created.
- **Attributed on display** â€” "Tip from [first name]" always. Never stripped to anonymous.
- **Optional** â€” no tip is fine. Overplanned fills the gap.

If the owner writes no tip, the activity appears in the shared list with no annotation. The product still works. The tip is a bonus signal, not a required field.

---

## Import Flow

### Granularity

Three levels, same as before, but the payload is the same in all cases â€” only activity references:

**Full list import** â€” creates a new `TripDraft` pre-seeded with all shared activities in the proposal pile. Async job. Returns `202 Accepted`.

**Day import** â€” adds one day's activities to the proposal pile of an existing trip. Synchronous.

**Single activity import** â€” adds one activity to the proposal pile. Synchronous. One tap.

All imports land in the **proposal pile** first. Nothing auto-commits to a scheduled itinerary. The user places deliberately.

### Account-gated import

View is public. Import requires account.

Non-logged-in flow:
```
Tap "Use this as a starting point"
  â†’ "Save this to your trips" bottom sheet
  â†’ Sign up / Log in
  â†’ Account created
  â†’ Import processes async
  â†’ Lands in trip creation with proposal pile pre-seeded
  â†’ Overplanned re-hydrates each activity immediately
  â†’ No onboarding detour â€” value first
```

### API

```
POST   /trips/:trip_id/share
         â†’ creates SharedTripToken, returns share URL

GET    /trips/:trip_id/share
         â†’ list active tokens

DELETE /trips/:trip_id/share/:token_id
         â†’ revoke immediately, synchronous CDN invalidation

GET    /s/:token_id
         â†’ public shared view, no auth, noindex
         â†’ returns static HTML only â€” no ActivityNode data exposed

GET    /s/:token_id/activities
         â†’ auth required â€” returns activity list with Overplanned re-hydration
         â†’ this is the import preview endpoint

POST   /s/:token_id/import
         â†’ auth required
         body: {
           import_type: 'full_list' | 'day' | 'activity',
           scope: { day_numbers?: int[], activity_ids?: string[] },
           destination_trip_id: string | 'new'
         }
```

---

## Commercial Protection Model

### What a bad actor gets from a shared link

A tour operator creates an account and shares a curated trip to promote their preferred venues:

- A public page with venue names and optional 160-char plain-text tips
- No Overplanned intelligence on the public page
- When imported: the importer gets Overplanned's data about those venues â€” Overplanned's narrative, Overplanned's source attribution, Overplanned's persona fit. Not the operator's.
- No mechanism to inject pricing, affiliate framing, or promotional narrative

The shared payload is so stripped down that there's nothing commercially useful in it that isn't already public knowledge. A list of Bangkok venue names is not a competitive asset. Overplanned's processing of those venues is â€” and that never leaves the system.

### Technical Protections

**`noindex` by default.**
All shared pages carry `<meta name="robots" content="noindex, nofollow">` unless the owner explicitly opts in. Opt-in, not opt-out. Commercial actors want search traffic; `noindex` kills the primary SEO exploitation vector immediately.

**Account activity gate.**
Share feature unlocks only after:
- Account is at least 48 hours old
- At least 1 completed trip event (activity checked in, pivot accepted, poll voted)
- No sharing within the first session

New accounts cannot share immediately. The gate is low enough that real users hit it naturally, and high enough that throwaway commercial accounts are slowed.

**URL stripping in `owner_tip`.**
Hard-stripped server-side at write time. Regex + URL parser. Account flagged on first attempt, no warning. The 160-char limit and URL strip together make the tip field commercially useless for affiliate injection.

**Import rate limiting.**

| Scope | Limit |
|---|---|
| Per authenticated account | 10 imports/hour, 3 full_list/day |
| Per IP (unauth view â†’ account creation â†’ import) | 3/day |
| Per token (views) | Flag for review if >500 views/hour |
| Per token (imports) | Flag for review if >50 imports/day |

**The `activity_id` namespace is closed.**
`activity_id` values are internal Overplanned identifiers, not guessable or enumerable from outside the system. A shared link is the only way to transmit an `activity_id` to a non-owner. A commercial actor cannot construct a synthetic payload pointing at venues Overplanned hasn't indexed â€” and Overplanned's indexing is Overplanned's call.

**Behavioral signal quarantine.**
Import events feed the behavioral graph. A coordinated commercial operation creating fake accounts to pump import signals for specific venues is a real attack:
- Import signals from accounts flagged as commercial are quarantined before reaching training pipelines
- Import signals from accounts with no organic behavioral history are down-weighted
- Cluster detection: many accounts importing the same token in a short window â†’ reduce signal weight for all of them

**Static HTML on the public endpoint.**
`GET /s/:token_id` returns static server-rendered HTML. No client-side API calls that expose `ActivityNode` data. No JSON endpoint on the public domain. A scraper hitting the public URL gets HTML with venue names. There is no underlying API to hit.

### What Overplanned Owns

**ToS language (draft):**
> Behavioral data generated through your use of Overplanned â€” including activity selections, poll votes, pivot decisions, import events, and all derived persona and preference signals â€” is proprietary to Overplanned and may not be scraped, exported, reverse-engineered, or used to train or inform competing systems. Activity references shared via trip links are resolved against Overplanned's World Knowledge database. All intelligence, narrative, source attribution, and scoring displayed within the Overplanned application is generated by Overplanned's systems and remains Overplanned's proprietary output regardless of the origin of the activity list.

**What this covers:**
- Behavioral graph and persona vectors â€” server-side, never exported
- Processed `ActivityNode` data (tourist scores, vibe embeddings, quality signals) â€” never in the shared payload
- LLM narrative output â€” attributed to Overplanned in all UI contexts
- Source attribution layer â€” Pipeline C output, in-app only

**What this doesn't cover:**
- Raw venue names â€” public knowledge
- `owner_tip` text â€” user-authored, owned by the user

---

## Resolved Open Questions

**Q1 â€” Social graph / following:** Not v1. `visibility: 'followers_only'` field exists on `SharedTripToken`, dormant.

**Q2 â€” Attribution after modification:** If importer changes `activity_ref` (different venue), attribution clears. If they only move it or retiming it, `source_token` persists. One check at slot mutation: `if new_activity_id != original_activity_id: clear_attribution()`.

**Q3 â€” Circular imports:** Direct source only. No chain. `source_token` points to immediate import event, full stop.

**Q4 â€” Commercial / spam:** Addressed above. Stripped payload is the primary defense. `noindex`, activity gate, URL strip, import rate limiting, behavioral signal quarantine are the supporting layer.

**Q5 â€” Same place, same time:** Requires social graph. Parked.

---

## Remaining Open Questions

**Unresolved activities.** If a shared `activity_id` no longer exists in `ActivityNode` (venue closed, data quality issue), the importer sees a minimal card: venue name + "we couldn't verify this is still open." Not silently dropped â€” the sharer put it there for a reason. Queue a Pipeline C re-check on first encounter.

**Social proof signal from import patterns.** When many users independently import the same activity from different shared lists, that's a quality signal for the `ActivityNode`. A place real users keep recommending to each other, separately, is different from a place with a high review count on TripAdvisor. Design a lightweight input to `ActivityNode.quality_signals` from aggregated import events â€” separated from the behavioral graph so it can't be poisoned by coordinated commercial activity.

**High-trust shared lists in discovery.** A shared list from an account with deep organic behavioral history and many completed trips is meaningfully higher signal than one from a new account. Should these eventually surface in the discovery feed ("someone who travels like you just got back from Kyoto")? Path to Discovery Frame 4 â€” requires trust scoring before shipping.

---

*Last updated: February 2026*
*Core revision: activity-only payload. Sharer provides venue list. Overplanned provides everything else.*
*Depends on: proposal pile (open questions Â§9), ActivityNode schema (build list Â§1.3), Pipeline C (build list Â§6)*
