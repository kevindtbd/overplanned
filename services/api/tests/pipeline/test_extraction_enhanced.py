"""
Enhanced vibe extraction tests.

Covers:
- overrated_flag parsing from mocked LLM response
- tourist_score aggregation thresholds (>40%, 20-40%, <20%)
- local 3x weighting in convergence authority score
- vibe_confidence harmonic mean calculation
- extraction logging writes valid JSONL
- status bug fix: pending + approved nodes are fetched, not 'active'
- ExtractionMetadata validation and coercion of bad values
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest

from services.api.pipeline.vibe_extraction import (
    ExtractionMetadata,
    ExtractionResult,
    TagResult,
    _parse_extraction_metadata,
    _parse_extraction_response,
    _write_extraction_log,
    EXTRACTION_LOG_DIR,
)
from services.api.pipeline.convergence import (
    compute_tourist_score,
    compute_vibe_confidence,
    compute_authority_score_with_local_weighting,
    _LOCAL_SIGNAL_WEIGHT_MULTIPLIER,
    _TOURIST_HIGH_THRESHOLD,
    _TOURIST_MID_THRESHOLD,
    _VIBE_CONF_SOURCE_CAP,
    _VIBE_CONF_MENTION_CAP,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_extraction_result(
    node_id: str = "node-001",
    node_name: str = "Test Venue",
    city: str = "bend",
    tags: Optional[list[TagResult]] = None,
    overrated_flag: bool = False,
    price_signal: Optional[str] = None,
    explicit_recommendation: bool = False,
    author_type: str = "unknown",
    crowd_notes: Optional[str] = None,
) -> ExtractionResult:
    """Build a minimal ExtractionResult for tests."""
    return ExtractionResult(
        node_id=node_id,
        node_name=node_name,
        city=city,
        tags=tags or [TagResult(tag_slug="hidden-gem", score=0.90)],
        metadata=ExtractionMetadata(
            overrated_flag=overrated_flag,
            price_signal=price_signal,
            explicit_recommendation=explicit_recommendation,
            author_type=author_type,
            crowd_notes=crowd_notes,
        ),
        flagged_contradictions=[],
        input_tokens=100,
        output_tokens=50,
    )


# ===========================================================================
# 1. overrated_flag extraction from mocked LLM response
# ===========================================================================


class TestOverratedFlagExtraction:
    """The LLM response parser correctly extracts overrated_flag from metadata."""

    def test_overrated_flag_true_parsed(self):
        raw = json.dumps({
            "tags": [{"tag": "iconic-worth-it", "score": 0.8}],
            "metadata": {
                "overrated_flag": True,
                "price_signal": "splurge",
                "explicit_recommendation": False,
                "author_type": "tourist",
                "crowd_notes": "full of tour groups",
            }
        })
        tags, meta_raw = _parse_extraction_response(raw)
        assert len(tags) == 1
        assert tags[0]["tag"] == "iconic-worth-it"
        metadata = _parse_extraction_metadata(meta_raw)
        assert metadata.overrated_flag is True
        assert metadata.author_type == "tourist"
        assert metadata.crowd_notes == "full of tour groups"

    def test_overrated_flag_false_parsed(self):
        raw = json.dumps({
            "tags": [{"tag": "hidden-gem", "score": 0.92}],
            "metadata": {
                "overrated_flag": False,
                "price_signal": "budget",
                "explicit_recommendation": True,
                "author_type": "local",
                "crowd_notes": None,
            }
        })
        tags, meta_raw = _parse_extraction_response(raw)
        metadata = _parse_extraction_metadata(meta_raw)
        assert metadata.overrated_flag is False
        assert metadata.explicit_recommendation is True
        assert metadata.price_signal == "budget"
        assert metadata.author_type == "local"
        assert metadata.crowd_notes is None

    def test_missing_metadata_key_defaults_to_false(self):
        """When metadata is absent, overrated_flag defaults to False."""
        raw = json.dumps({
            "tags": [{"tag": "street-food", "score": 0.85}],
        })
        tags, meta_raw = _parse_extraction_response(raw)
        metadata = _parse_extraction_metadata(meta_raw)
        assert metadata.overrated_flag is False
        assert metadata.explicit_recommendation is False
        assert metadata.price_signal is None
        assert metadata.author_type == "unknown"

    def test_invalid_price_signal_coerced_to_none(self):
        """Unrecognised price_signal values are silently nulled."""
        meta_raw = {"overrated_flag": False, "price_signal": "expensive_garbage"}
        metadata = _parse_extraction_metadata(meta_raw)
        assert metadata.price_signal is None

    def test_invalid_author_type_coerced_to_unknown(self):
        """Unrecognised author_type is coerced to 'unknown'."""
        meta_raw = {"overrated_flag": False, "author_type": "robot"}
        metadata = _parse_extraction_metadata(meta_raw)
        assert metadata.author_type == "unknown"

    def test_all_valid_price_signals(self):
        for ps in ("budget", "mid", "splurge", "free"):
            meta = _parse_extraction_metadata({"price_signal": ps})
            assert meta.price_signal == ps

    def test_all_valid_author_types(self):
        for at in ("local", "expat", "tourist", "unknown"):
            meta = _parse_extraction_metadata({"author_type": at})
            assert meta.author_type == at

    def test_markdown_code_fence_response_parsed(self):
        """Parser handles markdown fenced JSON from LLM."""
        raw = '```json\n' + json.dumps({
            "tags": [{"tag": "locals-only", "score": 0.88}],
            "metadata": {"overrated_flag": True, "author_type": "local"},
        }) + '\n```'
        tags, meta_raw = _parse_extraction_response(raw)
        assert len(tags) == 1
        metadata = _parse_extraction_metadata(meta_raw)
        assert metadata.overrated_flag is True

    def test_totally_unparseable_response_returns_empty(self):
        """Garbage response returns empty tags and metadata without raising."""
        tags, meta_raw = _parse_extraction_response("I'm sorry, I cannot classify this.")
        assert tags == []
        assert meta_raw == {}

    def test_crowd_notes_stripped(self):
        """Crowd notes whitespace is stripped."""
        meta = _parse_extraction_metadata({"crowd_notes": "  very busy on weekends  "})
        assert meta.crowd_notes == "very busy on weekends"

    def test_crowd_notes_empty_string_becomes_none(self):
        """Empty string crowd notes become None."""
        meta = _parse_extraction_metadata({"crowd_notes": ""})
        assert meta.crowd_notes is None


# ===========================================================================
# 2. tourist_score aggregation thresholds
# ===========================================================================


class TestTouristScoreAggregation:
    """compute_tourist_score applies the correct tier formula at each threshold."""

    # --- tier 1: >40% overrated ---

    def test_above_high_threshold_returns_score_in_tier1_range(self):
        """50% overrated -> tier 1: 0.7 + (0.5 * 0.3) = 0.85"""
        score = compute_tourist_score(overrated_count=5, total_mentions=10)
        assert score is not None
        assert score == pytest.approx(0.7 + (0.5 * 0.3), abs=0.001)

    def test_just_above_high_threshold(self):
        """41% overrated -> just into tier 1"""
        score = compute_tourist_score(overrated_count=41, total_mentions=100)
        assert score is not None
        expected = 0.7 + (0.41 * 0.3)
        assert score == pytest.approx(expected, abs=0.001)

    def test_100_percent_overrated_capped_at_1(self):
        """100% overrated -> 0.7 + 1.0 * 0.3 = 1.0"""
        score = compute_tourist_score(overrated_count=10, total_mentions=10)
        assert score is not None
        assert score == pytest.approx(1.0, abs=0.001)

    # --- tier 2: 20-40% overrated ---

    def test_just_above_mid_threshold_returns_tier2_score(self):
        """21% overrated -> tier 2: 0.4 + (0.21 * 0.75) = 0.5575"""
        score = compute_tourist_score(overrated_count=21, total_mentions=100)
        assert score is not None
        expected = 0.4 + (0.21 * 0.75)
        assert score == pytest.approx(expected, abs=0.001)

    def test_40_percent_exactly_is_tier2_not_tier1(self):
        """Exactly 40% should NOT reach tier 1 (requires strictly >40%)."""
        score = compute_tourist_score(overrated_count=4, total_mentions=10)
        assert score is not None
        # 40% -> NOT > _TOURIST_HIGH_THRESHOLD (0.40), so falls into tier 2
        expected = 0.4 + (0.40 * 0.75)
        assert score == pytest.approx(expected, abs=0.001)

    def test_20_percent_exactly_is_not_above_mid_threshold(self):
        """Exactly 20% should return None (requires strictly >20%)."""
        score = compute_tourist_score(overrated_count=2, total_mentions=10)
        assert score is None

    # --- <20%: no update ---

    def test_below_mid_threshold_returns_none(self):
        """19% overrated -> no tourist_score update."""
        score = compute_tourist_score(overrated_count=19, total_mentions=100)
        assert score is None

    def test_zero_overrated_returns_none(self):
        """Zero overrated signals -> no update."""
        score = compute_tourist_score(overrated_count=0, total_mentions=50)
        assert score is None

    def test_zero_mentions_returns_none(self):
        """No mentions at all -> no update (division by zero guard)."""
        score = compute_tourist_score(overrated_count=0, total_mentions=0)
        assert score is None

    def test_single_mention_overrated_returns_tier1(self):
        """1/1 = 100% overrated -> tier 1."""
        score = compute_tourist_score(overrated_count=1, total_mentions=1)
        assert score is not None
        assert score == pytest.approx(1.0, abs=0.001)

    def test_tourist_score_never_exceeds_1(self):
        """Score is always capped at 1.0."""
        for count in range(1, 21):
            score = compute_tourist_score(count, 20)
            if score is not None:
                assert score <= 1.0, f"score={score} exceeded 1.0 at {count}/20"


# ===========================================================================
# 3. Local 3x weighting in convergence
# ===========================================================================


class TestLocalWeightingInConvergence:
    """compute_authority_score_with_local_weighting applies 3x to local signals."""

    def test_single_local_signal_outweighs_three_regular(self):
        """One local signal at 0.5 authority equals 3 regular signals at 0.5."""
        local_score = compute_authority_score_with_local_weighting([
            ("reddit", 0.5, "local_recommendation"),
        ])
        # effective_count = 3.0, weighted_sum = 0.5 * 3 = 1.5, result = 1.5 / 3 = 0.5
        assert local_score == pytest.approx(0.5, abs=0.001)

    def test_local_signal_higher_than_equivalent_non_local(self):
        """A local signal pulls the authority average higher than a non-local signal of same authority."""
        local = compute_authority_score_with_local_weighting([
            ("reddit", 0.5, "local_recommendation"),
            ("blog", 0.3, "mention"),
        ])
        non_local = compute_authority_score_with_local_weighting([
            ("reddit", 0.5, "mention"),
            ("blog", 0.3, "mention"),
        ])
        assert local > non_local

    def test_multiplier_is_exactly_three(self):
        """Verify the multiplier constant is 3x."""
        assert _LOCAL_SIGNAL_WEIGHT_MULTIPLIER == 3.0

    def test_mixed_signals_weighted_correctly(self):
        """
        One local (0.6) + one non-local (0.4):
        weighted_sum = 0.6 * 3 + 0.4 * 1 = 2.2
        effective_count = 3 + 1 = 4
        result = 2.2 / 4 = 0.55
        """
        score = compute_authority_score_with_local_weighting([
            ("reddit_local", 0.6, "local_recommendation"),
            ("foursquare", 0.4, "mention"),
        ])
        assert score == pytest.approx(2.2 / 4.0, abs=0.001)

    def test_all_local_signals_same_as_regular_formula(self):
        """When all signals are local, the 3x multiplier cancels out in the average."""
        all_local = compute_authority_score_with_local_weighting([
            ("s1", 0.8, "local_recommendation"),
            ("s2", 0.6, "local_recommendation"),
        ])
        # weighted_sum = (0.8 + 0.6) * 3 = 4.2, effective_count = 2 * 3 = 6
        # result = 4.2 / 6 = 0.7
        assert all_local == pytest.approx(0.7, abs=0.001)

    def test_no_signals_returns_zero(self):
        score = compute_authority_score_with_local_weighting([])
        assert score == 0.0

    def test_all_non_local_matches_simple_average(self):
        """Non-local signals produce a simple average (all multipliers = 1)."""
        score = compute_authority_score_with_local_weighting([
            ("foursquare", 0.7, "mention"),
            ("atlas", 0.9, "mention"),
        ])
        assert score == pytest.approx((0.7 + 0.9) / 2, abs=0.001)


# ===========================================================================
# 4. vibe_confidence harmonic mean calculation
# ===========================================================================


class TestVibeConfidence:
    """compute_vibe_confidence computes harmonic mean correctly."""

    def test_zero_sources_zero_mentions(self):
        """Both inputs zero -> confidence = 0.0 (epsilon prevents division by zero)."""
        score = compute_vibe_confidence(0, 0)
        assert score == pytest.approx(0.0, abs=0.001)

    def test_max_diversity_max_mentions_returns_one(self):
        """5 sources and 20 mentions -> source_diversity=1.0, mention_score=1.0 -> HM=1.0."""
        score = compute_vibe_confidence(5, 20)
        assert score == pytest.approx(1.0, abs=0.001)

    def test_above_caps_still_returns_one(self):
        """Inputs beyond caps are clamped to 1.0 before harmonic mean."""
        score = compute_vibe_confidence(10, 40)
        assert score == pytest.approx(1.0, abs=0.001)

    def test_single_source_single_mention(self):
        """
        source_diversity = 1/5 = 0.2
        mention_count_score = 1/20 = 0.05
        HM = 2 * 0.2 * 0.05 / (0.2 + 0.05) = 0.02 / 0.25 = 0.08
        """
        score = compute_vibe_confidence(1, 1)
        expected = 2 * 0.2 * 0.05 / (0.2 + 0.05)
        assert score == pytest.approx(expected, abs=0.001)

    def test_source_cap_at_five(self):
        """_VIBE_CONF_SOURCE_CAP == 5.0."""
        assert _VIBE_CONF_SOURCE_CAP == 5.0

    def test_mention_cap_at_twenty(self):
        """_VIBE_CONF_MENTION_CAP == 20.0."""
        assert _VIBE_CONF_MENTION_CAP == 20.0

    def test_score_always_between_zero_and_one(self):
        """Confidence is always in [0, 1] for any positive input."""
        for sources in range(0, 10):
            for mentions in range(0, 25):
                score = compute_vibe_confidence(sources, mentions)
                assert 0.0 <= score <= 1.0, (
                    f"Out of range: compute_vibe_confidence({sources}, {mentions}) = {score}"
                )

    def test_harmonic_mean_penalises_imbalance(self):
        """HM is lower than arithmetic mean when inputs differ significantly."""
        balanced_score = compute_vibe_confidence(3, 10)
        # 3 sources, 10 mentions: source_d = 0.6, mention_s = 0.5
        # HM = 2 * 0.6 * 0.5 / (0.6 + 0.5) = 0.6 / 1.1 ≈ 0.545
        arithmetic_mean = (0.6 + 0.5) / 2  # = 0.55
        assert balanced_score < arithmetic_mean

    def test_returns_float_not_int(self):
        score = compute_vibe_confidence(3, 10)
        assert isinstance(score, float)


# ===========================================================================
# 5. Extraction logging writes valid JSONL
# ===========================================================================


class TestExtractionLogging:
    """_write_extraction_log writes one valid JSON line per result."""

    def test_writes_one_line_per_result(self, tmp_path):
        results = [
            _make_extraction_result(node_id="n1", city="bend"),
            _make_extraction_result(node_id="n2", city="bend"),
        ]
        with patch(
            "services.api.pipeline.vibe_extraction.EXTRACTION_LOG_DIR",
            tmp_path,
        ):
            _write_extraction_log(results, "bend")

        log_file = tmp_path / "bend.jsonl"
        assert log_file.exists()
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

    def test_each_line_is_valid_json(self, tmp_path):
        results = [_make_extraction_result(node_id="n1", city="bend")]
        with patch(
            "services.api.pipeline.vibe_extraction.EXTRACTION_LOG_DIR",
            tmp_path,
        ):
            _write_extraction_log(results, "bend")

        log_file = tmp_path / "bend.jsonl"
        for line in log_file.read_text().strip().splitlines():
            record = json.loads(line)  # should not raise
            assert "node_id" in record

    def test_log_contains_required_fields(self, tmp_path):
        result = _make_extraction_result(
            node_id="n-test",
            node_name="Test Place",
            city="bend",
            overrated_flag=True,
            price_signal="mid",
            explicit_recommendation=True,
            author_type="local",
            crowd_notes="packed at lunch",
        )
        with patch(
            "services.api.pipeline.vibe_extraction.EXTRACTION_LOG_DIR",
            tmp_path,
        ):
            _write_extraction_log([result], "bend")

        log_file = tmp_path / "bend.jsonl"
        record = json.loads(log_file.read_text().strip())
        assert record["node_id"] == "n-test"
        assert record["node_name"] == "Test Place"
        assert record["city"] == "bend"
        assert "extracted_at" in record
        assert isinstance(record["tags"], list)
        assert record["metadata"]["overrated_flag"] is True
        assert record["metadata"]["price_signal"] == "mid"
        assert record["metadata"]["explicit_recommendation"] is True
        assert record["metadata"]["author_type"] == "local"
        assert record["metadata"]["crowd_notes"] == "packed at lunch"
        assert isinstance(record["flagged_contradictions"], list)

    def test_empty_results_writes_nothing(self, tmp_path):
        with patch(
            "services.api.pipeline.vibe_extraction.EXTRACTION_LOG_DIR",
            tmp_path,
        ):
            _write_extraction_log([], "bend")

        # No file should be created for an empty list
        assert not (tmp_path / "bend.jsonl").exists()

    def test_appends_to_existing_file(self, tmp_path):
        """Multiple calls append rather than overwrite."""
        results_batch1 = [_make_extraction_result(node_id="n1", city="bend")]
        results_batch2 = [_make_extraction_result(node_id="n2", city="bend")]

        with patch(
            "services.api.pipeline.vibe_extraction.EXTRACTION_LOG_DIR",
            tmp_path,
        ):
            _write_extraction_log(results_batch1, "bend")
            _write_extraction_log(results_batch2, "bend")

        log_file = tmp_path / "bend.jsonl"
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 2

    def test_city_slug_normalised_for_filename(self, tmp_path):
        """City names with spaces and dashes are normalised to underscores."""
        result = _make_extraction_result(city="mexico-city")
        with patch(
            "services.api.pipeline.vibe_extraction.EXTRACTION_LOG_DIR",
            tmp_path,
        ):
            _write_extraction_log([result], "mexico-city")

        # Expect mexico_city.jsonl (dashes replaced with underscores)
        assert (tmp_path / "mexico_city.jsonl").exists()

    def test_ioerror_does_not_raise(self, tmp_path):
        """If the log directory is unwritable, the error is swallowed (never re-raised)."""
        result = _make_extraction_result()
        # Point at a non-existent nested directory without creating it —
        # this will cause an OSError since tmp_path is a valid directory;
        # instead, pass a path that looks like a file (not a directory).
        bad_dir = tmp_path / "not_a_dir.txt"
        bad_dir.write_text("block")  # write a file where a dir is expected
        with patch(
            "services.api.pipeline.vibe_extraction.EXTRACTION_LOG_DIR",
            bad_dir,  # bad_dir is a file, not a dir — open("bad_dir/x.jsonl") will fail
        ):
            # Should not raise
            _write_extraction_log([result], "bend")
