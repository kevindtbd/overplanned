"""Tests for the signal taxonomy — weights, polarity, and defaults."""

import pytest

from services.api.signals.taxonomy import (
    SIGNAL_WEIGHTS,
    get_training_weight,
    is_negative_signal,
    is_positive_signal,
)


class TestSignalWeights:
    """SIGNAL_WEIGHTS dict covers all four tiers."""

    def test_tier1_explicit_signals_weight_1(self):
        tier1 = ["slot_confirmed", "slot_rejected", "pre_trip_slot_swap", "pre_trip_slot_removed"]
        for sig in tier1:
            assert SIGNAL_WEIGHTS[sig] == 1.0, f"{sig} should be tier 1 (1.0)"

    def test_tier2_strong_implicit_weight_07(self):
        tier2 = ["slot_locked", "pre_trip_slot_added", "pre_trip_reorder", "discover_shortlist"]
        for sig in tier2:
            assert SIGNAL_WEIGHTS[sig] == 0.7, f"{sig} should be tier 2 (0.7)"

    def test_tier3_weak_implicit_weight_03(self):
        tier3 = ["card_viewed", "card_dismissed", "slot_moved", "discover_swipe_right", "discover_swipe_left"]
        for sig in tier3:
            assert SIGNAL_WEIGHTS[sig] == 0.3, f"{sig} should be tier 3 (0.3)"

    def test_tier4_passive_weight_01(self):
        tier4 = ["card_impression", "pivot_accepted", "pivot_rejected"]
        for sig in tier4:
            assert SIGNAL_WEIGHTS[sig] == 0.1, f"{sig} should be tier 4 (0.1)"

    def test_total_signal_count(self):
        assert len(SIGNAL_WEIGHTS) == 16


class TestGetTrainingWeight:
    """get_training_weight returns correct weight or default."""

    def test_known_signal(self):
        assert get_training_weight("slot_confirmed") == 1.0

    def test_unknown_signal_defaults_to_01(self):
        assert get_training_weight("totally_made_up_signal") == 0.1

    def test_empty_string_defaults(self):
        assert get_training_weight("") == 0.1


class TestPositiveSignal:
    """is_positive_signal returns True for preference / approval signals."""

    @pytest.mark.parametrize("signal_type", [
        "slot_confirmed",
        "slot_locked",
        "pre_trip_slot_added",
        "discover_shortlist",
        "discover_swipe_right",
        "pivot_accepted",
    ])
    def test_positive_signals(self, signal_type: str):
        assert is_positive_signal(signal_type) is True

    @pytest.mark.parametrize("signal_type", [
        "slot_rejected",
        "card_dismissed",
        "discover_swipe_left",
        "pivot_rejected",
        "card_impression",
        "unknown_signal",
    ])
    def test_non_positive_signals(self, signal_type: str):
        assert is_positive_signal(signal_type) is False


class TestNegativeSignal:
    """is_negative_signal returns True for rejection / disinterest signals."""

    @pytest.mark.parametrize("signal_type", [
        "slot_rejected",
        "pre_trip_slot_removed",
        "discover_swipe_left",
        "pivot_rejected",
        "card_dismissed",
    ])
    def test_negative_signals(self, signal_type: str):
        assert is_negative_signal(signal_type) is True

    @pytest.mark.parametrize("signal_type", [
        "slot_confirmed",
        "slot_locked",
        "card_impression",
        "card_viewed",
        "unknown_signal",
    ])
    def test_non_negative_signals(self, signal_type: str):
        assert is_negative_signal(signal_type) is False


class TestPolarityExclusivity:
    """No signal should be both positive and negative."""

    def test_no_overlap(self):
        for signal_type in SIGNAL_WEIGHTS:
            if is_positive_signal(signal_type):
                assert not is_negative_signal(signal_type), (
                    f"{signal_type} is both positive and negative"
                )

    def test_neutral_signals_exist(self):
        """Some signals are neither positive nor negative (neutral context)."""
        neutral = [
            s for s in SIGNAL_WEIGHTS
            if not is_positive_signal(s) and not is_negative_signal(s)
        ]
        # pre_trip_slot_swap, pre_trip_reorder, card_viewed, slot_moved, card_impression
        assert len(neutral) > 0
