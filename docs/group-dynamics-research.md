# Group Social Surface — Research Grounding & Edge Cases

*Compiled February 2026 | Informs group social surface design + Section 1 architecture (Group Dynamics)*

---

## What the Research Actually Says

### 1. Group Typology — Who's in the Group

Academic research on youth travel groups (Wong & Lau 2014, Njagi et al. 2017) identifies four consistent archetypes that map directly onto our persona system:

| Type | Behavior | System implication |
|------|----------|--------------------|
| **Leader** | Drives decisions, prioritizes group comfort over personal preference | High poll influence weight; tends to compromise most. Track burnout. |
| **Follower** | Adapts to group decisions; lowest expressed preference divergence | Don't mistake silence for agreement. Passive poll behavior ≠ satisfaction. |
| **Energizer** | Maintains group morale; suggests activities, keeps momentum | High social energy dimension. Flag if they go quiet — group mood signal. |
| **Loner** | Prefers solitude even within group; needs individual slots | Trigger subgroup split logic. Don't force full-group activities. |

**Design implication:** The group social surface should never label people with these archetypes. Surface behavior through what the system suggests ("JR hasn't weighed in lately — check in?"), not what the system diagnoses.

---

### 2. Fairness — The Core Research Problem

From the group recommender systems literature (Masthoff & Delić 2022, Herzog & Wörndl 2019, Kim et al. IEEE Access 2024), there are three fairness problems to solve:

**Average satisfaction** — maximize the mean. Fast to compute, but systematically screws the outlier. The person with the minority preference gets nothing.

**Least misery** — maximize the minimum. Prevents anyone from being very unhappy, but can produce mediocre outcomes for everyone.

**Envy-free** — no member would prefer another member's allocation. Hardest to compute, most psychologically satisfying.

**What we should use:** A hybrid. Least misery as the floor (no one gets nothing), with running fairness debt tracked across the trip. If SL has gotten her preferred outcome 4 times and Kevin 0, the system actively biases the next uncontested decision toward Kevin — without announcing it.

```python
# Fairness debt tracking
FairnessState {
  per_member: {
    member_id: str,
    times_preferred_outcome_won: int,
    times_compromised: int,
    fairness_debt: float,          # negative = system owes them
    last_win_slot_id: str
  }
}

# When scoring candidates for a flex slot with no strong group preference:
def apply_fairness_adjustment(base_scores, fairness_state, group_context):
    most_owed = max(fairness_state.members, key=lambda m: -m.fairness_debt)
    # Boost candidates that align with most_owed member's preferences
    for candidate in candidates:
        if matches_preference(candidate, most_owed):
            candidate.score *= 1.15   # 15% boost, not a takeover
    return candidates
```

**Critical:** Never surface the fairness debt number to users. No "Kevin's satisfaction score is 42%." Instead, translate into action: "JR picked last time — let's let SL choose the restaurant tonight."

---

### 3. The Spotify Blend Finding (CHI 2024)

Kwak et al. (CHI 2024, 21-day diary study, 15 pairs) found something directly applicable:

> Users engaged in **implicit social interactions** through shared recommendations — inferring companions' moods, emotions, and circumstances from what the system surfaced, without explicit communication.

In travel terms: the itinerary itself is a communication medium. When the system suggests a slow morning cafe instead of a packed temple, members read that as "the system knows someone's tired." The recommendation reveals information about the group's state that individuals might not say aloud.

**Design implication:** The group social surface should lean into this. Show what the day's plan reveals about the group's current state, not just a status dashboard. "Today's plan is slower than yesterday — the system adjusted for where everyone's energy is."

Also from the same study: **ambiguity in the recommendation algorithm enhanced social interaction**. When people didn't know exactly why something was suggested, they talked about it. Don't over-explain.

---

### 4. The Abilene Paradox — Biggest Edge Case

From Harvey (1988), referenced in group travel decision research: a group can collectively choose an outcome nobody individually wanted, because everyone assumed the others wanted it and didn't object.

In travel: "Does anyone actually want to do the Eiffel Tower? No one said no, so it's on the itinerary."

**System response:** The poll design has to make dissent low-friction. Not "vote yes or abstain" but "yes / maybe / not for me." A "not for me" from two members should trigger a quiet flag: "Not everyone's feeling this one — want to see alternatives or split?"

---

### 5. Individual Energy Curves Within a Group

This is the edge case you raised and it's under-researched. Each person has their own energy curve — jet lag, fitness, sleep, health — but they're traveling as a group.

**The problem scenarios:**

*Early fatigue:* One member hits a wall on day 2. Others are fine. Full group slows down or splits.

*Asymmetric fitness:* Hiking day planned. One member has knee issues. They said nothing at planning stage.

*Sleep schedule mismatch:* Night owl wants 11pm izakaya. Early riser is done by 9pm. Both voted yes to a late dinner — but for different reasons.

*Cumulative vs. acute fatigue:* One member is consistently lower energy across all days (introvert recharge deficit). Another crashes suddenly after one intense day. These need different responses — drift the schedule vs. insert a recovery slot.

**Architectural response:**

```python
# Individual energy tracking within group context
MemberEnergyState {
  member_id: str,
  current_energy_estimate: float,    # 0–1, updated by signals
  fatigue_trajectory: 'stable' | 'declining' | 'recovering',
  recovery_slots_today: int,
  personal_hard_constraints: [],     # mobility, dietary, schedule
  energy_delta_vs_group: float,      # how far off the group mean
}

# When delta > 0.3, trigger subgroup split evaluation
# When delta < 0 AND declining, flag for solo recovery slot
```

**Signal sources for individual energy:**
- Self-reported via prompt input ("I need a break")
- Poll response latency (slow = low enthusiasm or low energy)
- Slot modification by that member specifically (moved, shortened)
- Passive: check-in timing relative to scheduled start (late = dragging)

---

### 6. Group Shared Logistics — Todos, Packing, Dependencies

This was not in the original architecture and needs a home. The research gap here is real — most group rec systems ignore logistics entirely.

**The dependency problem:** SL is carrying the portable charger everyone needs. JR has the hotel key. Kevin booked a restaurant that requires group payment upfront. These create invisible dependencies that can cascade if someone deviates from the plan.

**Edge cases:**
- Packing item needed by multiple people (sunscreen, adapters, first aid)
- Pre-purchased tickets that lock in a time (non-flexible anchors)
- Someone on a different dietary requirement that affects restaurant selection for whole group
- One member has mobility constraint that affects routing for everyone (stair-heavy neighborhood)

**Proposed data model addition:**

```python
# Extend GroupNode with logistics layer
GroupLogistics {
  shared_items: [
    {
      item: str,
      holder: member_id,
      needed_by: [member_id],
      needed_at_slot: slot_id,       # when it matters
    }
  ],
  pre_purchased: [
    {
      slot_id: str,
      paid_by: member_id,
      amount: float,
      affects_members: [member_id],
      locked: True                   # can't be moved without consequence
    }
  ],
  dietary_constraints_affecting_group: [
    {
      member_id: str,
      constraint: str,               # 'halal', 'vegan', 'nut allergy'
      affects_all_meals: bool
    }
  ],
  mobility_constraints: [
    {
      member_id: str,
      constraint: 'no_stairs' | 'slow_pace' | 'wheelchair',
      affects_routing: bool
    }
  ]
}
```

**Surface in UI:** Group logistics shouldn't live on the main itinerary screen. It's a secondary panel — "things to sort before you go" — not clutter on the day view. One pre-trip prompt per item, resolved before departure.

---

### 7. Aggregation Strategy — When to Use What

From Kim et al. (IEEE Access 2024) and the broader group recommender literature:

| Situation | Best aggregation |
|-----------|-----------------|
| High group agreement (>70% alignment) | Average — just pick the consensus |
| Moderate divergence (30–70%) | Least misery — avoid the worst outcomes |
| High divergence (>70%) | Envy-free or subgroup split |
| One member with hard constraint | Constraint-first, then optimize |
| Fatigue detected in member(s) | Least misery weighted toward low-energy options |

**The 30% threshold** from the main architecture doc aligns with the research. Below 30% divergence, go with the crowd. Above it, the system needs to do more work.

---

### 8. The "Leader Burnout" Edge Case

Research on group travel shows leaders consistently prioritize group comfort over their own preferences. Over a 7-day trip, this accumulates. By day 4–5, the leader is the one who's been compromising most.

**The system should detect this:** If one member's poll choices have aligned with the group outcome at above 60% rate but their *initial* preference diverged — they're accommodating, not naturally aligned. The system tracks this as accumulated fairness debt and starts nudging outcomes their way without announcement.

**The danger:** Don't manufacture conflict. If someone is genuinely fine with whatever, don't assume they're hiding preferences. Signal detection threshold should require 3+ compromise events before triggering the fairness nudge.

---

### 9. References for Architecture Doc

**Core:**
- Masthoff, J. & Delić, A. (2022). Group recommender systems: beyond preference aggregation. *Recommender Systems Handbook.* Springer. — The definitive reference for our fairness model.
- Kim, J.K. et al. (2024). A Group Travel Recommender System Based on Group Approximate Constraint Satisfaction. *IEEE Access, 12*, 96113–96125. — Constraint satisfaction approach directly applicable to our itinerary solver.
- Kwak, D. et al. (2024). Investigating the Potential of Group Recommendation Systems As a Medium of Social Interactions: A Case of Spotify Blend. *CHI 2024.* — The social catalyst finding; ambiguity enhances interaction.
- Herzog, F. & Wörndl, W. (2019). Individual fairness in group recommendations. — Distributed GRS that aggregates preferences fairly with open preference discussion.
- Harvey, J.B. (1988). The Abilene Paradox. *Organizational Dynamics.* — The theoretical basis for our dissent-friendly poll design.

**Supporting:**
- Nguyen, T.N. et al. (2019). Conflict resolution in group decision making. *User Modeling and User-Adapted Interaction, 29*, 895–941.
- Su, L. et al. (2021). How Do Group Size and Group Familiarity Influence Tourist Satisfaction? *Journal of Travel Research.* — Group size effects on interaction dynamics.
- Wong & Lau / Njagi et al. (2014–2017). Group typology research (Leaders, Followers, Energizers, Loners). — Basis for our informal persona naming system.

---

## What This Means for the Group Social Surface Design

**What the screen shows:**
1. Today's group energy state — not individual scores, the gestalt. "Running a bit slower today — the plan reflects that."
2. Poll history for today's slots — who voted what, without judgment
3. Fairness summary — "SL's been flexible all trip. Tonight's dinner pick is hers." Language, not data.
4. Active logistics — things that need resolving before the next slot
5. Subgroup suggestion — only surfaces when divergence is high and a split makes logistical sense

**What it never shows:**
- Individual satisfaction percentages
- Who's been "winning" in a competitive framing
- Algorithmic reasoning ("the system calculated...")
- Anything that could create social awkwardness if someone else saw it

**The tone:** The warmest screen in the app. Not a dashboard. More like a group chat that already knows the context.

---

*Next session: Build the group social surface UI on top of v4 base*


---

## Session 2 — Design Principles & Data Science Decisions

*February 2026 — pre-build session for group social surface*

---

### The Product's Role: Invisible Glue

The defining principle for this screen — and for group dynamics modeling broadly:

**The app is the glue. The participants feel the cohesion.**

The system does the work. The group gets the credit. Nobody should leave a trip thinking "the app managed our dynamics well." They should think "we actually traveled really well together." The product succeeds when it disappears.

This has direct architectural implications. Every fairness rebalancing, every passive member nudge, every budget-sensitive suggestion — these happen invisibly. The surface only ever shows forward-facing actions and natural language state. Never the mechanics.

---

### Fairness Language — Resolved

**Rule:** Track everything, surface nothing about the tracking. Surface action, not analysis.

**Not this (therapist mode):**
> "SL has compromised 4 times this trip — it's her turn."

**This (agency mode):**
> "SL, what are you feeling for dinner tonight?"

Same fairness logic underneath. Different surface entirely. The first makes social debt visible and creates obligation. The second just feels like the app asked the right person at the right moment.

**When fairness logic is completely invisible:** When the group has no accumulated debt and no conflict. The system only acts when there's something to rebalance. Calm default. Active only when needed.

**Language register for all fairness-adjacent surfaces:**
- Forward-facing, never retrospective
- Addresses the individual by name, casually
- Sounds like a friend who's been paying attention, not a mediator
- Never explains its own reasoning

---

### Passive Member — Two Distinct Profiles

Do not treat silence as a deficit to fix. Distinguish by completion signals:

**Disengaged silence:**
- Low poll participation + declining completion signals (late arrivals, early departures, slot modifications)
- Energy delta vs. group mean is negative and worsening
- System response: one low-friction surface moment. "JR, anything you want to add for tomorrow?" Once. Never repeated.

**Content follower:**
- Low poll participation + strong completion signals (shows up, stays, no modifications)
- `planning_preference` dimension score is genuinely low — they're a follower by choice
- System response: leave them alone. Ensure fairness logic doesn't default-deprioritize them.

**Behavioral signal that separates them:**
```python
def classify_silence(member, trip_signals):
    participation_rate = member.poll_votes / total_polls
    completion_enthusiasm = avg(member.slot_completion_signals)
    energy_trend = member.energy_trajectory  # 'stable' | 'declining'

    if participation_rate < 0.3 and completion_enthusiasm < 0.5:
        return 'disengaged'   # worth a gentle nudge
    if participation_rate < 0.3 and completion_enthusiasm > 0.7:
        return 'content_follower'  # leave alone
    return 'normal'
```

**Trip-level vs. person-level following:**
Follower behavior is trip-contextual, not a permanent trait. Someone deferring in a partner's home city is not a follower by nature. Confidence decay back to neutral across trips. `planning_preference` dimension uses standard decay function from Section 7.

---

### Budget — Inferred, Never Disclosed

**Architecture decision: budget is a behavioral signal, not a form field.**

Never ask for a number. Never compare members' budgets to each other. Never surface budget reasoning to the group.

**Passive signal collection (already in behavioral graph):**
```python
budget_signals = [
    'cost_tier_selection',        # which tier chosen when given options
    'restaurant_modification',    # swapped to cheaper option themselves
    'splurge_suggestion_response',# dismissed or accepted
    'actual_vs_suggested_venue',  # went somewhere cheaper nearby
    'slot_cost_modification'      # changed duration/cost of booked activity
]
```

**For groups:** default to lowest detected budget ceiling across members. Never the average. Never disclosed.

**The one pre-trip surface:** During trip creation, a single framing question — not "what's your budget" but a vibe question mapped to preset seeds:

```
"How are you thinking about spending on this trip?"
→ "Keeping it lean"         maps to: budget_sensitivity: +0.7
→ "Mix of splurge and save" maps to: budget_sensitivity: +0.2
→ "Not really counting"     maps to: budget_sensitivity: -0.3
```

Framed as vibe. Maps to behavioral seed. Nobody interrogated. Behavioral tracking does the rest.

**The group never has the money conversation unless they choose to.**

---

### Individual Energy Curves Within Group — Data Model

```python
MemberEnergyState {
  member_id: str,
  current_energy: float,           # 0–1, signal-updated
  trajectory: 'stable' | 'declining' | 'recovering',
  fatigue_type: 'acute' | 'chronic' | None,
  recovery_slots_today: int,
  energy_delta_vs_group: float,    # deviation from group mean

  # Signals feeding this estimate
  last_signals: [
    'self_report',                 # typed "I'm tired"
    'poll_latency',                # slow response = low enthusiasm
    'slot_modification',           # shortened or moved a slot
    'checkin_timing',              # late arrival to scheduled activity
    'completion_rate'              # left early
  ]
}

# Trigger logic
if abs(member.energy_delta_vs_group) > 0.3:
    evaluate_subgroup_split()

if member.fatigue_type == 'chronic':
    # Don't just insert recovery slots — flag for solo time suggestion
    # "JR's been running at a different pace — worth building in
    #  some independent time tomorrow?"
    
if member.fatigue_type == 'acute':
    # Insert single recovery slot, re-evaluate next signal
```

**Acute vs. chronic distinction matters:**
- Acute: single bad day, insert recovery slot, monitor
- Chronic: structural mismatch with group pace, needs solo time logic, not just breaks

---

### Fairness Debt — Full Data Model

```python
FairnessState {
  per_member: {
    member_id: str,
    preference_wins: int,          # times their preferred outcome won
    compromises: int,              # times they deferred to group
    fairness_debt: float,          # negative = system owes them
    debt_confidence: float,        # how sure we are (low if content follower)
    last_win_slot_id: str,
    suppress_rebalance: bool       # true if classified as content follower
  }
}

def apply_fairness_adjustment(candidates, fairness_state):
    # Only activate if debt_confidence > 0.6
    # (don't rebalance toward someone we think is a content follower)
    owed = [m for m in fairness_state.members 
            if m.fairness_debt < -1.5 
            and m.debt_confidence > 0.6
            and not m.suppress_rebalance]
    
    if not owed:
        return candidates   # no adjustment needed
    
    most_owed = min(owed, key=lambda m: m.fairness_debt)
    for c in candidates:
        if matches_preference(c, most_owed):
            c.score *= 1.15   # 15% boost — nudge, not override
    return candidates
```

**Surface translation:**
```
fairness_debt < -2.0  →  "[Name], what are you feeling for X tonight?"
fairness_debt < -1.0  →  Route next uncontested flex slot toward their preferences silently
fairness_debt >= 0    →  No action
```

Never surface the number. Translate to action or a single natural language prompt.

---

### Group Logistics Data Model

New addition to GroupNode — not in original architecture doc.

```python
GroupLogistics {
  shared_items: [{
    item: str,
    holder: member_id,
    needed_by: [member_id],
    needed_at_slot: slot_id,
    resolved: bool
  }],

  pre_purchased: [{
    slot_id: str,
    paid_by: member_id,
    total_amount: float,
    locked: True              # cannot be moved without flagging
  }],

  group_constraints: [{
    member_id: str,
    type: 'dietary' | 'mobility' | 'schedule',
    constraint: str,          # 'vegan', 'no_stairs', 'flight_at_14:00'
    affects_routing: bool,
    affects_all_meals: bool
  }]
}
```

**Surface rule:** Logistics surface only when relevant to an upcoming slot. Not a persistent checklist. Background presence, foreground only when something needs attention.

---

### The Group Affinity Matrix — How It Seeds and Updates

```python
GroupAffinityMatrix {
  # Pairwise similarity scores between members
  pairs: {
    (member_a, member_b): {
      preference_similarity: float,   # from poll overlap
      energy_compatibility: float,    # from pace signals
      budget_compatibility: float,    # from inferred budget signals
      historical_agreement: float,    # across past trips together
      subgroup_tendency: float        # how often they split together
    }
  }
}
```

**Seeds from:**
1. Preset template selection overlap/divergence at trip creation
2. Onboarding tag selection similarity
3. First 3 polls of the trip (fast initial calibration)

**Updates from:**
- Every poll vote (preference similarity)
- Subgroup formations (who goes with whom)
- Energy co-movement (do they fatigue at the same rate)
- Shared modification patterns (do they both swap the same kinds of slots)

**Used for:**
- Subgroup split suggestions ("you and SL tend to align on pace")
- Conflict prediction (high divergence pair + contested slot = flag early)
- Cold start on new trips together (past affinity matrix seeds new trip)

---

### What the Group Social Screen Must Communicate

Three layers, in order of warmth:

**1. The group's state — one line, no metrics**
LLM synthesis from: energy states, fairness state, day number, completion signals.
Examples:
- "Three days in, everyone's hitting their stride."
- "Today's plan is a bit gentler — felt like the right call."
- "You've got a big day tomorrow. Tonight's low-key."

Never: percentages, scores, "the algorithm adjusted for..."

**2. Forward-facing moments — agency, not reporting**
Only surfaces when the system needs a human decision or wants to hand agency to someone.
Examples:
- "SL, what are you feeling for dinner tonight?" (fairness rebalance)
- "JR hasn't weighed in on tomorrow — anything to add?" (disengagement nudge, once)
- "Nobody's strongly feeling the temple — want to rethink it together?" (Abilene antidote)

**3. Quiet logistics — background, foreground only when needed**
Pre-trip: one prompt per unresolved item before departure.
Mid-trip: surfaces only when a slot is approaching and something needs attention.
Never: a persistent checklist visible at all times.

---

### References Added This Session

- Harvey, J.B. (1988). The Abilene Paradox. *Organizational Dynamics.* — Basis for dissent-friendly poll design ("not for me" option).
- Kwak, D. et al. (CHI 2024). Spotify Blend group dynamics study. — GRS as social catalyst; ambiguity prompts human connection; completion signals distinguish follower types.
- Masthoff & Delić (2022). Group recommender systems. — Fairness aggregation strategies (least misery floor + envy-free ideal).
- Kim et al. (IEEE Access 2024). Group approximate constraint satisfaction. — Constraint-first aggregation for hard member constraints.

---
*Next: Build group social surface UI on v4 base*
