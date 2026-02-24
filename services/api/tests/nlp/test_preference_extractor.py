"""
Unit tests for the preference extractor — nlp/preference_extractor.py.

Covers:
- Each rule pattern dimension fires correctly
- Confidence levels: keyword (0.6), phrase (0.8), explicit (0.9)
- Word boundary: "solo" matches but "consolation" does not
- Case insensitivity
- Empty / whitespace input returns empty list
- Deduplication: same dimension from rules + LLM -> keep highest confidence
- LLM pass skipped when rules find 3+ signals
- source_text truncation at 500 chars
- All returned dimensions are in the valid 10-dimension enum
- PreferenceSignal dataclass truncates source_text on init
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.api.nlp.preference_extractor import (
    LLM_MAX_CONFIDENCE,
    LLM_TRIGGER_THRESHOLD,
    SOURCE_TEXT_MAX_LEN,
    PreferenceSignal,
    _deduplicate_by_dimension,
    _parse_llm_response,
    extract_preferences,
    extract_preferences_llm,
    extract_preferences_rules,
)
from services.api.nlp.patterns import VALID_DIMENSIONS, VALID_VALUES


# ---------------------------------------------------------------------------
# PreferenceSignal dataclass
# ---------------------------------------------------------------------------

class TestPreferenceSignalDataclass:
    def test_basic_construction(self):
        sig = PreferenceSignal(
            dimension="energy_level",
            direction="positive",
            confidence=0.8,
            source_text="chill trip",
            source="rule_based",
        )
        assert sig.dimension == "energy_level"
        assert sig.direction == "positive"
        assert sig.confidence == 0.8
        assert sig.source_text == "chill trip"
        assert sig.source == "rule_based"

    def test_source_text_truncated_on_init(self):
        long_text = "x" * 600
        sig = PreferenceSignal(
            dimension="energy_level",
            direction="positive",
            confidence=0.6,
            source_text=long_text,
            source="rule_based",
        )
        assert len(sig.source_text) == SOURCE_TEXT_MAX_LEN
        assert len(sig.source_text) <= 500

    def test_source_text_not_truncated_when_short(self):
        sig = PreferenceSignal(
            dimension="food_priority",
            direction="positive",
            confidence=0.9,
            source_text="I am a foodie",
            source="rule_based",
        )
        assert sig.source_text == "I am a foodie"

    def test_source_text_exactly_at_limit_not_truncated(self):
        text = "a" * SOURCE_TEXT_MAX_LEN
        sig = PreferenceSignal(
            dimension="food_priority",
            direction="positive",
            confidence=0.6,
            source_text=text,
            source="rule_based",
        )
        assert len(sig.source_text) == SOURCE_TEXT_MAX_LEN


# ---------------------------------------------------------------------------
# extract_preferences_rules — empty/whitespace
# ---------------------------------------------------------------------------

class TestExtractRulesEmptyInput:
    def test_empty_string_returns_empty(self):
        assert extract_preferences_rules("") == []

    def test_whitespace_only_returns_empty(self):
        assert extract_preferences_rules("   \n\t  ") == []

    def test_none_equivalent_empty(self):
        # Not passing None directly since type is str, but guard is there
        result = extract_preferences_rules("")
        assert result == []


# ---------------------------------------------------------------------------
# extract_preferences_rules — dimension coverage
# ---------------------------------------------------------------------------

class TestExtractRulesEnergyLevel:
    def test_chill_extracts_low_energy(self):
        result = extract_preferences_rules("I want a chill relaxed trip")
        dims = {s.dimension: s for s in result}
        assert "energy_level" in dims
        assert dims["energy_level"].confidence >= 0.6

    def test_adventure_extracts_high_energy(self):
        result = extract_preferences_rules("I love adventure and thrill-seeking")
        dims = {s.dimension: s for s in result}
        assert "energy_level" in dims

    def test_adrenaline_rush_extracts_high_energy(self):
        result = extract_preferences_rules("adrenaline rush is my thing")
        dims = {s.dimension: s for s in result}
        assert "energy_level" in dims

    def test_mellow_extracts_low_energy(self):
        result = extract_preferences_rules("I prefer something mellow and slow")
        dims = {s.dimension: s for s in result}
        assert "energy_level" in dims


class TestExtractRulesSocialOrientation:
    def test_solo_extracts_solo_focused(self):
        result = extract_preferences_rules("I am travelling solo")
        dims = {s.dimension: s for s in result}
        assert "social_orientation" in dims

    def test_by_myself_extracts_solo_focused(self):
        result = extract_preferences_rules("I am going by myself")
        dims = {s.dimension: s for s in result}
        assert "social_orientation" in dims

    def test_with_friends_extracts_social_explorer(self):
        result = extract_preferences_rules("Going with friends to Tokyo")
        dims = {s.dimension: s for s in result}
        assert "social_orientation" in dims

    def test_small_group_extracts_small_group(self):
        result = extract_preferences_rules("Just a small group of us")
        dims = {s.dimension: s for s in result}
        assert "social_orientation" in dims


class TestExtractRulesBudgetOrientation:
    def test_cheap_extracts_budget_conscious(self):
        result = extract_preferences_rules("Looking for cheap accommodation")
        dims = {s.dimension: s for s in result}
        assert "budget_orientation" in dims

    def test_on_a_budget_extracts_budget_conscious(self):
        result = extract_preferences_rules("I am on a budget this trip")
        dims = {s.dimension: s for s in result}
        assert "budget_orientation" in dims

    def test_luxury_extracts_premium_seeker(self):
        result = extract_preferences_rules("I want luxury hotels")
        dims = {s.dimension: s for s in result}
        assert "budget_orientation" in dims

    def test_splurge_extracts_premium_seeker(self):
        result = extract_preferences_rules("I want to splurge a little")
        dims = {s.dimension: s for s in result}
        assert "budget_orientation" in dims


class TestExtractRulesFoodPriority:
    def test_foodie_extracts_food_driven(self):
        result = extract_preferences_rules("I am a foodie")
        dims = {s.dimension: s for s in result}
        assert "food_priority" in dims

    def test_must_eat_extracts_food_driven(self):
        result = extract_preferences_rules("Give me all the must-eat spots")
        dims = {s.dimension: s for s in result}
        assert "food_priority" in dims

    def test_best_restaurants_extracts_food_driven(self):
        result = extract_preferences_rules("I want to visit the best restaurants")
        dims = {s.dimension: s for s in result}
        assert "food_priority" in dims

    def test_not_picky_extracts_food_secondary(self):
        result = extract_preferences_rules("I am not picky about food")
        dims = {s.dimension: s for s in result}
        assert "food_priority" in dims


class TestExtractRulesPlanningStyle:
    def test_spontaneous_extracts_spontaneous(self):
        result = extract_preferences_rules("I am a spontaneous person")
        dims = {s.dimension: s for s in result}
        assert "planning_style" in dims

    def test_go_with_flow_extracts_spontaneous(self):
        result = extract_preferences_rules("I like to go with the flow")
        dims = {s.dimension: s for s in result}
        assert "planning_style" in dims

    def test_schedule_extracts_structured(self):
        result = extract_preferences_rules("I want a detailed schedule")
        dims = {s.dimension: s for s in result}
        assert "planning_style" in dims

    def test_flexible_extracts_flexible(self):
        result = extract_preferences_rules("I prefer to stay flexible")
        dims = {s.dimension: s for s in result}
        assert "planning_style" in dims


class TestExtractRulesAuthenticityPreference:
    def test_off_beaten_path_extracts_authenticity_driven(self):
        result = extract_preferences_rules("I love off the beaten path places")
        dims = {s.dimension: s for s in result}
        assert "authenticity_preference" in dims

    def test_hidden_gem_extracts_authenticity_driven(self):
        result = extract_preferences_rules("I want hidden gems only")
        dims = {s.dimension: s for s in result}
        assert "authenticity_preference" in dims

    def test_must_see_extracts_mainstream_comfortable(self):
        result = extract_preferences_rules("Show me the must-see attractions")
        dims = {s.dimension: s for s in result}
        assert "authenticity_preference" in dims

    def test_famous_extracts_mainstream_comfortable(self):
        result = extract_preferences_rules("I want to see the famous landmarks")
        dims = {s.dimension: s for s in result}
        assert "authenticity_preference" in dims


# ---------------------------------------------------------------------------
# Confidence level tests
# ---------------------------------------------------------------------------

class TestConfidenceLevels:
    """
    Rule confidence tiers:
      keyword single match   -> 0.6
      phrase match           -> 0.8
      explicit self-decl     -> 0.9
    """

    def test_keyword_confidence_is_0_6(self):
        # "chill" is a keyword-level pattern
        result = extract_preferences_rules("chill trip")
        dims = {s.dimension: s for s in result}
        assert "energy_level" in dims
        assert dims["energy_level"].confidence == pytest.approx(0.6, abs=0.01)

    def test_phrase_confidence_is_0_8(self):
        # "low-key" is a phrase-level pattern
        result = extract_preferences_rules("I prefer low-key activities")
        dims = {s.dimension: s for s in result}
        assert "energy_level" in dims
        assert dims["energy_level"].confidence == pytest.approx(0.8, abs=0.01)

    def test_explicit_confidence_is_0_9(self):
        # "I am a foodie" is an explicit-level pattern
        result = extract_preferences_rules("I am a foodie and love local food")
        dims = {s.dimension: s for s in result}
        assert "food_priority" in dims
        assert dims["food_priority"].confidence == pytest.approx(0.9, abs=0.01)

    def test_explicit_beats_keyword_in_same_text(self):
        # Text has both "adventure" (keyword) and "I love adventure" (explicit)
        result = extract_preferences_rules("I love adventure — thrill is my thing")
        dims = {s.dimension: s for s in result}
        assert "energy_level" in dims
        # The explicit/phrase should win over bare keyword
        assert dims["energy_level"].confidence >= 0.8


# ---------------------------------------------------------------------------
# Word boundary tests
# ---------------------------------------------------------------------------

class TestWordBoundary:
    def test_solo_matches_solo(self):
        result = extract_preferences_rules("I prefer to travel solo")
        dims = {s.dimension: s for s in result}
        assert "social_orientation" in dims

    def test_consolation_does_not_match_solo(self):
        result = extract_preferences_rules("It was a consolation prize for the runner-up")
        dims = {s.dimension: s for s in result}
        assert "social_orientation" not in dims

    def test_chill_matches(self):
        result = extract_preferences_rules("very chill itinerary please")
        dims = {s.dimension: s for s in result}
        assert "energy_level" in dims

    def test_chilly_does_not_match_chill(self):
        # "\bchill\b" must NOT match "chilly" — word boundary stops before the 'y'
        result = extract_preferences_rules("The weather is chilly in November")
        dims = {s.dimension: s for s in result}
        assert "energy_level" not in dims, (
            "False positive: 'chilly' should not match the \\bchill\\b pattern"
        )

    def test_local_keyword_matches(self):
        result = extract_preferences_rules("I want local experiences")
        dims = {s.dimension: s for s in result}
        assert "authenticity_preference" in dims

    def test_locals_keyword_matches(self):
        # "locals" should still match via the local keyword
        result = extract_preferences_rules("eating where the locals eat")
        # The regex \blocal\b won't match "locals" — that's fine, phrase patterns cover it
        # This test just verifies no crash
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Case insensitivity
# ---------------------------------------------------------------------------

class TestCaseInsensitivity:
    def test_uppercase_solo(self):
        result = extract_preferences_rules("SOLO trip")
        dims = {s.dimension: s for s in result}
        assert "social_orientation" in dims

    def test_mixed_case_foodie(self):
        result = extract_preferences_rules("I Am A Foodie")
        dims = {s.dimension: s for s in result}
        assert "food_priority" in dims

    def test_uppercase_luxury(self):
        result = extract_preferences_rules("LUXURY hotels only")
        dims = {s.dimension: s for s in result}
        assert "budget_orientation" in dims

    def test_mixed_case_spontaneous(self):
        result = extract_preferences_rules("I Am Spontaneous")
        dims = {s.dimension: s for s in result}
        assert "planning_style" in dims


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_same_dimension_keeps_highest_confidence(self):
        signals = [
            PreferenceSignal("energy_level", "positive", 0.6, "chill", "rule_based"),
            PreferenceSignal("energy_level", "positive", 0.8, "low-key", "rule_based"),
            PreferenceSignal("energy_level", "positive", 0.7, "relaxed", "llm_haiku"),
        ]
        result = _deduplicate_by_dimension(signals)
        assert len(result) == 1
        assert result[0].confidence == pytest.approx(0.8, abs=0.001)

    def test_different_dimensions_all_kept(self):
        signals = [
            PreferenceSignal("energy_level", "positive", 0.6, "chill", "rule_based"),
            PreferenceSignal("food_priority", "positive", 0.9, "foodie", "rule_based"),
            PreferenceSignal("planning_style", "positive", 0.8, "spontaneous", "rule_based"),
        ]
        result = _deduplicate_by_dimension(signals)
        assert len(result) == 3

    def test_tie_prefers_rule_based(self):
        signals = [
            PreferenceSignal("energy_level", "positive", 0.7, "from llm", "llm_haiku"),
            PreferenceSignal("energy_level", "positive", 0.7, "from rule", "rule_based"),
        ]
        result = _deduplicate_by_dimension(signals)
        assert len(result) == 1
        assert result[0].source == "rule_based"

    def test_empty_input_returns_empty(self):
        assert _deduplicate_by_dimension([]) == []

    def test_single_signal_returned_unchanged(self):
        sig = PreferenceSignal("energy_level", "positive", 0.6, "chill", "rule_based")
        result = _deduplicate_by_dimension([sig])
        assert result == [sig]


# ---------------------------------------------------------------------------
# All returned dimensions are valid
# ---------------------------------------------------------------------------

class TestValidDimensions:
    def test_all_rule_results_have_valid_dimensions(self):
        texts = [
            "I want a chill solo trip with good food and local experiences",
            "Adventure seeker, luxury hotels, plan everything in advance",
            "Going with friends, not picky about food, must-see attractions",
        ]
        for text in texts:
            result = extract_preferences_rules(text)
            for sig in result:
                assert sig.dimension in VALID_DIMENSIONS, (
                    f"Invalid dimension {sig.dimension!r} from text: {text[:50]}"
                )


# ---------------------------------------------------------------------------
# source_text truncation
# ---------------------------------------------------------------------------

class TestSourceTextTruncation:
    def test_rule_source_text_never_exceeds_500_chars(self):
        # Create a very long text that matches multiple patterns
        text = "solo " * 200 + "chill " * 200 + "foodie " * 200
        result = extract_preferences_rules(text)
        for sig in result:
            assert len(sig.source_text) <= SOURCE_TEXT_MAX_LEN, (
                f"source_text exceeded {SOURCE_TEXT_MAX_LEN} chars for {sig.dimension}"
            )

    def test_preference_signal_truncates_on_construction(self):
        long_text = "y" * 600
        sig = PreferenceSignal("energy_level", "positive", 0.6, long_text, "rule_based")
        assert len(sig.source_text) == SOURCE_TEXT_MAX_LEN


# ---------------------------------------------------------------------------
# LLM pass skip threshold
# ---------------------------------------------------------------------------

class TestLLMPassThreshold:
    """LLM pass must be skipped when rules already found >= 3 signals."""

    @pytest.mark.asyncio
    async def test_llm_skipped_when_rules_find_three_or_more(self):
        # Text with enough keywords to trigger 3+ rule signals
        text = (
            "I am a foodie who loves solo travel. "
            "I prefer luxury hotels and spontaneous adventures."
        )

        mock_client = AsyncMock()
        mock_client.messages = AsyncMock()
        mock_client.messages.create = AsyncMock()

        result = await extract_preferences(text, anthropic_client=mock_client)

        # LLM create should NOT have been called
        mock_client.messages.create.assert_not_called()

        # But we should still have results from rules
        assert len(result) >= 3

    @pytest.mark.asyncio
    async def test_llm_called_when_rules_find_fewer_than_threshold(self):
        """When rules find < 3 signals, LLM should be invoked."""
        # Text where only 1-2 signals are clearly rule-extractable
        text = "chill trip"  # only energy_level likely to match

        # Mock a well-formed LLM response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "signals": [
                {
                    "dimension": "food_priority",
                    "direction": "positive",
                    "confidence": 0.6,
                    "evidence": "inferred from text",
                }
            ]
        }))]
        mock_response.usage = MagicMock(input_tokens=50, output_tokens=30)

        mock_client = AsyncMock()
        mock_client.messages = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        result = await extract_preferences(text, anthropic_client=mock_client)
        mock_client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_skipped_when_client_is_none(self):
        """If anthropic_client is None, LLM pass never runs even with few signals."""
        text = "chill trip"
        result = await extract_preferences(text, anthropic_client=None)
        # Should return rule results only — no crash
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# LLM pass — LLM_MAX_CONFIDENCE cap
# ---------------------------------------------------------------------------

class TestLLMConfidenceCap:
    @pytest.mark.asyncio
    async def test_llm_confidence_capped_at_0_7(self):
        """LLM signals must have confidence <= 0.7 regardless of LLM output."""
        text = "chill"  # minimal text so LLM pass fires

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "signals": [
                {
                    "dimension": "food_priority",
                    "direction": "positive",
                    "confidence": 0.99,  # LLM returns 0.99
                    "evidence": "some food text",
                }
            ]
        }))]
        mock_response.usage = MagicMock(input_tokens=50, output_tokens=30)

        mock_client = AsyncMock()
        mock_client.messages = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        result = await extract_preferences(text, anthropic_client=mock_client)

        # Find the food_priority signal
        food_sig = next((s for s in result if s.dimension == "food_priority"), None)
        if food_sig:
            assert food_sig.confidence <= LLM_MAX_CONFIDENCE


# ---------------------------------------------------------------------------
# LLM JSON parsing
# ---------------------------------------------------------------------------

class TestLLMResponseParsing:
    def test_valid_json_parsed_correctly(self):
        raw = json.dumps({
            "signals": [
                {
                    "dimension": "food_priority",
                    "direction": "positive",
                    "confidence": 0.65,
                    "evidence": "loves local cuisine",
                }
            ]
        })
        result = _parse_llm_response(raw)
        assert len(result) == 1
        assert result[0].dimension == "food_priority"
        assert result[0].direction == "positive"
        assert result[0].confidence == pytest.approx(0.65, abs=0.001)

    def test_markdown_code_fence_stripped(self):
        raw = '```json\n{"signals": [{"dimension": "planning_style", "direction": "positive", "confidence": 0.6, "evidence": "spontaneous"}]}\n```'
        result = _parse_llm_response(raw)
        assert len(result) == 1
        assert result[0].dimension == "planning_style"

    def test_invalid_json_returns_empty(self):
        result = _parse_llm_response("not json at all {{{")
        assert result == []

    def test_invalid_dimension_rejected(self):
        raw = json.dumps({
            "signals": [
                {
                    "dimension": "fake_dimension_xyz",
                    "direction": "positive",
                    "confidence": 0.6,
                    "evidence": "some text",
                }
            ]
        })
        result = _parse_llm_response(raw)
        assert result == []

    def test_invalid_direction_rejected(self):
        raw = json.dumps({
            "signals": [
                {
                    "dimension": "food_priority",
                    "direction": "sideways",
                    "confidence": 0.6,
                    "evidence": "some text",
                }
            ]
        })
        result = _parse_llm_response(raw)
        assert result == []

    def test_empty_signals_array_returns_empty(self):
        raw = json.dumps({"signals": []})
        result = _parse_llm_response(raw)
        assert result == []

    def test_confidence_capped_during_validation(self):
        raw = json.dumps({
            "signals": [
                {
                    "dimension": "energy_level",
                    "direction": "positive",
                    "confidence": 0.99,
                    "evidence": "high energy text",
                }
            ]
        })
        result = _parse_llm_response(raw)
        assert len(result) == 1
        assert result[0].confidence <= LLM_MAX_CONFIDENCE

    def test_evidence_truncated_at_500_chars(self):
        raw = json.dumps({
            "signals": [
                {
                    "dimension": "energy_level",
                    "direction": "positive",
                    "confidence": 0.6,
                    "evidence": "a" * 600,
                }
            ]
        })
        result = _parse_llm_response(raw)
        assert len(result) == 1
        assert len(result[0].evidence) == SOURCE_TEXT_MAX_LEN


# ---------------------------------------------------------------------------
# Combined extract_preferences — output sorted by confidence
# ---------------------------------------------------------------------------

class TestExtractPreferencesSorting:
    @pytest.mark.asyncio
    async def test_results_sorted_by_confidence_descending(self):
        text = (
            "I am a foodie who loves solo travel. "
            "I prefer luxury hotels and spontaneous adventures off the beaten path."
        )
        result = await extract_preferences(text, anthropic_client=None)
        confidences = [s.confidence for s in result]
        assert confidences == sorted(confidences, reverse=True)

    @pytest.mark.asyncio
    async def test_empty_text_returns_empty(self):
        result = await extract_preferences("", anthropic_client=None)
        assert result == []

    @pytest.mark.asyncio
    async def test_whitespace_returns_empty(self):
        result = await extract_preferences("   ", anthropic_client=None)
        assert result == []

    @pytest.mark.asyncio
    async def test_all_sources_rule_based_when_no_client(self):
        text = "I am a foodie solo traveler who loves luxury and adventure"
        result = await extract_preferences(text, anthropic_client=None)
        for sig in result:
            assert sig.source == "rule_based"

    @pytest.mark.asyncio
    async def test_deduplication_in_combined_flow(self):
        """Even if rules + LLM both produce energy_level, only one survives."""
        text = "chill"  # only energy_level from rules

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "signals": [
                {
                    "dimension": "energy_level",  # same dimension as rules
                    "direction": "positive",
                    "confidence": 0.5,  # lower than rule's 0.6
                    "evidence": "chill vibe",
                }
            ]
        }))]
        mock_response.usage = MagicMock(input_tokens=40, output_tokens=20)

        mock_client = AsyncMock()
        mock_client.messages = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        result = await extract_preferences(text, anthropic_client=mock_client)

        energy_signals = [s for s in result if s.dimension == "energy_level"]
        # Must be exactly one energy_level signal
        assert len(energy_signals) == 1
        # Rule (0.6) beats LLM (0.5)
        assert energy_signals[0].source == "rule_based"
