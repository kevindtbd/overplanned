"""
Tests for services/api/priors/destination_prior.py

Coverage:
  - All 7 cities have priors defined
  - Every city covers all 8 expected preference dimensions
  - Confidence gate: priors NOT injected when user confidence >= 0.3
  - Confidence gate: priors injected when user confidence < 0.3
  - Weight blend: injected prior has confidence = city_confidence * PRIOR_WEIGHT
  - Unknown city_slug returns user_signals unchanged (+ warning)
  - User signals are never mutated (pure function)
  - Multiple user signals for same dimension: max confidence used for gate check
  - Empty user_signals returns only priors
  - Prior signals tagged with source="destination_prior"
  - Prior signals include city_slug and prior_weight fields
  - Specific city characteristic priors are correct direction
"""

from __future__ import annotations

import copy
from unittest.mock import patch

import pytest

from services.api.priors.destination_prior import (
    apply_destination_prior,
    CITY_PRIORS,
    PRIOR_WEIGHT,
    CONFIDENCE_GATE,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPECTED_CITIES = {
    "austin",
    "new-orleans",
    "seattle",
    "asheville",
    "portland",
    "mexico-city",
    "bend",
}

EXPECTED_DIMENSIONS = {
    "food_priority",
    "nightlife_interest",
    "pace_preference",
    "budget_sensitivity",
    "outdoor_affinity",
    "cultural_depth",
    "social_energy",
    "adventure_tolerance",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signal(dimension: str, direction: str = "high", confidence: float = 0.8) -> dict:
    return {
        "dimension": dimension,
        "direction": direction,
        "confidence": confidence,
        "source": "behavioral",
    }


def _get_injected_dims(blended: list[dict]) -> set[str]:
    """Return set of dimensions injected from destination_prior source."""
    return {s["dimension"] for s in blended if s.get("source") == "destination_prior"}


def _get_user_dims(blended: list[dict]) -> set[str]:
    """Return set of dimensions from user signals."""
    return {s["dimension"] for s in blended if s.get("source") != "destination_prior"}


# ---------------------------------------------------------------------------
# Static data validation
# ---------------------------------------------------------------------------

class TestCityPriorsStaticData:
    def test_all_7_cities_present(self):
        assert set(CITY_PRIORS.keys()) == EXPECTED_CITIES

    @pytest.mark.parametrize("city", list(EXPECTED_CITIES))
    def test_each_city_covers_all_8_dimensions(self, city: str):
        city_dims = set(CITY_PRIORS[city].keys())
        assert city_dims == EXPECTED_DIMENSIONS, (
            f"City {city!r} missing dimensions: {EXPECTED_DIMENSIONS - city_dims}"
        )

    @pytest.mark.parametrize("city", list(EXPECTED_CITIES))
    def test_each_city_prior_has_required_fields(self, city: str):
        for dim, spec in CITY_PRIORS[city].items():
            assert "direction" in spec, f"{city}.{dim} missing 'direction'"
            assert "confidence" in spec, f"{city}.{dim} missing 'confidence'"
            assert "weight" in spec, f"{city}.{dim} missing 'weight'"

    @pytest.mark.parametrize("city", list(EXPECTED_CITIES))
    def test_confidence_in_valid_range(self, city: str):
        for dim, spec in CITY_PRIORS[city].items():
            conf = spec["confidence"]
            assert 0.0 <= conf <= 1.0, (
                f"{city}.{dim}: confidence {conf} out of [0.0, 1.0]"
            )

    @pytest.mark.parametrize("city", list(EXPECTED_CITIES))
    def test_direction_is_valid(self, city: str):
        valid = {"high", "low", "neutral"}
        for dim, spec in CITY_PRIORS[city].items():
            assert spec["direction"] in valid, (
                f"{city}.{dim}: invalid direction {spec['direction']!r}"
            )

    @pytest.mark.parametrize("city", list(EXPECTED_CITIES))
    def test_weight_equals_prior_weight_constant(self, city: str):
        for dim, spec in CITY_PRIORS[city].items():
            assert spec["weight"] == PRIOR_WEIGHT, (
                f"{city}.{dim}: weight {spec['weight']} != PRIOR_WEIGHT {PRIOR_WEIGHT}"
            )


# ---------------------------------------------------------------------------
# City-specific characteristic directions
# ---------------------------------------------------------------------------

class TestCityCharacteristicPriors:
    """Spot-check key city personality signals are correct direction."""

    def test_new_orleans_food_is_high(self):
        assert CITY_PRIORS["new-orleans"]["food_priority"]["direction"] == "high"

    def test_new_orleans_nightlife_is_high(self):
        assert CITY_PRIORS["new-orleans"]["nightlife_interest"]["direction"] == "high"

    def test_new_orleans_food_confidence_is_high(self):
        # New Orleans food is iconic — confidence should be >= 0.85
        assert CITY_PRIORS["new-orleans"]["food_priority"]["confidence"] >= 0.85

    def test_bend_outdoor_is_high(self):
        assert CITY_PRIORS["bend"]["outdoor_affinity"]["direction"] == "high"

    def test_bend_outdoor_confidence_is_very_high(self):
        assert CITY_PRIORS["bend"]["outdoor_affinity"]["confidence"] >= 0.90

    def test_bend_nightlife_is_low(self):
        assert CITY_PRIORS["bend"]["nightlife_interest"]["direction"] == "low"

    def test_mexico_city_cultural_depth_is_high(self):
        assert CITY_PRIORS["mexico-city"]["cultural_depth"]["direction"] == "high"

    def test_mexico_city_cultural_confidence_is_high(self):
        assert CITY_PRIORS["mexico-city"]["cultural_depth"]["confidence"] >= 0.85

    def test_asheville_outdoor_is_high(self):
        assert CITY_PRIORS["asheville"]["outdoor_affinity"]["direction"] == "high"

    def test_austin_food_is_high(self):
        assert CITY_PRIORS["austin"]["food_priority"]["direction"] == "high"

    def test_portland_budget_sensitivity_is_high(self):
        # Portland is known as budget-friendly
        assert CITY_PRIORS["portland"]["budget_sensitivity"]["direction"] == "high"

    def test_seattle_outdoor_affinity_is_high(self):
        assert CITY_PRIORS["seattle"]["outdoor_affinity"]["direction"] == "high"


# ---------------------------------------------------------------------------
# apply_destination_prior: confidence gate
# ---------------------------------------------------------------------------

class TestConfidenceGate:
    def test_high_confidence_user_signal_blocks_prior(self):
        """User confidence >= 0.3 means prior should NOT be injected for that dim."""
        user_signals = [_make_signal("food_priority", confidence=0.3)]
        blended = apply_destination_prior(user_signals, "austin")
        injected = _get_injected_dims(blended)
        assert "food_priority" not in injected

    def test_exactly_at_gate_blocks_prior(self):
        """confidence == CONFIDENCE_GATE exactly -> prior blocked."""
        user_signals = [_make_signal("food_priority", confidence=CONFIDENCE_GATE)]
        blended = apply_destination_prior(user_signals, "austin")
        assert "food_priority" not in _get_injected_dims(blended)

    def test_below_gate_allows_prior(self):
        """User confidence < 0.3 means prior should be injected for that dim."""
        user_signals = [_make_signal("food_priority", confidence=0.1)]
        blended = apply_destination_prior(user_signals, "austin")
        assert "food_priority" in _get_injected_dims(blended)

    def test_absent_dimension_gets_prior(self):
        """If user has no signal for a dim, prior is injected."""
        user_signals = []  # no signals at all
        blended = apply_destination_prior(user_signals, "austin")
        injected = _get_injected_dims(blended)
        # All 8 dimensions should be injected when user has no signals
        assert injected == EXPECTED_DIMENSIONS

    def test_dimension_not_in_user_signals_gets_prior(self):
        """Dimension absent from user signals -> prior injected."""
        # User has food_priority but not nightlife_interest
        user_signals = [_make_signal("food_priority", confidence=0.8)]
        blended = apply_destination_prior(user_signals, "austin")
        assert "nightlife_interest" in _get_injected_dims(blended)

    def test_multiple_signals_same_dim_uses_max_confidence(self):
        """When user has multiple signals for same dim, max confidence is used for gate."""
        # Two signals: one weak (0.1) and one strong (0.5)
        user_signals = [
            _make_signal("food_priority", confidence=0.1),
            _make_signal("food_priority", confidence=0.5),
        ]
        blended = apply_destination_prior(user_signals, "austin")
        # Max is 0.5 >= 0.3 gate -> prior should NOT be injected
        assert "food_priority" not in _get_injected_dims(blended)

    def test_multiple_signals_all_weak_injects_prior(self):
        """All user signals for dim have low confidence -> prior injected."""
        user_signals = [
            _make_signal("food_priority", confidence=0.1),
            _make_signal("food_priority", confidence=0.2),
        ]
        blended = apply_destination_prior(user_signals, "austin")
        # Max is 0.2 < 0.3 gate -> prior injected
        assert "food_priority" in _get_injected_dims(blended)


# ---------------------------------------------------------------------------
# apply_destination_prior: weight blending
# ---------------------------------------------------------------------------

class TestWeightBlending:
    def test_injected_prior_confidence_scaled_by_weight(self):
        """Injected prior confidence = city_confidence * PRIOR_WEIGHT."""
        user_signals = []
        blended = apply_destination_prior(user_signals, "austin")

        city_food_conf = CITY_PRIORS["austin"]["food_priority"]["confidence"]
        expected_effective = round(city_food_conf * PRIOR_WEIGHT, 4)

        prior_signals = [
            s for s in blended
            if s.get("source") == "destination_prior" and s["dimension"] == "food_priority"
        ]
        assert len(prior_signals) == 1
        assert prior_signals[0]["confidence"] == pytest.approx(expected_effective, abs=1e-6)

    def test_prior_weight_constant_is_0_15(self):
        assert PRIOR_WEIGHT == 0.15

    def test_confidence_gate_constant_is_0_3(self):
        assert CONFIDENCE_GATE == 0.3

    def test_prior_weight_field_in_injected_signal(self):
        blended = apply_destination_prior([], "bend")
        for sig in blended:
            if sig.get("source") == "destination_prior":
                assert sig.get("prior_weight") == PRIOR_WEIGHT


# ---------------------------------------------------------------------------
# apply_destination_prior: metadata on injected signals
# ---------------------------------------------------------------------------

class TestInjectedSignalMetadata:
    def test_injected_signals_have_destination_prior_source(self):
        blended = apply_destination_prior([], "new-orleans")
        for sig in blended:
            assert sig.get("source") == "destination_prior"

    def test_injected_signals_include_city_slug(self):
        blended = apply_destination_prior([], "mexico-city")
        for sig in blended:
            if sig.get("source") == "destination_prior":
                assert sig.get("city_slug") == "mexico-city"

    def test_user_signals_preserved_unchanged(self):
        user_sig = _make_signal("food_priority", confidence=0.8)
        user_sig_copy = copy.deepcopy(user_sig)
        blended = apply_destination_prior([user_sig], "austin")

        user_in_blended = [s for s in blended if s.get("source") == "behavioral"]
        assert len(user_in_blended) == 1
        assert user_in_blended[0] == user_sig_copy


# ---------------------------------------------------------------------------
# apply_destination_prior: pure function / immutability
# ---------------------------------------------------------------------------

class TestPureFunction:
    def test_original_list_not_mutated(self):
        user_signals = [_make_signal("food_priority", confidence=0.1)]
        original_copy = copy.deepcopy(user_signals)
        apply_destination_prior(user_signals, "austin")
        assert user_signals == original_copy

    def test_original_signal_dicts_not_mutated(self):
        user_signals = [_make_signal("food_priority", confidence=0.8)]
        original_confidence = user_signals[0]["confidence"]
        apply_destination_prior(user_signals, "austin")
        assert user_signals[0]["confidence"] == original_confidence

    def test_returns_new_list(self):
        user_signals = [_make_signal("food_priority", confidence=0.8)]
        result = apply_destination_prior(user_signals, "austin")
        assert result is not user_signals


# ---------------------------------------------------------------------------
# apply_destination_prior: unknown city
# ---------------------------------------------------------------------------

class TestUnknownCity:
    def test_unknown_city_returns_user_signals_unchanged(self):
        user_signals = [_make_signal("food_priority", confidence=0.5)]
        result = apply_destination_prior(user_signals, "atlantis")
        # Should return user_signals (as new list)
        assert len(result) == 1
        assert result[0]["dimension"] == "food_priority"

    def test_unknown_city_logs_warning(self):
        with patch("services.api.priors.destination_prior.logger") as mock_log:
            apply_destination_prior([], "not-a-city")
            mock_log.warning.assert_called_once()
            warning_args = mock_log.warning.call_args[0]
            assert "unknown" in warning_args[0].lower() or "not-a-city" in str(warning_args)


# ---------------------------------------------------------------------------
# apply_destination_prior: edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_user_signals_returns_all_priors(self):
        blended = apply_destination_prior([], "asheville")
        injected = _get_injected_dims(blended)
        assert injected == EXPECTED_DIMENSIONS

    def test_all_strong_user_signals_no_priors_injected(self):
        """User has strong signals for all 8 dims -> no priors injected."""
        user_signals = [
            _make_signal(dim, confidence=0.9)
            for dim in EXPECTED_DIMENSIONS
        ]
        blended = apply_destination_prior(user_signals, "portland")
        injected = _get_injected_dims(blended)
        assert injected == set()

    @pytest.mark.parametrize("city", list(EXPECTED_CITIES))
    def test_each_city_produces_output(self, city: str):
        blended = apply_destination_prior([], city)
        assert len(blended) > 0

    def test_blended_list_length_equals_user_plus_injected(self):
        user_signals = [
            _make_signal("food_priority", confidence=0.8),  # high confidence -> no prior
            _make_signal("nightlife_interest", confidence=0.1),  # low -> prior injected
        ]
        blended = apply_destination_prior(user_signals, "austin")
        # User signals: 2
        # Injected priors: 7 dims (nightlife_interest has user weak signal -> injected,
        #   food_priority strong -> not injected, 6 missing dims -> injected = 7 total)
        injected = _get_injected_dims(blended)
        # nightlife_interest (weak) + 6 dims not in user_signals = 7
        assert len(injected) == 7
        assert len(blended) == 2 + 7
