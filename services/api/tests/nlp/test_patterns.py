"""
Unit tests for the rule-based pattern definitions in nlp/patterns.py.

Covers:
- Each pattern category fires in isolation
- No false positives on common travel text
- Regression: "I love exploring local food markets" extracts food_driven + authenticity_driven
- Pattern structure integrity (valid values, compiled regexes)
"""

from __future__ import annotations

import re

import pytest

from services.api.nlp.patterns import (
    DIMENSION_PATTERNS,
    VALID_DIMENSIONS,
    VALID_VALUES,
    PatternSpec,
)


# ---------------------------------------------------------------------------
# Pattern structure integrity
# ---------------------------------------------------------------------------

class TestPatternStructure:
    """Every pattern spec must be well-formed."""

    def test_all_dimensions_have_patterns(self):
        """Dimensions covered by rules should be a non-empty subset."""
        assert len(DIMENSION_PATTERNS) > 0

    def test_all_pattern_dimensions_are_valid(self):
        for dim in DIMENSION_PATTERNS:
            assert dim in VALID_DIMENSIONS, f"Rogue dimension in patterns: {dim!r}"

    def test_all_pattern_specs_have_required_keys(self):
        for dim, specs in DIMENSION_PATTERNS.items():
            for spec in specs:
                assert "pattern" in spec, f"Missing 'pattern' in {dim} spec"
                assert "value" in spec, f"Missing 'value' in {dim} spec"
                assert "confidence" in spec, f"Missing 'confidence' in {dim} spec"
                assert "is_phrase" in spec, f"Missing 'is_phrase' in {dim} spec"

    def test_all_pattern_regexes_are_compiled(self):
        for dim, specs in DIMENSION_PATTERNS.items():
            for spec in specs:
                assert isinstance(spec["pattern"], re.Pattern), (
                    f"Pattern in {dim} is not a compiled regex"
                )

    def test_all_confidence_values_in_range(self):
        for dim, specs in DIMENSION_PATTERNS.items():
            for spec in specs:
                conf = spec["confidence"]
                assert 0.0 <= conf <= 1.0, (
                    f"Confidence {conf} out of range in {dim}"
                )

    def test_all_pattern_values_are_valid_for_dimension(self):
        """Every pattern's value must be in the closed enum for its dimension."""
        for dim, specs in DIMENSION_PATTERNS.items():
            valid_vals = VALID_VALUES.get(dim, frozenset())
            for spec in specs:
                val = spec["value"]
                assert val in valid_vals, (
                    f"Value {val!r} not valid for dimension {dim!r}. "
                    f"Valid: {sorted(valid_vals)}"
                )

    def test_valid_dimensions_complete(self):
        """Exactly 10 persona dimensions."""
        assert len(VALID_DIMENSIONS) == 10

    def test_valid_values_all_dimensions_covered(self):
        for dim in VALID_DIMENSIONS:
            assert dim in VALID_VALUES, f"No valid values for dimension {dim!r}"
            assert len(VALID_VALUES[dim]) > 0, f"Empty valid values for {dim!r}"


# ---------------------------------------------------------------------------
# energy_level patterns
# ---------------------------------------------------------------------------

class TestEnergyLevelPatterns:
    """energy_level patterns fire and don't cross-contaminate."""

    def _find(self, text: str, value: str) -> bool:
        specs = DIMENSION_PATTERNS["energy_level"]
        return any(
            spec["value"] == value and spec["pattern"].search(text)
            for spec in specs
        )

    def test_chill_matches_low_energy(self):
        assert self._find("I want a chill trip", "low_energy")

    def test_relaxed_matches_low_energy(self):
        assert self._find("I prefer a relaxed pace", "low_energy")

    def test_low_key_matches_low_energy(self):
        assert self._find("I like low-key destinations", "low_energy")

    def test_adventure_matches_high_energy(self):
        assert self._find("I love adventure and hiking", "high_energy")

    def test_adrenaline_matches_high_energy(self):
        assert self._find("adrenaline rush is what I seek", "high_energy")

    def test_thrill_matches_high_energy(self):
        assert self._find("thrill seeker looking for extreme sports", "high_energy")

    def test_relaxing_matches_low_energy(self):
        assert self._find("I want something relaxing", "low_energy")

    def test_neutral_text_no_energy_match(self):
        # Generic travel text should not match energy_level
        text = "I am planning a two week trip to Japan in April."
        any_match = any(
            spec["pattern"].search(text)
            for spec in DIMENSION_PATTERNS["energy_level"]
        )
        assert not any_match


# ---------------------------------------------------------------------------
# social_orientation patterns
# ---------------------------------------------------------------------------

class TestSocialOrientationPatterns:
    def _find(self, text: str, value: str) -> bool:
        specs = DIMENSION_PATTERNS["social_orientation"]
        return any(
            spec["value"] == value and spec["pattern"].search(text)
            for spec in specs
        )

    def test_solo_matches_solo_focused(self):
        assert self._find("I am going solo", "solo_focused")

    def test_by_myself_matches_solo_focused(self):
        assert self._find("traveling by myself for two weeks", "solo_focused")

    def test_alone_matches_solo_focused(self):
        assert self._find("I prefer going alone", "solo_focused")

    def test_with_friends_matches_social_explorer(self):
        assert self._find("going with friends to Tokyo", "social_explorer")

    def test_group_matches_social_explorer(self):
        assert self._find("group trip of eight people", "social_explorer")

    def test_small_group_matches_small_group(self):
        assert self._find("just a small group of three", "small_group")

    def test_my_partner_matches_small_group(self):
        assert self._find("travelling with my partner", "small_group")

    def test_consolation_not_solo(self):
        """Word boundary: 'consolation' must NOT match 'solo'."""
        assert not self._find("it was a consolation prize", "solo_focused")


# ---------------------------------------------------------------------------
# budget_orientation patterns
# ---------------------------------------------------------------------------

class TestBudgetOrientationPatterns:
    def _find(self, text: str, value: str) -> bool:
        specs = DIMENSION_PATTERNS["budget_orientation"]
        return any(
            spec["value"] == value and spec["pattern"].search(text)
            for spec in specs
        )

    def test_cheap_matches_budget_conscious(self):
        assert self._find("looking for cheap flights and hostels", "budget_conscious")

    def test_on_a_budget_matches_budget_conscious(self):
        assert self._find("I am traveling on a budget", "budget_conscious")

    def test_affordable_matches_budget_conscious(self):
        assert self._find("I want affordable options", "budget_conscious")

    def test_splurge_matches_premium_seeker(self):
        assert self._find("I want to splurge on this trip", "premium_seeker")

    def test_luxury_matches_premium_seeker(self):
        assert self._find("luxury hotels only please", "premium_seeker")

    def test_fancy_matches_premium_seeker(self):
        assert self._find("I like fancy restaurants", "premium_seeker")

    def test_high_end_matches_premium_seeker(self):
        assert self._find("looking for high-end experiences", "premium_seeker")

    def test_neutral_price_text_no_match(self):
        text = "I want to visit some restaurants and museums."
        any_match = any(
            spec["pattern"].search(text)
            for spec in DIMENSION_PATTERNS["budget_orientation"]
        )
        assert not any_match


# ---------------------------------------------------------------------------
# food_priority patterns
# ---------------------------------------------------------------------------

class TestFoodPriorityPatterns:
    def _find(self, text: str, value: str) -> bool:
        specs = DIMENSION_PATTERNS["food_priority"]
        return any(
            spec["value"] == value and spec["pattern"].search(text)
            for spec in specs
        )

    def test_foodie_matches_food_driven(self):
        assert self._find("I am a foodie", "food_driven")

    def test_must_eat_matches_food_driven(self):
        assert self._find("Tell me the must-eat spots", "food_driven")

    def test_best_restaurants_matches_food_driven(self):
        assert self._find("I want to know the best restaurants", "food_driven")

    def test_street_food_matches_food_driven(self):
        assert self._find("I love street food", "food_driven")

    def test_not_picky_matches_food_secondary(self):
        assert self._find("I am not picky about food", "food_secondary")

    def test_eat_anything_matches_food_secondary(self):
        assert self._find("I can eat anything really", "food_secondary")

    def test_food_market_matches_food_driven(self):
        assert self._find("I love exploring local food markets", "food_driven")


# ---------------------------------------------------------------------------
# planning_style patterns
# ---------------------------------------------------------------------------

class TestPlanningStylePatterns:
    def _find(self, text: str, value: str) -> bool:
        specs = DIMENSION_PATTERNS["planning_style"]
        return any(
            spec["value"] == value and spec["pattern"].search(text)
            for spec in specs
        )

    def test_spontaneous_matches_spontaneous(self):
        assert self._find("I am a spontaneous traveler", "spontaneous")

    def test_go_with_flow_matches_spontaneous(self):
        assert self._find("I like to go with the flow", "spontaneous")

    def test_wing_it_matches_spontaneous(self):
        assert self._find("I usually just wing it", "spontaneous")

    def test_schedule_matches_structured(self):
        assert self._find("I want a detailed schedule", "structured")

    def test_plan_everything_matches_structured(self):
        assert self._find("I like to plan everything in advance", "structured")

    def test_flexible_matches_flexible(self):
        assert self._find("I prefer to stay flexible", "flexible")

    def test_organised_matches_structured(self):
        assert self._find("I am very organised", "structured")


# ---------------------------------------------------------------------------
# authenticity_preference patterns
# ---------------------------------------------------------------------------

class TestAuthenticityPreferencePatterns:
    def _find(self, text: str, value: str) -> bool:
        specs = DIMENSION_PATTERNS["authenticity_preference"]
        return any(
            spec["value"] == value and spec["pattern"].search(text)
            for spec in specs
        )

    def test_off_beaten_path_matches_authenticity_driven(self):
        assert self._find("I want to go off the beaten path", "authenticity_driven")

    def test_hidden_gem_matches_authenticity_driven(self):
        assert self._find("I love finding hidden gems", "authenticity_driven")

    def test_like_a_local_matches_authenticity_driven(self):
        assert self._find("I want to eat like a local", "authenticity_driven")

    def test_tourist_trap_matches_authenticity_driven(self):
        assert self._find("I want to avoid tourist traps", "authenticity_driven")

    def test_must_see_matches_mainstream_comfortable(self):
        assert self._find("I want to visit the must-see attractions", "mainstream_comfortable")

    def test_famous_landmarks_matches_mainstream_comfortable(self):
        assert self._find("I love famous landmarks", "mainstream_comfortable")

    def test_local_keyword_matches_locally_curious(self):
        assert self._find("I love local culture", "locally_curious")

    def test_authentic_matches_authenticity_driven(self):
        assert self._find("I want authentic experiences", "authenticity_driven")


# ---------------------------------------------------------------------------
# No false positives — common travel text
# ---------------------------------------------------------------------------

class TestNoFalsePositives:
    """These texts should not produce signals."""

    SAFE_TEXTS = [
        "I am planning a trip to Japan.",
        "What are the visa requirements?",
        "How many days should I spend in Kyoto?",
        "The flight departs at 6am.",
        "I need to pack light for this trip.",
        "What currency do they use?",
        "Is tap water safe to drink?",
        "Do I need travel insurance?",
    ]

    def test_visa_question_no_budget_match(self):
        text = "What are the visa requirements for Japan?"
        any_match = any(
            spec["pattern"].search(text)
            for spec in DIMENSION_PATTERNS["budget_orientation"]
        )
        assert not any_match

    def test_days_question_no_planning_match(self):
        text = "How many days should I spend in Kyoto?"
        # "schedule" / "plan" words absent — should not match structured
        any_match = any(
            spec["pattern"].search(text)
            for spec in DIMENSION_PATTERNS["planning_style"]
        )
        assert not any_match

    def test_pack_light_no_energy_match(self):
        text = "I need to pack light for this trip."
        any_match = any(
            spec["pattern"].search(text)
            for spec in DIMENSION_PATTERNS["energy_level"]
        )
        assert not any_match


# ---------------------------------------------------------------------------
# Regression test
# ---------------------------------------------------------------------------

class TestRegressions:
    def test_local_food_market_extracts_food_driven_and_authenticity(self):
        """
        'I love exploring local food markets' should match:
          - food_priority / food_driven  (via "food market")
          - authenticity_preference / locally_curious  (via "local")
        """
        text = "I love exploring local food markets"

        food_match = any(
            spec["value"] == "food_driven" and spec["pattern"].search(text)
            for spec in DIMENSION_PATTERNS["food_priority"]
        )
        auth_match = any(
            spec["value"] in ("locally_curious", "authenticity_driven")
            and spec["pattern"].search(text)
            for spec in DIMENSION_PATTERNS["authenticity_preference"]
        )

        assert food_match, "Expected food_driven match on 'local food markets'"
        assert auth_match, "Expected authenticity match on 'local food markets'"
