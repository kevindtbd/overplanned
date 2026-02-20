# Architecture Addendum — Real-Time Reactivity Layer & Feedback Systems

*Compiled from design session, February 2026*
*Extends Section 8 (Real-Time Reactivity Layer) and Section 6 (Fine-Tuning / Training Strategy)*

---

## Section 8 Update — Real-Time Reactivity Layer (Deep Dive Complete)

The design session resolved the key open questions from Section 8. Architecture decisions below.

### The Unified Drawer Model

The core UX insight with direct architectural implications: **both user-initiated and system-initiated pivots produce the same component and the same signal type.** The distinction is irrelevant to the recommendation engine — what matters is that a slot change event occurred, what triggered it, and what the user did with the suggestion.

```
PivotEvent {
  trigger_type: 'system' | 'user'          // who initiated
  trigger_source: 'venue_closed' | 'weather' | 'mood_signal' | 
                  'transit_delay' | 'cascade' | 'user_text'
  affected_slot_id: string
  suggested_swap_id: string
  user_action: 'accepted' | 'dismissed' | 'ignored' | 
               'selected_alt' | 'expanded_alts'
  time_to_action_ms: number                // latency signal
  feedback: 'up' | 'down' | null          // optional explicit
  cascade_affected_slots: string[]         // downstream slot IDs
}
```

Every PivotEvent feeds Pipeline A (User Understanding) as a behavioral signal. Accept/dismiss/ignore are all implicit feedback. The explicit thumbs up/down is a bonus signal layered on top, never the primary source.

---

### Trigger Classification

Five trigger types, each with different latency budgets and pre-computation needs:

| Trigger | Source | Pre-computable? | Latency budget |
|---------|--------|-----------------|----------------|
| Venue closed | Pipeline C real-time check | Partially (fallbacks cached) | <2s |
| Weather change | Weather API + outdoor slot detector | Yes (fallbacks by category) | <2s |
| User mood signal | NLP on prompt input | No (on-demand) | <3s |
| Transit delay | Transit API + cascade evaluator | Partial | <5s (cascade) |
| Polar opposite pivot | Vibe vector search | No (on-demand) | <3s |

**Pre-cached fallback graph:** For every scheduled activity, pre-compute at trip-generation time:
- 2 adjacent alternatives (same vibe, nearby, different venue)
- 1 polar opposite (vibe vector in opposite direction)
- 1 indoor fallback (for outdoor slots, weather-triggered)

This makes the <2s latency target achievable for the most common triggers (venue closed, weather). Mood-signal pivots require on-demand vector search but have a slightly higher tolerance.

---

### Cascade Evaluation — Selective Re-solve

Do NOT recompute the full day on a single slot change. Instead:

```
def evaluate_cascade(changed_slot, full_day_slots):
    affected = []
    for slot in slots_after(changed_slot):
        if depends_on(slot, changed_slot):  # proximity, meal timing, energy
            affected.append(slot)
        else:
            break  # cascade stops at independent slots
    
    if len(affected) == 0:
        return SwapResult(changed_slot_only=True)
    
    if len(affected) <= 2:
        return SwapResult(selective_resolve=affected)
    
    # 3+ affected: offer full re-solve as opt-in
    return SwapResult(suggest_full_resolve=True, preview=affected[:2])
```

Key rule: **only surface what changed.** If a transit delay pushes lunch 20 minutes but dinner is unaffected, show the lunch adjustment only. Don't mention dinner.

---

### Mood Signal Detection — Active vs. Passive

**Passive signals (no user action required):**
- Skip rate on activity cards (tapping past without engaging)
- Time spent on each slot vs. predicted duration
- Poll response latency (slow = low enthusiasm)
- Group divergence spikes (someone went silent in polls)

**Active signals (user-initiated, low friction):**
- Typed prompt in the input bar (NLP classified)
- Quick emoji tap (optional, one-time offer mid-day if passive signals are ambiguous)

**NLP classification for typed prompts:**
```
mood_classifier_labels = [
  'low_energy',        # "tired", "exhausted", "rest", "slow down"
  'high_energy',       # "wild", "active", "something fun", "let's go"
  'food_focus',        # "hungry", "eat", "something good"
  'weather_response',  # "it's raining", "too hot"
  'cancellation',      # "X is closed", "can't make it"
  'generic_change',    # "change something", "something different"
]
```

For `generic_change` with no strong signal: default to low-energy swap (safer than high-energy; easier to add energy than recover from an overwhelming slot).

---

### Context Drift Guard — Implementation

This is a hard architectural constraint, not a UX preference.

```python
MAX_PIVOT_DEPTH = 1          # slots changed per pivot event, default
MAX_PIVOT_DEPTH_EXPLICIT = 5 # user asks for full rebuild

def apply_pivot(pivot_event, itinerary):
    if pivot_event.trigger_source == 'full_rebuild_requested':
        depth = MAX_PIVOT_DEPTH_EXPLICIT
    else:
        depth = MAX_PIVOT_DEPTH
    
    # Never change more than `depth` slots without explicit user consent
    changes = compute_changes(pivot_event, itinerary)
    if len(changes) > depth:
        changes = changes[:depth]
        flag_remaining_as_suggestion(changes[depth:])
    
    return changes
```

The itinerary must remain recognizable after any single pivot. If the system needs to change 3+ slots to satisfy a constraint, it surfaces this as "this affects your whole afternoon — want me to rebuild it?" — opt-in, never automatic.

---

### Pivot Signals as Training Data

Every PivotEvent is training data for multiple models:

**Ranking model (Pipeline B):** Was the suggested swap accepted? What features predicted acceptance? Build a pivot-acceptance model distinct from the general recommendation ranking model — the signal context is different (urgency, mood, group state mid-trip).

**Persona dimension updates (Pipeline A):**
```
{
  action_type: 'pivot_accepted' | 'pivot_dismissed',
  trigger: 'user_mood_low_energy',
  swap_category: 'pace',         # garden vs walk
  energy_delta: -0.3,            # swap was significantly lower energy
  time_of_day: 'afternoon',
  day_number: 3,                 # fatigue accumulates
}
```
This is richer than a normal accept/reject because it includes the *reason* (mood signal) and the *magnitude* of the vibe shift (how far the swap moved in the embedding space).

**Vibe embedding space:** Accepted pivot pairs (original → swap) with their mood signal context are high-quality training pairs for the two-tower model. "User said tired at 2pm day 3 → accepted garden over street walk" teaches the model that `low_energy_afternoon` shifts user embedding toward `restorative_outdoor`.

---

## Section 6 Addendum — Implicit Feedback Architecture

### The Feedback Hierarchy

From highest signal quality to lowest:

1. **Trip completion + post-trip rating** — was this worth it? Rare, high quality.
2. **Pivot accept/dismiss** — mid-trip, high-intent, contextually rich.
3. **Activity completion** — did they actually go? (GPS or manual check-in)
4. **Slot modification** — user changed time, duration, or swapped themselves.
5. **Poll vote** — what did they vote for in group decisions?
6. **Accept/skip in recommendation scroll** — low intent, high volume.
7. **Explicit thumbs after pivot** — optional, never required.

The explicit thumbs up/down after a pivot accept follows the **one-time offer rule:**
- Shown once per accepted swap
- Auto-dismisses after 4 seconds if ignored
- Ignored = neutral signal (not negative)
- Never shown again for that swap
- Never shown twice in the same hour regardless

### Instagram Reels Model Applied

The behavioral graph does not need explicit ratings to learn. The watch-time equivalent in travel:

| Reels signal | Travel equivalent | What it teaches |
|--------------|-------------------|-----------------|
| Watch 80% | Spent full duration at venue | Activity matched energy/interest |
| Skip after 2s | Dismissed pivot drawer fast | Swap was off-base |
| Share | Added to trip, told group | High confidence positive |
| Not interested | Pivot dismissed + similar rejected next | Category/vibe negative signal |
| Replay | Viewed activity card multiple times | Consideration, not yet commitment |

### YouTube DNN Parallel

From the Covington 2016 paper: implicit feedback (watches) is orders of magnitude more abundant than explicit (ratings). Same here. Design the system to learn primarily from implicit signals, treat explicit ratings as validation data, not the primary training signal.

---

## New Section: Preset Templates & Cold Start Acceleration

*Introduced in design session — not yet in main architecture doc*

### Trip Presets as Behavioral Seed

Before the tag system runs, offer 4–6 preset templates that map directly to persona dimension starting points:

```
TripPreset {
  id: 'couples_slow'
  label: 'Just us, no rush'
  description: 'Two people, slow mornings, good food, long dinners'
  persona_seed: {
    pace_preference: -0.6,      // slow
    social_energy: -0.2,        // semi-private
    food_priority: +0.7,
    adventure_appetite: +0.1,
    planning_preference: -0.3,  // spontaneous-ish
  }
  tag_preselects: ['slow-mornings', 'fine-dining', 'late-nights', 'hidden-gems']
}

TripPreset {
  id: 'group_packed'
  label: 'Everyone, everything'
  description: 'Big group, full days, max experiences'
  persona_seed: {
    pace_preference: +0.6,
    social_energy: +0.8,
    food_priority: +0.3,
    adventure_appetite: +0.5,
    planning_preference: +0.6,  // structured
  }
  tag_preselects: ['packed-days', 'street-food', 'hiking', 'temples', 'markets']
}
```

Presets are not locked — they're a starting point that the tag system and behavioral signals override. The value is accelerating cold start: even one preset selection gives the system a persona seed before any trip behavior is observed.

**Preset × group dynamics:** In a group trip, different members can select different presets. The group affinity matrix seeds from the overlap/divergence between preset selections — "she picked couples_slow, he picked group_packed, divergence is high on pace_preference" is immediately useful for group split logic.

---

## Open Questions Updated

From original Section 9, updated with session findings:

1. **Group dynamics modeling** — still open. Group social surface design session next.
2. **Local source authority** — architecture defined in Pipeline C doc. Implementation ongoing.
3. **Energy curve calibration** — partially addressed by context drift guard (MAX_PIVOT_DEPTH). Full calibration across user types still needed.
4. **Real-time reactivity** — ✅ RESOLVED. Architecture above.
5. **Vibe embedding space** — pivot pairs as training data now documented. Two-tower model approach unchanged.
6. **Overrated detection** — architecture defined. Implementation ongoing.
7. **Cold start** — preset templates partially address. Onboarding screen design pending.
8. **NEW: Feedback loop without burden** — resolved. Implicit-first, one-time explicit offer, never required.
9. **NEW: Context drift guard** — resolved. MAX_PIVOT_DEPTH=1 default, opt-in for full rebuild.
10. **NEW: Generic/landmark balance** — 70/30 heuristic (architecture doc Section 5) applies to pivot suggestions. Swaps should not default to TripAdvisor top 10 when replacing a hidden gem.

---

*Last updated: February 2026*
*Next: Group social surface — fairness tracking, subgroup split logic, compromise modeling*
