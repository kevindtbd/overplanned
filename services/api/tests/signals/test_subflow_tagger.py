"""
Unit tests: Subflow Tagger — Phase 1.2.

Covers:
- Each of the 11 subflow tags can be assigned
- Priority ordering (rarest context wins when multiple keys are set)
- Fallback to "core_ranking" when no special context is present
- Returns None when both signal and context are empty
- Context key lookup is case-sensitive
- Signal-level flags override / merge with context dict
"""

import pytest

from services.api.signals.subflow_tagger import tag_subflow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tag(signal: dict = None, context: dict = None) -> str | None:
    return tag_subflow(signal or {}, context or {})


# ===================================================================
# 1. Individual subflow assignment
# ===================================================================

class TestIndividualSubflows:
    """Each subflow is reachable when its context key is set."""

    def test_first_creation_rejection(self):
        result = _tag(context={"firstCreationRejection": True})
        assert result == "first_creation_rejection"

    def test_itinerary_alteration_date(self):
        result = _tag(context={"itineraryAlterationDate": True})
        assert result == "itinerary_alteration_date"

    def test_itinerary_alteration_swap(self):
        result = _tag(context={"itineraryAlterationSwap": True})
        assert result == "itinerary_alteration_swap"

    def test_itinerary_alteration_category(self):
        result = _tag(context={"itineraryAlterationCategory": True})
        assert result == "itinerary_alteration_category"

    def test_group_split(self):
        result = _tag(context={"groupSplit": True})
        assert result == "group_split"

    def test_repeat_city(self):
        result = _tag(context={"repeatCity": True})
        assert result == "repeat_city"

    def test_group_ranking(self):
        result = _tag(context={"groupRanking": True})
        assert result == "group_ranking"

    def test_hllm_rerank(self):
        result = _tag(context={"hllmRerank": True})
        assert result == "hllm_rerank"

    def test_offline_pivot(self):
        result = _tag(context={"offlinePivot": True})
        assert result == "offline_pivot"

    def test_onthefly_add(self):
        result = _tag(context={"ontheflyAdd": True})
        assert result == "onthefly_add"

    def test_core_ranking_is_default(self):
        """Empty context dict returns 'core_ranking'."""
        result = _tag(context={})
        assert result == "core_ranking"


# ===================================================================
# 2. Priority ordering
# ===================================================================

class TestPriorityOrdering:
    """Higher-priority (rarer) context wins when multiple keys are set."""

    def test_first_creation_beats_everything(self):
        """firstCreationRejection is priority 1 — beats all others."""
        context = {
            "firstCreationRejection": True,
            "groupSplit": True,
            "repeatCity": True,
            "ontheflyAdd": True,
        }
        result = _tag(context=context)
        assert result == "first_creation_rejection"

    def test_alteration_date_beats_group_split(self):
        """itineraryAlterationDate (priority 2) beats groupSplit (priority 5)."""
        context = {
            "itineraryAlterationDate": True,
            "groupSplit": True,
        }
        result = _tag(context=context)
        assert result == "itinerary_alteration_date"

    def test_alteration_swap_beats_repeat_city(self):
        """itineraryAlterationSwap (priority 3) beats repeatCity (priority 6)."""
        context = {
            "itineraryAlterationSwap": True,
            "repeatCity": True,
        }
        result = _tag(context=context)
        assert result == "itinerary_alteration_swap"

    def test_alteration_category_beats_group_ranking(self):
        """itineraryAlterationCategory (priority 4) beats groupRanking (priority 7)."""
        context = {
            "itineraryAlterationCategory": True,
            "groupRanking": True,
        }
        result = _tag(context=context)
        assert result == "itinerary_alteration_category"

    def test_group_split_beats_repeat_city(self):
        """groupSplit (priority 5) beats repeatCity (priority 6)."""
        context = {
            "groupSplit": True,
            "repeatCity": True,
        }
        result = _tag(context=context)
        assert result == "group_split"

    def test_repeat_city_beats_group_ranking(self):
        """repeatCity (priority 6) beats groupRanking (priority 7)."""
        context = {
            "repeatCity": True,
            "groupRanking": True,
        }
        result = _tag(context=context)
        assert result == "repeat_city"

    def test_group_ranking_beats_hllm_rerank(self):
        """groupRanking (priority 7) beats hllmRerank (priority 8)."""
        context = {
            "groupRanking": True,
            "hllmRerank": True,
        }
        result = _tag(context=context)
        assert result == "group_ranking"

    def test_hllm_rerank_beats_offline_pivot(self):
        """hllmRerank (priority 8) beats offlinePivot (priority 9)."""
        context = {
            "hllmRerank": True,
            "offlinePivot": True,
        }
        result = _tag(context=context)
        assert result == "hllm_rerank"

    def test_offline_pivot_beats_onthefly_add(self):
        """offlinePivot (priority 9) beats ontheflyAdd (priority 10)."""
        context = {
            "offlinePivot": True,
            "ontheflyAdd": True,
        }
        result = _tag(context=context)
        assert result == "offline_pivot"

    def test_onthefly_add_beats_core_ranking_default(self):
        """ontheflyAdd (priority 10) beats the core_ranking fallback."""
        context = {"ontheflyAdd": True}
        result = _tag(context=context)
        assert result == "onthefly_add"


# ===================================================================
# 3. Falsy / null handling
# ===================================================================

class TestFalsyHandling:
    """Keys set to False or None should not trigger the subflow."""

    def test_false_context_key_does_not_trigger(self):
        result = _tag(context={"firstCreationRejection": False, "ontheflyAdd": True})
        assert result == "onthefly_add"

    def test_none_context_key_does_not_trigger(self):
        result = _tag(context={"groupSplit": None, "repeatCity": True})
        assert result == "repeat_city"

    def test_zero_context_key_does_not_trigger(self):
        """Numeric 0 is falsy and should not trigger a subflow."""
        result = _tag(context={"groupRanking": 0, "ontheflyAdd": True})
        assert result == "onthefly_add"

    def test_empty_string_context_key_does_not_trigger(self):
        result = _tag(context={"hllmRerank": "", "offlinePivot": True})
        assert result == "offline_pivot"

    def test_both_none_returns_none(self):
        """When both signal and context are None / empty, return None."""
        result = tag_subflow(None, None)
        assert result is None

    def test_both_empty_dicts_return_core_ranking(self):
        """When both are empty dicts (not None), return core_ranking."""
        result = tag_subflow({}, {})
        assert result == "core_ranking"


# ===================================================================
# 4. Signal-level flags
# ===================================================================

class TestSignalLevelFlags:
    """Signal dict flags are merged with context — same priority rules apply."""

    def test_signal_flag_can_set_subflow(self):
        """A flag on the signal dict is respected."""
        result = tag_subflow({"offlinePivot": True}, {})
        assert result == "offline_pivot"

    def test_signal_flag_obeys_priority_against_context(self):
        """Context flag with higher priority beats signal flag."""
        result = tag_subflow(
            {"ontheflyAdd": True},
            {"firstCreationRejection": True},
        )
        assert result == "first_creation_rejection"

    def test_signal_flag_beats_lower_priority_context(self):
        """Signal flag beats a lower-priority context key."""
        result = tag_subflow(
            {"hllmRerank": True},
            {"ontheflyAdd": True},
        )
        assert result == "hllm_rerank"

    def test_signal_none_with_context_works(self):
        """Passing None as signal dict is handled gracefully."""
        result = tag_subflow(None, {"repeatCity": True})
        assert result == "repeat_city"

    def test_context_none_with_signal_works(self):
        """Passing None as context dict is handled gracefully."""
        result = tag_subflow({"groupSplit": True}, None)
        assert result == "group_split"
