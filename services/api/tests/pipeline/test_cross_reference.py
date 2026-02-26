"""Tests for Pipeline D cross-reference scorer."""
import pytest
from services.api.pipeline.cross_reference import (
    reconstruct_c_signal, compute_tag_agreement, merge_tourist_scores,
    compute_merged_confidence, merge_vibe_tags, score_cross_reference,
    CSignal, DSignal, CrossRefOutput,
)


class TestReconstructCSignal:
    def test_builds_from_node(self):
        node = {"convergenceScore": 0.7, "authorityScore": 0.6,
                "tourist_score": 0.4, "sourceCount": 5}
        signal = reconstruct_c_signal(node, quality_signal_count=12)
        assert signal.convergence == 0.7
        assert signal.has_signal is True

    def test_handles_none(self):
        node = {"convergenceScore": None, "authorityScore": None,
                "tourist_score": None, "sourceCount": 0}
        signal = reconstruct_c_signal(node, quality_signal_count=0)
        assert signal.convergence == 0.0
        assert signal.has_signal is False


class TestComputeTagAgreement:
    def test_perfect(self):
        assert compute_tag_agreement(["a", "b"], ["a", "b"]) == 1.0

    def test_partial(self):
        score = compute_tag_agreement(["a", "b"], ["a", "c"])
        assert 0.0 < score < 1.0

    def test_none(self):
        assert compute_tag_agreement(["a"], ["b"]) == 0.0

    def test_both_empty(self):
        assert compute_tag_agreement([], []) == 0.0

    def test_one_empty(self):
        assert compute_tag_agreement(["a"], []) == 0.0


class TestMergeTouristScores:
    def test_conflict_65_35(self):
        merged = merge_tourist_scores(c_score=0.8, d_score=0.3)
        expected = 0.65 * 0.8 + 0.35 * 0.3
        assert abs(merged - expected) < 0.01

    def test_aligned_55_45(self):
        merged = merge_tourist_scores(c_score=0.5, d_score=0.6)
        expected = 0.55 * 0.5 + 0.45 * 0.6
        assert abs(merged - expected) < 0.01

    def test_none_c(self):
        assert merge_tourist_scores(None, 0.6) == 0.6

    def test_none_d(self):
        assert merge_tourist_scores(0.5, None) == 0.5

    def test_both_none(self):
        assert merge_tourist_scores(None, None) is None


class TestMergedConfidence:
    def test_base(self):
        conf = compute_merged_confidence(0.8, 0.7, tag_agreement=0.3)
        base = 0.4 * 0.8 + 0.6 * 0.7
        assert abs(conf - base) < 0.05

    def test_bonus(self):
        conf = compute_merged_confidence(0.8, 0.7, tag_agreement=0.6)
        assert conf > 0.8

    def test_penalty(self):
        with_conflict = compute_merged_confidence(0.8, 0.7, 0.6, signal_conflict=True)
        without = compute_merged_confidence(0.8, 0.7, 0.6, signal_conflict=False)
        assert with_conflict < without

    def test_cap_1(self):
        assert compute_merged_confidence(1.0, 1.0, 1.0) <= 1.0

    def test_floor_0(self):
        assert compute_merged_confidence(0.0, 0.0, 0.0, signal_conflict=True) >= 0.0


class TestMergeVibeTags:
    def test_consensus_first(self):
        tags = merge_vibe_tags(["a", "b"], ["a", "c"])
        assert tags[0] == "a"

    def test_max_8(self):
        d = [f"d{i}" for i in range(6)]
        c = [f"c{i}" for i in range(6)]
        assert len(merge_vibe_tags(d, c)) <= 8


class TestScoreCrossReference:
    def test_both_agree(self):
        c = CSignal(0.7, 0.6, 0.4, 10, ["hidden-gem"], True)
        d = DSignal(0.45, 0.8, ["hidden-gem", "scenic"], False, "bundle_primary")
        result = score_cross_reference(c, d)
        assert result.both_agree is True

    def test_d_only(self):
        c = CSignal(0.0, 0.0, None, 0, [], False)
        d = DSignal(0.5, 0.7, ["hidden-gem"], False, "training_prior")
        result = score_cross_reference(c, d)
        assert result.d_only is True

    def test_c_only(self):
        c = CSignal(0.7, 0.6, 0.4, 10, ["hidden-gem"], True)
        d = DSignal(None, 0.0, [], False, "neither")
        result = score_cross_reference(c, d)
        assert result.c_only is True

    def test_both_conflict(self):
        c = CSignal(0.7, 0.6, 0.2, 10, ["hidden-gem"], True)
        d = DSignal(0.9, 0.8, ["iconic-worth-it"], False, "training_prior")
        result = score_cross_reference(c, d)
        assert result.both_conflict is True
        assert result.signal_conflict is True
