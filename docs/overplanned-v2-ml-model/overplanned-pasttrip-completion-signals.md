# Past Trip Completion Signals — Behavioral Integrity Spec

*Overplanned Internal · February 2026*  
*Depends on: heuristics-addendum.md §2.1, v2-mobile.md Feature 1 & 2, posttrip.docx §3*

---

## 1. The Problem

When a trip ends, the system has a partially observed picture of what actually happened. The itinerary represents intent. What the user did is a different thing entirely. The gap between planned and actual is one of the most signal-rich surfaces in the product — and also one of the most dangerous to misinterpret.

Treating unattended slots as negative signals is wrong. Treating all attended slots as equally strong positive signals is also wrong. This doc defines exactly how to classify, weight, and surface itinerary completion states — both for ML training pipelines and for the user-facing past trips view.

---

## 2. Slot Outcome Classification

Every planned slot on a completed trip resolves to one of five states. This is already defined in `heuristics-addendum.md §2.1` as the `SlotCompletionSignal` enum. Reproduced and extended here for completeness.

```python
class SlotCompletionSignal(Enum):
    CONFIRMED_ATTENDED   = "confirmed_attended"    # GPS presence confirms attendance (v2 only)
    LIKELY_ATTENDED      = "likely_attended"        # no GPS; no conflicting signal
    CONFIRMED_SKIPPED    = "confirmed_skipped"      # user manually marked skip mid-trip
    PIVOT_REPLACED       = "pivot_replaced"         # a pivot event exists for this slot
    NO_SHOW_AMBIGUOUS    = "no_show_ambiguous"      # no signal of any kind
```

### Classification Logic

```python
def classify_slot_outcome(slot_id: str, trip_id: str, user_id: str) -> SlotCompletionSignal:
    if get_pivot_event_for_slot(slot_id):
        return SlotCompletionSignal.PIVOT_REPLACED

    if get_manual_skip(slot_id, user_id):
        return SlotCompletionSignal.CONFIRMED_SKIPPED

    if get_gps_presence(slot_id, trip_id, user_id):
        return SlotCompletionSignal.CONFIRMED_ATTENDED

    # No positive or negative signal — ambiguous, not absent
    return SlotCompletionSignal.NO_SHOW_AMBIGUOUS
```

`NO_SHOW_AMBIGUOUS` is not a null — it is an unknown. The distinction matters for training. Unknown signals are excluded from training entirely, not zeroed out.

---

## 3. Training Signal Weights

```python
SLOT_OUTCOME_LABEL = {
    SlotCompletionSignal.CONFIRMED_ATTENDED:  1.0,    # strong positive
    SlotCompletionSignal.LIKELY_ATTENDED:     0.6,    # soft positive
    SlotCompletionSignal.CONFIRMED_SKIPPED:  -0.5,    # negative
    SlotCompletionSignal.PIVOT_REPLACED:      None,   # use pivot signal instead; do not double-count
    SlotCompletionSignal.NO_SHOW_AMBIGUOUS:   None,   # excluded from training entirely
}
```

### Why `LIKELY_ATTENDED` is only 0.6

Weather, venue closures, travel delays, and spontaneous itinerary drift all produce false positives in the likely-attended bucket. A user who planned brunch at a coffee shop but actually slept in generates the same signal state as one who went. Until GPS confirms presence (v2), 0.6 is the right prior — optimistic but not blind.

### Why `CONFIRMED_SKIPPED` is -0.5, not -1.0

A confirmed skip during a trip is not a strong rejection signal. The user may have been tired, short on time, or skipping for logistical reasons unrelated to preference. -0.5 soft-signals preference misalignment without eliminating the venue category from future recommendations. One confirmed skip never eliminates a category. Feedback propagates via weight softening, not category elimination.

---

## 4. The `user_added_off_plan` Signal

This is the highest-confidence positive signal in the behavioral model, and currently underdefined.

When a user adds a venue to their active itinerary mid-trip that was **not** in the original plan — a place they discovered on the ground — this represents:

- Genuine enthusiasm (enough to stop and add it)
- Independent discovery (no system suggestion to anchor to)
- Revealed preference at its most unmediated

This should be tracked as a distinct signal type with a training weight above any system-recommended acceptance:

```python
class BehavioralSignalType(Enum):
    # ... existing types ...
    USER_ADDED_OFF_PLAN = "user_added_off_plan"    # user self-sourced during trip

SIGNAL_TYPE_WEIGHTS = {
    # ... existing ...
    "user_added_off_plan":          1.4,    # highest single signal weight
    "card_viewed_then_accepted":    1.0,
    "confirmed_attended":           1.0,
    "likely_attended":              0.6,
    "confirmed_skipped":           -0.5,
}
```

### What to Capture

```python
@dataclass
class OffPlanAddEvent:
    user_id:         str
    trip_id:         str
    occurred_at:     float
    activity_id:     str | None   # matched to ActivityNode if venue is in corpus
    raw_place_name:  str          # always store; match may fail
    source:          str          # 'manual_search' | 'maps_link' | 'photo_tag' | 'unknown'
    trip_day_number: int
    day_part:        str          # morning | afternoon | evening
```

If `activity_id` resolves to an existing `ActivityNode`, route to behavioral write-back as a high-weight positive. If it doesn't (venue not in corpus), flag for Pipeline C ingestion — the user just told you about a local place worth knowing about.

---

## 5. Post-Trip Disambiguation — The Skipped Slot Problem

Mid-trip, a skipped slot is ambiguous. Post-trip is the only moment to resolve genuine uncertainty — but the UX can only ask about high-confidence ambiguity, not every slot.

### The Rule

Only surface the disambiguation question for slots where the system is genuinely uncertain. If 4 slots were skipped and 3 had clear timing constraints already logged, only ask about the 1 that's ambiguous. Asking about every skip is noise and annoyance.

### Disambiguation UX

One passive affordance per ambiguous slot in the past trips view. Not a push notification. Not a modal. A quiet prompt embedded in the trip timeline: **"Did you end up going?"** with a yes / no tap.

- **Yes** → upgrades to `CONFIRMED_ATTENDED` retroactively. Persona update runs with 0.7x weight (retrospective signal discount).
- **No** → upgrades to `CONFIRMED_SKIPPED`. Optionally surfaces a follow-up: *"Timing, or just not your thing?"* — one tap, optional, never required.
- **No response** → slot remains `NO_SHOW_AMBIGUOUS` indefinitely. Excluded from training forever.

### What the Follow-Up Captures

```python
class SkipReason(Enum):
    LOGISTICS   = "logistics"   # time, weather, closed, transport
    PREFERENCE  = "preference"  # genuine dislike or disinterest
    UNKNOWN     = "unknown"     # user didn't specify
```

`LOGISTICS` skips do not update persona dimensions. `PREFERENCE` skips update persona dimensions at soft-negative weight (-0.3). `UNKNOWN` skips update nothing — treated as ambiguous at the preference layer even if classified as confirmed-skipped at the completion layer.

---

## 6. User-Facing Past Trips View

### What Users See

The past trip UI shows the itinerary as planned, with subtle visual state markers:

| State | Visual Treatment |
|---|---|
| CONFIRMED_ATTENDED | Solid checkmark, venue card fully rendered |
| LIKELY_ATTENDED | Soft checkmark (no GPS), venue card fully rendered |
| CONFIRMED_SKIPPED | Muted card, no checkmark, optional skip reason |
| PIVOT_REPLACED | Shows replacement activity, original shown collapsed |
| NO_SHOW_AMBIGUOUS | Neutral card, no marker, "did you go?" affordance |
| USER_ADDED_OFF_PLAN | Highlighted differently — "you added this on the ground" |

### What Users Cannot See

- Raw behavioral signal weights or labels
- ML model versions that ranked recommendations
- Confidence scores on their persona dimensions
- Training inclusion/exclusion status of any signal

### What Users Can Edit

| Element | Editable | Notes |
|---|---|---|
| Trip name / dates | Yes | Cosmetic |
| Photos / notes | Yes | Always |
| Post-trip reflection tags | Yes, within 7 days | Read-only after window closes |
| "Did you go?" disambiguation | Yes, always | Upgrades signal state retroactively |
| Live behavioral signals | No | System-owned, immutable, never exposed |
| Itinerary timestamps | No | Required for decay weighting |

---

## 7. Signal Routing Summary

| Source | Signal Type | Pipeline Destination | Weight |
|---|---|---|---|
| GPS presence during slot | `confirmed_attended` | Pipeline B (ranking model) | 1.0 |
| No GPS, no conflicting signal | `likely_attended` | Pipeline B | 0.6 |
| Manual skip mid-trip | `confirmed_skipped` | Pipeline B | -0.5 |
| Pivot event | `pivot_replaced` | Pipeline B (via pivot signal) | — |
| Post-trip disambiguation: yes | `confirmed_attended` (retro) | Pipeline A (persona) | 0.7 |
| Post-trip disambiguation: no + logistics | `confirmed_skipped` | Excluded from persona | — |
| Post-trip disambiguation: no + preference | `confirmed_skipped` | Pipeline A | -0.3 |
| User off-plan add | `user_added_off_plan` | Pipeline A + B + C | 1.4 |
| Photo tag at venue | Venue status confirmation | Pipeline C (quality signal) | — |
| "Place was wrong" flag | Data quality failure | Pipeline C re-crawl queue | — |

---

## 8. Implementation Notes

### v1 (No Passive GPS)

Without the v2 passive tracker, `CONFIRMED_ATTENDED` is only achievable via manual check-in. Most slots will resolve to `LIKELY_ATTENDED` or `NO_SHOW_AMBIGUOUS`. This is acceptable — the system trains on the signals it has, not the signals it wishes it had. Do not inflate confidence on `LIKELY_ATTENDED` to compensate.

### v2 (Passive GPS Tracker)

The passive tracker resolves a large fraction of ambiguous completions to `CONFIRMED_ATTENDED` or `CONFIRMED_SKIPPED`. Every v2 user with tracking enabled contributes materially higher-fidelity training signals. The migration path: v1 signals remain valid at their original weights; v2 signals simply add higher-confidence entries to the same pipeline.

GPS trace processing:
1. Compress consecutive pings within 50m into a single stay point with duration
2. Classify stays: `in_transit`, `brief_stop` (<10 min), `visit` (10–90 min), `extended_stay` (>90 min)
3. Match `visit` and `extended_stay` points to ActivityNodes within 200m radius
4. Matched stays during slot windows → `CONFIRMED_ATTENDED`

Raw GPS pings are never uploaded. Only compressed stay points. Raw data deleted from device after successful upload. Stay points retained for 90 days post-trip, then deleted. Anonymized aggregate patterns may be retained indefinitely.

### Retroactive Signal Updates

When a user answers a disambiguation question on a past trip, the signal state updates retroactively in `behavioral_signals`. The nightly extraction job re-processes any signals that changed state that day. This means the ranking model can eventually train on cleaned signals from historical trips — but only when the user voluntarily provides the disambiguation. No inference, no backfilling.

---

*Depends on: heuristics-addendum.md, v2-mobile.md, posttrip.docx, bootstrap-deepdive.md §4.5*  
*Next: integrate `user_added_off_plan` into behavioral_signals table schema and Pipeline C ingestion queue*
