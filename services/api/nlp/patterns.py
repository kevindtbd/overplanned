"""
Rule-based pattern definitions for NLP preference extraction.

Each entry in DIMENSION_PATTERNS maps a persona dimension key to a list of
pattern specs. Each spec is a dict with:
  - "pattern":    compiled regex (word-boundary anchored, IGNORECASE)
  - "value":      the dimension value to assign when matched
  - "confidence": float — 0.6 keyword | 0.8 phrase | 0.9 explicit statement
  - "is_phrase":  True when the pattern is a multi-word phrase (for doc clarity)

Dimensions covered by rules (most common in natural language):
  energy_level, social_orientation, budget_orientation,
  food_priority, planning_style, authenticity_preference

Dimensions intentionally left to LLM pass (less common surface forms):
  culture_engagement, nature_preference, nightlife_interest, pace_preference
"""

from __future__ import annotations

import re
from typing import TypedDict


class PatternSpec(TypedDict):
    pattern: re.Pattern[str]
    value: str
    confidence: float
    is_phrase: bool


def _kw(word: str, value: str, confidence: float = 0.6) -> PatternSpec:
    """Compile a single keyword pattern."""
    return PatternSpec(
        pattern=re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE),
        value=value,
        confidence=confidence,
        is_phrase=False,
    )


def _ph(phrase: str, value: str, confidence: float = 0.8) -> PatternSpec:
    """Compile a multi-word phrase pattern."""
    return PatternSpec(
        pattern=re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE),
        value=value,
        confidence=confidence,
        is_phrase=True,
    )


def _ex(phrase: str, value: str) -> PatternSpec:
    """Compile an explicit self-declaration pattern (highest confidence)."""
    return PatternSpec(
        pattern=re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE),
        value=value,
        confidence=0.9,
        is_phrase=True,
    )


# ---------------------------------------------------------------------------
# Pattern registry — ordered from most-specific (phrases/explicit) to
# least-specific (keywords). The extractor checks all patterns and keeps
# the highest-confidence match per dimension value.
# ---------------------------------------------------------------------------

DIMENSION_PATTERNS: dict[str, list[PatternSpec]] = {

    # -------------------------------------------------------------------
    # energy_level
    # -------------------------------------------------------------------
    "energy_level": [
        # explicit self-declarations
        _ex("i am an adventurer", "high_energy"),
        _ex("i love adventure", "high_energy"),
        _ex("i like to relax", "low_energy"),
        _ex("i prefer a relaxed pace", "low_energy"),
        _ex("i am laid back", "low_energy"),

        # phrases (0.8)
        _ph("go with the flow", "low_energy"),
        _ph("take it easy", "low_energy"),
        _ph("chill out", "low_energy"),
        _ph("slow down", "low_energy"),
        _ph("adventure seeker", "high_energy"),
        _ph("thrill seeker", "high_energy"),
        _ph("adrenaline rush", "high_energy"),
        _ph("high energy", "high_energy"),
        _ph("action packed", "high_energy"),
        _ph("packed itinerary", "high_energy"),
        _ph("low key", "low_energy"),
        _ph("low-key", "low_energy"),

        # keywords (0.6)
        _kw("chill", "low_energy"),
        _kw("relaxed", "low_energy"),
        _kw("relaxing", "low_energy"),
        _kw("mellow", "low_energy"),
        _kw("easygoing", "low_energy"),
        _kw("adventure", "high_energy"),
        _kw("adventurous", "high_energy"),
        _kw("thrill", "high_energy"),
        _kw("adrenaline", "high_energy"),
        _kw("energetic", "high_energy"),
        _kw("active", "medium_energy"),
    ],

    # -------------------------------------------------------------------
    # social_orientation
    # -------------------------------------------------------------------
    "social_orientation": [
        # explicit
        _ex("traveling solo", "solo_focused"),
        _ex("travelling solo", "solo_focused"),
        _ex("going alone", "solo_focused"),
        _ex("trip for one", "solo_focused"),
        _ex("solo trip", "solo_focused"),
        _ex("going with friends", "social_explorer"),
        _ex("travelling with friends", "social_explorer"),
        _ex("traveling with friends", "social_explorer"),
        _ex("group trip", "social_explorer"),
        _ex("with my friends", "social_explorer"),

        # phrases (0.8)
        _ph("by myself", "solo_focused"),
        _ph("on my own", "solo_focused"),
        _ph("just me", "solo_focused"),
        _ph("meet locals", "social_explorer"),
        _ph("meet new people", "social_explorer"),
        _ph("with a group", "social_explorer"),
        _ph("with friends", "social_explorer"),
        _ph("small group", "small_group"),
        _ph("just us", "small_group"),
        _ph("couple trip", "small_group"),
        _ph("my partner", "small_group"),
        _ph("with my partner", "small_group"),

        # keywords (0.6)
        _kw("solo", "solo_focused"),
        _kw("alone", "solo_focused"),
        _kw("group", "social_explorer"),
        _kw("social", "social_explorer"),
    ],

    # -------------------------------------------------------------------
    # budget_orientation
    # -------------------------------------------------------------------
    "budget_orientation": [
        # explicit
        _ex("i am on a budget", "budget_conscious"),
        _ex("travelling on a budget", "budget_conscious"),
        _ex("traveling on a budget", "budget_conscious"),
        _ex("money is no object", "premium_seeker"),
        _ex("spare no expense", "premium_seeker"),
        _ex("i love luxury", "premium_seeker"),
        _ex("i prefer luxury", "premium_seeker"),

        # phrases (0.8)
        _ph("on a budget", "budget_conscious"),
        _ph("budget travel", "budget_conscious"),
        _ph("budget friendly", "budget_conscious"),
        _ph("budget-friendly", "budget_conscious"),
        _ph("save money", "budget_conscious"),
        _ph("cheap eats", "budget_conscious"),
        _ph("free things", "budget_conscious"),
        _ph("free activities", "budget_conscious"),
        _ph("luxury hotel", "premium_seeker"),
        _ph("five star", "premium_seeker"),
        _ph("5 star", "premium_seeker"),
        _ph("high end", "premium_seeker"),
        _ph("high-end", "premium_seeker"),
        _ph("treat myself", "premium_seeker"),
        _ph("splurge on", "premium_seeker"),

        # keywords (0.6)
        _kw("cheap", "budget_conscious"),
        _kw("affordable", "budget_conscious"),
        _kw("frugal", "budget_conscious"),
        _kw("inexpensive", "budget_conscious"),
        _kw("splurge", "premium_seeker"),
        _kw("luxury", "premium_seeker"),
        _kw("fancy", "premium_seeker"),
        _kw("upscale", "premium_seeker"),
        _kw("premium", "premium_seeker"),
        _kw("lavish", "premium_seeker"),
    ],

    # -------------------------------------------------------------------
    # food_priority
    # -------------------------------------------------------------------
    "food_priority": [
        # explicit
        _ex("i am a foodie", "food_driven"),
        _ex("i'm a foodie", "food_driven"),
        _ex("food is my priority", "food_driven"),
        _ex("food is everything", "food_driven"),
        _ex("not picky about food", "food_secondary"),
        _ex("not a foodie", "food_secondary"),
        _ex("i'm not picky", "food_secondary"),
        _ex("i am not picky", "food_secondary"),

        # phrases (0.8)
        _ph("must-eat", "food_driven"),
        _ph("must eat", "food_driven"),
        _ph("best restaurants", "food_driven"),
        _ph("food scene", "food_driven"),
        _ph("local cuisine", "food_driven"),
        _ph("culinary experience", "food_driven"),
        _ph("food tour", "food_driven"),
        _ph("food market", "food_driven"),
        _ph("street food", "food_driven"),
        _ph("not picky", "food_secondary"),
        _ph("eat anything", "food_secondary"),
        _ph("food doesn't matter", "food_secondary"),
        _ph("whatever is convenient", "food_secondary"),

        # keywords (0.6)
        _kw("foodie", "food_driven"),
        _kw("gastronomy", "food_driven"),
        _kw("tasting", "food_driven"),
        _kw("cuisine", "food_driven"),
        _kw("chef", "food_driven"),
        _kw("michelin", "food_driven"),
    ],

    # -------------------------------------------------------------------
    # planning_style
    # -------------------------------------------------------------------
    "planning_style": [
        # explicit
        _ex("i love planning", "structured"),
        _ex("i like to plan everything", "structured"),
        _ex("i hate planning", "spontaneous"),
        _ex("i prefer no plans", "spontaneous"),
        _ex("no itinerary", "spontaneous"),

        # phrases (0.8)
        _ph("go with the flow", "spontaneous"),
        _ph("play it by ear", "spontaneous"),
        _ph("no plans", "spontaneous"),
        _ph("wing it", "spontaneous"),
        _ph("plan everything", "structured"),
        _ph("detailed itinerary", "structured"),
        _ph("schedule everything", "structured"),
        _ph("plan ahead", "structured"),
        _ph("book in advance", "structured"),

        # keywords (0.6)
        _kw("spontaneous", "spontaneous"),
        _kw("spontaneously", "spontaneous"),
        _kw("unplanned", "spontaneous"),
        _kw("flexible", "flexible"),
        _kw("improvise", "spontaneous"),
        _kw("structured", "structured"),
        _kw("organised", "structured"),
        _kw("organized", "structured"),
        _kw("schedule", "structured"),
        _kw("itinerary", "structured"),
    ],

    # -------------------------------------------------------------------
    # authenticity_preference
    # -------------------------------------------------------------------
    "authenticity_preference": [
        # explicit
        _ex("i love hidden gems", "authenticity_driven"),
        _ex("i prefer off the beaten path", "authenticity_driven"),
        _ex("i like tourist spots", "mainstream_comfortable"),
        _ex("i enjoy popular attractions", "mainstream_comfortable"),

        # phrases (0.8)
        _ph("off the beaten path", "authenticity_driven"),
        _ph("off the beaten track", "authenticity_driven"),
        _ph("hidden gem", "authenticity_driven"),
        _ph("hidden gems", "authenticity_driven"),
        _ph("local experience", "authenticity_driven"),
        _ph("local food", "authenticity_driven"),
        _ph("local spots", "authenticity_driven"),
        _ph("like a local", "authenticity_driven"),
        _ph("avoid tourists", "authenticity_driven"),
        _ph("tourist trap", "authenticity_driven"),
        _ph("tourist traps", "authenticity_driven"),
        _ph("must see", "mainstream_comfortable"),
        _ph("must-see", "mainstream_comfortable"),
        _ph("famous landmarks", "mainstream_comfortable"),
        _ph("top attractions", "mainstream_comfortable"),
        _ph("popular spots", "mainstream_comfortable"),
        _ph("all the classics", "mainstream_comfortable"),

        # keywords (0.6)
        _kw("authentic", "authenticity_driven"),
        _kw("authenticity", "authenticity_driven"),
        _kw("local", "locally_curious"),
        _kw("genuine", "authenticity_driven"),
        _kw("touristy", "mainstream_comfortable"),
        _kw("mainstream", "mainstream_comfortable"),
        _kw("famous", "mainstream_comfortable"),
        _kw("iconic", "mainstream_comfortable"),
        _kw("popular", "mainstream_comfortable"),
    ],
}

# Ordered list of all valid persona dimension keys (closed enum)
VALID_DIMENSIONS: frozenset[str] = frozenset({
    "energy_level",
    "social_orientation",
    "planning_style",
    "budget_orientation",
    "food_priority",
    "culture_engagement",
    "nature_preference",
    "nightlife_interest",
    "authenticity_preference",
    "pace_preference",
})

# All valid values per dimension (closed enum)
VALID_VALUES: dict[str, frozenset[str]] = {
    "energy_level": frozenset({"low_energy", "medium_energy", "high_energy"}),
    "social_orientation": frozenset({"solo_focused", "small_group", "social_explorer"}),
    "planning_style": frozenset({"spontaneous", "flexible", "structured"}),
    "budget_orientation": frozenset({"budget_conscious", "moderate_spender", "premium_seeker"}),
    "food_priority": frozenset({"food_secondary", "food_balanced", "food_driven"}),
    "culture_engagement": frozenset({"culture_light", "culture_moderate", "culture_immersive"}),
    "nature_preference": frozenset({"urban_focused", "nature_curious", "nature_driven"}),
    "nightlife_interest": frozenset({"early_riser", "balanced_schedule", "nightlife_seeker"}),
    "authenticity_preference": frozenset({"mainstream_comfortable", "locally_curious", "authenticity_driven"}),
    "pace_preference": frozenset({"slow_traveler", "moderate_pace", "fast_paced"}),
}
