"""Tests for Pipeline D validation gate."""
import pytest
from services.api.pipeline.research_validator import (
    validate_pass_a,
    validate_pass_b,
    validate_full,
    ValidationResult,
)


class TestValidatePassA:
    def test_passes_valid(self):
        synthesis = {
            "neighborhood_character": {"old_bend": "walkable"},
            "temporal_patterns": {"summer": "busy"},
            "peak_and_decline_flags": [],
            "source_amplification_flags": [],
            "divergence_signals": [],
            "synthesis_confidence": 0.75,
        }
        result = validate_pass_a(synthesis)
        assert result.passed
        assert len(result.errors) == 0

    def test_fails_missing_field(self):
        result = validate_pass_a({"neighborhood_character": {}})
        assert not result.passed

    def test_fails_bad_confidence(self):
        synthesis = {
            "neighborhood_character": {}, "temporal_patterns": {},
            "peak_and_decline_flags": [], "source_amplification_flags": [],
            "divergence_signals": [], "synthesis_confidence": 1.5,
        }
        result = validate_pass_a(synthesis)
        assert not result.passed


class TestValidatePassB:
    def _v(self, **kw):
        base = {"venue_name": "Test", "vibe_tags": ["hidden-gem"],
                "tourist_score": 0.5, "research_confidence": 0.7,
                "knowledge_source": "bundle_primary"}
        base.update(kw)
        return base

    def test_passes_valid(self):
        result = validate_pass_b([self._v()], valid_tags={"hidden-gem"})
        assert result.passed

    def test_warns_over_confidence(self):
        venues = [self._v(research_confidence=0.95) for _ in range(10)]
        result = validate_pass_b(venues, valid_tags={"hidden-gem"})
        assert any("over-confidence" in w.lower() for w in result.warnings)

    def test_warns_tag_concentration(self):
        venues = [self._v(vibe_tags=["hidden-gem"]) for _ in range(10)]
        result = validate_pass_b(venues, valid_tags={"hidden-gem"})
        assert any("concentration" in w.lower() for w in result.warnings)

    def test_warns_training_prior_heavy(self):
        venues = [self._v(knowledge_source="training_prior") for _ in range(10)]
        result = validate_pass_b(venues, valid_tags={"hidden-gem"})
        assert any("training_prior" in w.lower() for w in result.warnings)

    def test_fails_score_out_of_range(self):
        venues = [self._v(tourist_score=2.0)]
        result = validate_pass_b(venues, valid_tags={"hidden-gem"})
        assert not result.passed


class TestValidateFull:
    def test_semantic_warns_low_scores(self):
        venues = [{"venue_name": f"V{i}", "vibe_tags": [], "tourist_score": 0.1,
                    "research_confidence": 0.2, "knowledge_source": "bundle_primary"}
                   for i in range(10)]
        result = validate_full(
            pass_a={"synthesis_confidence": 0.8, "neighborhood_character": {},
                    "temporal_patterns": {}, "peak_and_decline_flags": [],
                    "source_amplification_flags": [], "divergence_signals": []},
            venues=venues, valid_tags=set(), c_baseline_median=0.65)
        assert any("semantic" in w.lower() or "injection" in w.lower() for w in result.warnings)

    def test_passes_clean_data(self):
        venues = [{"venue_name": "V1", "vibe_tags": ["hidden-gem"], "tourist_score": 0.5,
                    "research_confidence": 0.7, "knowledge_source": "bundle_primary"}]
        result = validate_full(
            pass_a={"synthesis_confidence": 0.8, "neighborhood_character": {},
                    "temporal_patterns": {}, "peak_and_decline_flags": [],
                    "source_amplification_flags": [], "divergence_signals": []},
            venues=venues, valid_tags={"hidden-gem"}, c_baseline_median=0.5)
        assert result.passed
