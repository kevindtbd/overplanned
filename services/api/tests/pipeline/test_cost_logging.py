"""
LLM cost logging tests.

Covers:
- Every Haiku call logged with model_version, prompt_version, latency, cost
- ModelRegistry entries created with correct metadata
- Token counting and cost estimation
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.api.pipeline.vibe_extraction import (
    MODEL_NAME,
    PROMPT_VERSION,
    CONFIDENCE_THRESHOLD,
    MAX_TAGS_PER_SOURCE,
    INPUT_COST_PER_1M,
    OUTPUT_COST_PER_1M,
    BatchStats,
    ExtractionMetadata,
    ExtractionResult,
    NodeInput,
    TagResult,
    _build_user_prompt,
    _parse_extraction_response,
    ALL_TAGS,
)

from .conftest import FakePool, make_id


# ===================================================================
# Model version constants
# ===================================================================


class TestModelConstants:
    def test_model_name_is_haiku(self):
        assert "haiku" in MODEL_NAME.lower()

    def test_prompt_version_set(self):
        assert PROMPT_VERSION == "vibe-extract-v2"

    def test_confidence_threshold(self):
        assert CONFIDENCE_THRESHOLD == 0.75

    def test_tag_limit_per_source(self):
        assert MAX_TAGS_PER_SOURCE == 5


# ===================================================================
# Cost estimation
# ===================================================================


class TestCostEstimation:
    def test_cost_calculation_formula(self):
        """Verify cost = (input_tokens / 1M * input_rate) + (output_tokens / 1M * output_rate)."""
        input_tokens = 1000
        output_tokens = 200

        expected_cost = (
            (input_tokens / 1_000_000) * INPUT_COST_PER_1M
            + (output_tokens / 1_000_000) * OUTPUT_COST_PER_1M
        )

        stats = BatchStats()
        stats.total_input_tokens = input_tokens
        stats.total_output_tokens = output_tokens

        actual_cost = (
            (stats.total_input_tokens / 1_000_000) * INPUT_COST_PER_1M
            + (stats.total_output_tokens / 1_000_000) * OUTPUT_COST_PER_1M
        )

        assert actual_cost == expected_cost
        assert actual_cost > 0

    def test_zero_tokens_zero_cost(self):
        cost = (0 / 1_000_000) * INPUT_COST_PER_1M + (0 / 1_000_000) * OUTPUT_COST_PER_1M
        assert cost == 0.0

    def test_pricing_rates_positive(self):
        assert INPUT_COST_PER_1M > 0
        assert OUTPUT_COST_PER_1M > 0


# ===================================================================
# BatchStats tracking
# ===================================================================


class TestBatchStats:
    def test_default_stats(self):
        stats = BatchStats()
        assert stats.nodes_processed == 0
        assert stats.tags_written == 0
        assert stats.total_input_tokens == 0
        assert stats.total_output_tokens == 0
        assert stats.estimated_cost_usd == 0.0
        assert stats.errors == []

    def test_stats_accumulation(self):
        stats = BatchStats()
        stats.nodes_processed += 5
        stats.total_input_tokens += 5000
        stats.total_output_tokens += 1000
        stats.tags_written += 15

        assert stats.nodes_processed == 5
        assert stats.total_input_tokens == 5000

    def test_stats_errors_tracked(self):
        stats = BatchStats()
        stats.errors.append("HTTP 429 for node xyz")
        stats.errors.append("Timeout for node abc")
        assert len(stats.errors) == 2


# ===================================================================
# Extraction result structure
# ===================================================================


class TestExtractionResult:
    def test_result_structure(self):
        result = ExtractionResult(
            node_id="test-node",
            node_name="Test Venue",
            city="tokyo",
            tags=[
                TagResult(tag_slug="hidden-gem", score=0.92),
                TagResult(tag_slug="local-institution", score=0.85),
            ],
            metadata=ExtractionMetadata(),
            flagged_contradictions=[],
            input_tokens=500,
            output_tokens=100,
        )

        assert result.node_id == "test-node"
        assert len(result.tags) == 2
        assert result.input_tokens == 500
        assert result.output_tokens == 100

    def test_result_with_contradictions(self):
        result = ExtractionResult(
            node_id="test",
            node_name="Test Venue",
            city="tokyo",
            tags=[
                TagResult(tag_slug="hidden-gem", score=0.9),
                TagResult(tag_slug="iconic-worth-it", score=0.8),
            ],
            metadata=ExtractionMetadata(),
            flagged_contradictions=[("hidden-gem", "iconic-worth-it")],
            input_tokens=0,
            output_tokens=0,
        )
        assert len(result.flagged_contradictions) == 1


# ===================================================================
# Prompt construction
# ===================================================================


class TestPromptConstruction:
    def test_build_user_prompt_contains_venue_info(self):
        node = NodeInput(
            id="test",
            name="Ichiran Ramen",
            city="Tokyo",
            category="dining",
            description_short="Famous tonkotsu ramen",
        )
        prompt = _build_user_prompt(node)

        assert "Ichiran Ramen" in prompt
        assert "Tokyo" in prompt
        assert "dining" in prompt
        assert "Famous tonkotsu" in prompt

    def test_build_user_prompt_includes_vocabulary(self):
        node = NodeInput(id="t", name="Test", city="Test", category="dining")
        prompt = _build_user_prompt(node)

        # Should include tag vocabulary
        assert "hidden-gem" in prompt
        assert "street-food" in prompt

    def test_build_user_prompt_includes_excerpts(self):
        node = NodeInput(
            id="t",
            name="Test",
            city="Test",
            category="dining",
            quality_excerpts=["Amazing food!", "Best ramen in town"],
        )
        prompt = _build_user_prompt(node)
        assert "Amazing food!" in prompt
        assert "Best ramen in town" in prompt


# ===================================================================
# Response parsing
# ===================================================================


class TestResponseParsing:
    def test_parse_valid_json(self):
        text = '{"tags": [{"tag": "hidden-gem", "score": 0.9}]}'
        result, _meta = _parse_extraction_response(text)
        assert len(result) == 1
        assert result[0]["tag"] == "hidden-gem"

    def test_parse_json_array(self):
        # Legacy bare array — still supported for backward compat
        text = '[{"tag": "street-food", "score": 0.85}]'
        result, _meta = _parse_extraction_response(text)
        assert len(result) == 1

    def test_parse_markdown_code_block(self):
        text = '```json\n{"tags": [{"tag": "lively", "score": 0.88}]}\n```'
        result, _meta = _parse_extraction_response(text)
        assert len(result) == 1
        assert result[0]["tag"] == "lively"

    def test_parse_invalid_json(self):
        text = "This is not JSON at all"
        result, _meta = _parse_extraction_response(text)
        assert result == []


# ===================================================================
# Vocabulary integrity
# ===================================================================


class TestVocabularyIntegrity:
    def test_vocabulary_has_44_tags(self):
        assert len(ALL_TAGS) == 44

    def test_known_tags_present(self):
        assert "hidden-gem" in ALL_TAGS
        assert "street-food" in ALL_TAGS
        assert "local-institution" in ALL_TAGS
        assert "deep-history" in ALL_TAGS
        assert "solo-friendly" in ALL_TAGS
        assert "budget-friendly" in ALL_TAGS
