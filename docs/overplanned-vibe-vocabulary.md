# Overplanned — Vibe Vocabulary

*Locked February 2026*
*42 vibe tags + 2 location flags*

This is the controlled tag set used by Pipeline C extraction, the vibe tagger model, and the two-tower retrieval system. Every ActivityNode gets tagged against this vocabulary. Tags must be extractable from real review text with high confidence — no tag should require inference beyond what a reviewer explicitly or clearly implies.

---

## The Tags

### Pace & Energy
| Tag | Extraction signal |
|---|---|
| `high-energy` | "buzzing", "packed", "non-stop", "exhausting in the best way" |
| `slow-burn` | "no rush", "linger", "lazy afternoon", "took our time" |
| `immersive` | "lost track of time", "completely absorbed", "hours passed" |

### Crowd & Atmosphere
| Tag | Extraction signal |
|---|---|
| `hidden-gem` | "tourists don't know", "stumbled upon", "no signs", "locals keep secret" |
| `iconic-worth-it` | "yes it's touristy but", "worth the hype", "do it once" |
| `locals-only` | "only locals", "no English menu", "no tourists", "neighborhood spot" |

### Food & Drink
| Tag | Extraction signal |
|---|---|
| `destination-meal` | "flew in for this", "best meal of the trip", "reservation months ahead" |
| `street-food` | "street stall", "standing", "paper plate", "vendor" |
| `local-institution` | "been here 40 years", "grandma's recipe", "third generation" |
| `drinks-forward` | "cocktail program", "wine list", "natural wine", "sake selection" |

### Physical & Outdoors
| Tag | Extraction signal |
|---|---|
| `physically-demanding` | "tough hike", "steep", "sore the next day", "bring water" |
| `easy-walk` | "leisurely", "flat", "accessible", "anyone can do it" |
| `nature-immersive` | "surrounded by nature", "no city in sight", "forest", "mountains" |
| `urban-exploration` | "back streets", "alley", "neighborhood wander", "city texture" |

### Culture & Depth
| Tag | Extraction signal |
|---|---|
| `deep-history` | "ancient", "centuries old", "historical significance", "read everything" |
| `contemporary-culture` | "cutting edge", "modern", "current scene", "local artists" |
| `people-watching` | "sit and watch", "great for observing", "theater of life" |
| `hands-on` | "you make it", "workshop", "cooking class", "participatory" |

### Time & Social
| Tag | Extraction signal |
|---|---|
| `late-night` | "after midnight", "night owl", "2am", "stays open late" |
| `early-morning` | "sunrise", "before crowds", "opens at 6", "morning ritual" |
| `solo-friendly` | "great alone", "counter seating", "single travelers", "no awkwardness solo" |
| `group-friendly` | "big tables", "sharable", "great for groups", "loud and fun" |
| `social-scene` | "talked to strangers", "communal tables", "bar culture", "meet people" |
| `low-interaction` | "just you and the thing", "peaceful", "contemplative", "no pressure" |

### Atmosphere & Mood
| Tag | Extraction signal |
|---|---|
| `intimate` | "tiny", "8 seats", "feels personal", "chef talks to you" |
| `lively` | "music", "energy", "buzzing room", "loud in a good way" |
| `offbeat` | "weird", "unexpected", "only in this city", "hard to describe" |
| `scenic` | "views", "beautiful", "photogenic" (but real, not Instagram-bait) |
| `interactive` | "you participate", "they involve you", "not passive" |
| `participatory` | "you make something", "craft", "activity with your hands" |

### Practical
| Tag | Extraction signal |
|---|---|
| `cash-only` | "cash only", "no cards", "bring yen/won/etc" — **surface prominently in UI** |
| `queue-worthy` | "worth the wait", "queue early", "line out the door but fast" |
| `book-ahead` | "reservations essential", "books out weeks", "impossible to walk in" |
| `no-frills` | "plastic chairs", "paper napkins", "don't go for ambiance" |

### Visit Character
| Tag | Extraction signal |
|---|---|
| `repeat-worthy` | "came back every day", "went twice", "would return immediately" |
| `once-in-a-trip` | "do it once", "checked the box", "glad I went, wouldn't repeat" |
| `underrated` | "nobody talks about this", "surprised this isn't more famous" |
| `seasonal` | "cherry blossom season", "summer only", "only in winter" |
| `time-sensitive` | "closes at 2pm", "sells out", "limited hours", "don't miss it" |
| `locals-routine` | "what locals do on a Tuesday", "daily ritual", "not a destination" |

### Cost Character
| Tag | Extraction signal |
|---|---|
| `budget-friendly` | "cheap", "affordable", "great value", "under $10" |
| `mid-range` | "reasonable", "worth the price", "not cheap but fair" |
| `splurge-worthy` | "expensive but worth it", "treat yourself", "special occasion" |
| `free` | "no entry fee", "free", "donation only" |

---

## Location Flags
*Structural — lives on ActivityNode separately from vibe tags. Used by constraint solver for transit estimation and day pacing.*

| Flag | Definition |
|---|---|
| `city-core` | Within the urban center. Walking or short transit from most accommodation. |
| `out-of-city` | Requires dedicated half-day or full-day. Day trip territory. |

---

## Design Rules

**Tag count per ActivityNode:** 3–8 tags maximum. A venue with 12 tags is a venue the system doesn't understand well. Force discipline.

**Tags are positive signals only.** The system recommends *toward* tags, never away from them. Negative signals (tourist trap, overrated) are captured by `tourist_score` and `quality_signals` on the ActivityNode — not by vibe tags.

**Multiple tags can co-exist.** `intimate` + `lively` is valid (a small bar with great energy). `hidden-gem` + `iconic-worth-it` is a contradiction — flag for human review.

**`cash-only` gets special UI treatment.** Displayed prominently on the slot card regardless of other tags. Users need to know before they're standing at the counter.

**Extraction confidence threshold:** A tag is only applied if the LLM extraction scores it ≥ 0.75 confidence. Below that, it's discarded — not applied at low confidence. False positives corrupt the embedding space.

**Location flags are always set.** Every ActivityNode must have exactly one location flag. No nulls.

---

## How Tags Map to Persona Dimensions

| Persona dimension | Strongly correlated tags |
|---|---|
| `adventure_appetite` high | `hidden-gem`, `offbeat`, `urban-exploration`, `physically-demanding`, `underrated` |
| `food_priority` high | `destination-meal`, `local-institution`, `street-food`, `drinks-forward`, `queue-worthy` |
| `pace_preference` low (slow) | `slow-burn`, `low-interaction`, `repeat-worthy`, `locals-routine` |
| `pace_preference` high (packed) | `high-energy`, `once-in-a-trip`, `time-sensitive` |
| `cultural_depth` high | `deep-history`, `contemporary-culture`, `hands-on`, `participatory`, `immersive` |
| `social_energy` high | `social-scene`, `lively`, `group-friendly`, `late-night` |
| `social_energy` low | `solo-friendly`, `low-interaction`, `intimate`, `early-morning` |
| `budget_sensitivity` high | `budget-friendly`, `free`, `no-frills`, `street-food` |
| `budget_sensitivity` low | `splurge-worthy`, `destination-meal`, `book-ahead` |

---

*Last updated: February 2026*
*Owner: Kevin — any additions require explicit sign-off. Tag vocabulary drift corrupts the embedding space.*
