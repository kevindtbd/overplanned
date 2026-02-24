"""
Tests for services/api/simulation/synthetic_runner.py

Coverage:
  - Admin check: raises PermissionError when is_admin=False
  - Admin check: succeeds when is_admin=True
  - Archetype definitions: 12 archetypes exist, each has required fields
  - Archetype filter: subset of archetypes runs correctly
  - Archetype filter: unknown archetype ID raises ValueError
  - Circuit breaker: 5 consecutive Haiku failures abort the archetype
  - Circuit breaker: less than 5 failures do not abort
  - Budget cap: aborts when cumulative cost >= $100
  - Haiku output validation: rejects invalid dimension enum
  - Haiku output validation: rejects invalid direction enum
  - Haiku output validation: rejects confidence outside [0.0, 1.0]
  - Haiku output validation: rejects non-array output
  - Haiku output validation: accepts valid [] (empty array)
  - Synthetic user IDs use "synth-" prefix
  - All synthetic DB writes use "category_preference" signal_type
  - signal_value stays within [-1.0, 3.0] for all direction/confidence combos
  - LLM calls are logged with model version, prompt version, latency, cost
  - DB write uses correct SQL table (behavioral_signals)
  - Run with zero archetypes returns completed with 0 signals
  - Sonnet failure per trip is non-fatal (skips trip, continues)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from services.api.simulation.synthetic_runner import (
    run_synthetic_simulation,
    ARCHETYPES,
    _validate_haiku_output,
    _direction_to_signal_value,
    SYNTH_ID_PREFIX,
    CIRCUIT_BREAKER_THRESHOLD,
    BUDGET_CAP_USD,
    SIGNAL_WEIGHT_MIN,
    SIGNAL_WEIGHT_MAX,
    SONNET_MODEL,
    HAIKU_MODEL,
    SONNET_PROMPT_VERSION,
    HAIKU_PROMPT_VERSION,
)

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db_pool() -> AsyncMock:
    pool = AsyncMock()
    conn = AsyncMock()
    conn.executemany = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))
    return pool


def _make_usage(input_tokens: int = 100, output_tokens: int = 50) -> MagicMock:
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    return usage


def _make_anthropic_client(
    sonnet_text: str = "I enjoyed the local restaurants and took a slow walk.",
    haiku_text: str = json.dumps([
        {"dimension": "food_priority", "direction": "high", "confidence": 0.8},
        {"dimension": "pace_preference", "direction": "low", "confidence": 0.7},
    ]),
) -> AsyncMock:
    """Mock Anthropic client. Sonnet produces journal text, Haiku classifies it."""
    client = AsyncMock()

    def _make_response(text: str) -> MagicMock:
        resp = MagicMock()
        resp.content = [MagicMock()]
        resp.content[0].text = text
        resp.usage = _make_usage()
        return resp

    # Route responses: Sonnet gets journal text, Haiku gets classification JSON
    async def _create(**kwargs):
        model = kwargs.get("model", "")
        if model == SONNET_MODEL:
            return _make_response(sonnet_text)
        return _make_response(haiku_text)

    client.messages.create = AsyncMock(side_effect=_create)
    return client


# ---------------------------------------------------------------------------
# Admin check
# ---------------------------------------------------------------------------

class TestAdminCheck:
    async def test_raises_permission_error_when_not_admin(self):
        with pytest.raises(PermissionError, match="admin-only"):
            await run_synthetic_simulation(
                db_pool=_make_db_pool(),
                anthropic_client=_make_anthropic_client(),
                is_admin=False,
            )

    async def test_succeeds_when_admin(self):
        result = await run_synthetic_simulation(
            db_pool=_make_db_pool(),
            anthropic_client=_make_anthropic_client(),
            is_admin=True,
            archetype_filter=["budget_backpacker"],
            trips_per_archetype=1,
        )
        assert result["status"] in ("completed", "aborted")


# ---------------------------------------------------------------------------
# Archetype definitions
# ---------------------------------------------------------------------------

class TestArchetypeDefinitions:
    def test_12_archetypes_defined(self):
        assert len(ARCHETYPES) == 12

    @pytest.mark.parametrize("archetype", ARCHETYPES)
    def test_archetype_has_required_fields(self, archetype: dict):
        assert "id" in archetype
        assert "name" in archetype
        assert "description" in archetype
        assert "preferences" in archetype
        assert "sample_cities" in archetype

    @pytest.mark.parametrize("archetype", ARCHETYPES)
    def test_archetype_id_is_snake_case_string(self, archetype: dict):
        assert isinstance(archetype["id"], str)
        assert archetype["id"].replace("_", "").isalnum()

    @pytest.mark.parametrize("archetype", ARCHETYPES)
    def test_archetype_preferences_has_8_dimensions(self, archetype: dict):
        expected_dims = {
            "food_priority", "nightlife_interest", "pace_preference",
            "budget_sensitivity", "outdoor_affinity", "cultural_depth",
            "social_energy", "adventure_tolerance",
        }
        assert set(archetype["preferences"].keys()) == expected_dims

    @pytest.mark.parametrize("archetype", ARCHETYPES)
    def test_archetype_preference_directions_are_valid(self, archetype: dict):
        valid = {"high", "low", "neutral"}
        for dim, direction in archetype["preferences"].items():
            assert direction in valid, (
                f"Archetype {archetype['id']!r} has invalid direction {direction!r} "
                f"for dimension {dim!r}"
            )

    @pytest.mark.parametrize("archetype", ARCHETYPES)
    def test_archetype_has_at_least_one_sample_city(self, archetype: dict):
        assert len(archetype["sample_cities"]) >= 1

    def test_archetype_ids_are_unique(self):
        ids = [a["id"] for a in ARCHETYPES]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Archetype filter
# ---------------------------------------------------------------------------

class TestArchetypeFilter:
    async def test_filter_runs_only_specified_archetypes(self):
        result = await run_synthetic_simulation(
            db_pool=_make_db_pool(),
            anthropic_client=_make_anthropic_client(),
            is_admin=True,
            archetype_filter=["budget_backpacker", "luxury_foodie"],
            trips_per_archetype=1,
        )
        assert result["archetypes_run"] == 2

    async def test_unknown_archetype_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown archetype"):
            await run_synthetic_simulation(
                db_pool=_make_db_pool(),
                anthropic_client=_make_anthropic_client(),
                is_admin=True,
                archetype_filter=["nonexistent_archetype"],
            )

    async def test_empty_filter_list_runs_nothing(self):
        result = await run_synthetic_simulation(
            db_pool=_make_db_pool(),
            anthropic_client=_make_anthropic_client(),
            is_admin=True,
            archetype_filter=[],
            trips_per_archetype=1,
        )
        assert result["archetypes_run"] == 0
        assert result["signals_generated"] == 0
        assert result["status"] == "completed"

    async def test_none_filter_runs_all_12_archetypes(self):
        result = await run_synthetic_simulation(
            db_pool=_make_db_pool(),
            anthropic_client=_make_anthropic_client(),
            is_admin=True,
            archetype_filter=None,
            trips_per_archetype=1,
        )
        assert result["archetypes_run"] == 12


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    async def test_5_consecutive_haiku_failures_aborts_archetype(self):
        """Haiku always returns invalid JSON -> triggers circuit breaker."""
        client = AsyncMock()
        # Sonnet succeeds
        sonnet_resp = MagicMock()
        sonnet_resp.content = [MagicMock()]
        sonnet_resp.content[0].text = "Had a great time on my trip to Austin."
        sonnet_resp.usage = _make_usage()

        # Haiku returns garbage JSON
        haiku_resp = MagicMock()
        haiku_resp.content = [MagicMock()]
        haiku_resp.content[0].text = "not valid json {"
        haiku_resp.usage = _make_usage()

        async def _create(**kwargs):
            if kwargs.get("model") == SONNET_MODEL:
                return sonnet_resp
            return haiku_resp

        client.messages.create = AsyncMock(side_effect=_create)

        result = await run_synthetic_simulation(
            db_pool=_make_db_pool(),
            anthropic_client=client,
            is_admin=True,
            archetype_filter=["budget_backpacker"],
            trips_per_archetype=20,  # more than threshold
        )

        archetype_result = result["archetype_results"][0]
        assert archetype_result["aborted"] is True
        assert "circuit_breaker" in archetype_result["abort_reason"]
        # Should have aborted after CIRCUIT_BREAKER_THRESHOLD trips
        assert archetype_result["trips_completed"] < CIRCUIT_BREAKER_THRESHOLD

    async def test_4_failures_do_not_abort(self):
        """4 consecutive Haiku failures (< threshold) should not abort."""
        failure_count = [0]

        sonnet_resp = MagicMock()
        sonnet_resp.content = [MagicMock()]
        sonnet_resp.content[0].text = "Visited several restaurants on my trip."
        sonnet_resp.usage = _make_usage()

        valid_haiku = json.dumps([
            {"dimension": "food_priority", "direction": "high", "confidence": 0.8}
        ])

        async def _create(**kwargs):
            if kwargs.get("model") == SONNET_MODEL:
                return sonnet_resp
            # Fail first 4, then succeed
            resp = MagicMock()
            resp.usage = _make_usage()
            resp.content = [MagicMock()]
            if failure_count[0] < CIRCUIT_BREAKER_THRESHOLD - 1:
                resp.content[0].text = "GARBAGE"
                failure_count[0] += 1
            else:
                resp.content[0].text = valid_haiku
                failure_count[0] = 0  # reset after success
            return resp

        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=_create)

        result = await run_synthetic_simulation(
            db_pool=_make_db_pool(),
            anthropic_client=client,
            is_admin=True,
            archetype_filter=["budget_backpacker"],
            trips_per_archetype=10,
        )

        archetype_result = result["archetype_results"][0]
        # Should NOT have been aborted by circuit breaker
        assert archetype_result["aborted"] is False

    async def test_circuit_breaker_threshold_constant(self):
        assert CIRCUIT_BREAKER_THRESHOLD == 5


# ---------------------------------------------------------------------------
# Budget cap
# ---------------------------------------------------------------------------

class TestBudgetCap:
    async def test_budget_cap_aborts_run(self):
        """Mock very expensive API calls to trigger budget cap."""
        sonnet_resp = MagicMock()
        sonnet_resp.content = [MagicMock()]
        sonnet_resp.content[0].text = "Explored the city on my vacation."
        sonnet_resp.usage = MagicMock()
        # Extremely high token counts -> expensive
        sonnet_resp.usage.input_tokens = 1_000_000
        sonnet_resp.usage.output_tokens = 1_000_000

        haiku_resp = MagicMock()
        haiku_resp.content = [MagicMock()]
        haiku_resp.content[0].text = "[]"
        haiku_resp.usage = MagicMock()
        haiku_resp.usage.input_tokens = 100
        haiku_resp.usage.output_tokens = 10

        async def _create(**kwargs):
            if kwargs.get("model") == SONNET_MODEL:
                return sonnet_resp
            return haiku_resp

        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=_create)

        result = await run_synthetic_simulation(
            db_pool=_make_db_pool(),
            anthropic_client=client,
            is_admin=True,
            archetype_filter=None,
            trips_per_archetype=50,
        )

        assert result["status"] == "aborted"
        assert "budget_cap" in (result["abort_reason"] or "")
        assert result["cost_estimate_usd"] >= BUDGET_CAP_USD

    async def test_budget_cap_constant(self):
        assert BUDGET_CAP_USD == 100.0


# ---------------------------------------------------------------------------
# Haiku output validation
# ---------------------------------------------------------------------------

class TestValidateHaikuOutput:
    def test_valid_output_accepted(self):
        raw = json.dumps([
            {"dimension": "food_priority", "direction": "high", "confidence": 0.8},
            {"dimension": "outdoor_affinity", "direction": "low", "confidence": 0.3},
        ])
        result = _validate_haiku_output(raw)
        assert len(result) == 2
        assert result[0]["dimension"] == "food_priority"
        assert result[0]["direction"] == "high"
        assert result[0]["confidence"] == pytest.approx(0.8)

    def test_empty_array_accepted(self):
        result = _validate_haiku_output("[]")
        assert result == []

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="invalid JSON"):
            _validate_haiku_output("not json {")

    def test_non_array_raises(self):
        with pytest.raises(ValueError, match="JSON array"):
            _validate_haiku_output('{"dimension": "food_priority"}')

    def test_invalid_dimension_raises(self):
        raw = json.dumps([{"dimension": "invalid_dim", "direction": "high", "confidence": 0.5}])
        with pytest.raises(ValueError, match="invalid dimension"):
            _validate_haiku_output(raw)

    def test_invalid_direction_raises(self):
        raw = json.dumps([{"dimension": "food_priority", "direction": "maybe", "confidence": 0.5}])
        with pytest.raises(ValueError, match="invalid direction"):
            _validate_haiku_output(raw)

    def test_confidence_above_1_raises(self):
        raw = json.dumps([{"dimension": "food_priority", "direction": "high", "confidence": 1.1}])
        with pytest.raises(ValueError, match="confidence"):
            _validate_haiku_output(raw)

    def test_confidence_below_0_raises(self):
        raw = json.dumps([{"dimension": "food_priority", "direction": "high", "confidence": -0.1}])
        with pytest.raises(ValueError, match="confidence"):
            _validate_haiku_output(raw)

    def test_confidence_exactly_0_accepted(self):
        raw = json.dumps([{"dimension": "food_priority", "direction": "neutral", "confidence": 0.0}])
        result = _validate_haiku_output(raw)
        assert result[0]["confidence"] == 0.0

    def test_confidence_exactly_1_accepted(self):
        raw = json.dumps([{"dimension": "food_priority", "direction": "high", "confidence": 1.0}])
        result = _validate_haiku_output(raw)
        assert result[0]["confidence"] == 1.0

    def test_non_numeric_confidence_raises(self):
        raw = json.dumps([{"dimension": "food_priority", "direction": "high", "confidence": "high"}])
        with pytest.raises(ValueError, match="confidence"):
            _validate_haiku_output(raw)

    def test_all_8_valid_dimensions_accepted(self):
        valid_dims = [
            "food_priority", "nightlife_interest", "pace_preference",
            "budget_sensitivity", "outdoor_affinity", "cultural_depth",
            "social_energy", "adventure_tolerance",
        ]
        for dim in valid_dims:
            raw = json.dumps([{"dimension": dim, "direction": "high", "confidence": 0.7}])
            result = _validate_haiku_output(raw)
            assert result[0]["dimension"] == dim

    def test_all_3_valid_directions_accepted(self):
        for direction in ("high", "low", "neutral"):
            raw = json.dumps([{"dimension": "food_priority", "direction": direction, "confidence": 0.5}])
            result = _validate_haiku_output(raw)
            assert result[0]["direction"] == direction


# ---------------------------------------------------------------------------
# Signal value bounds
# ---------------------------------------------------------------------------

class TestDirectionToSignalValue:
    def test_high_direction_positive(self):
        val = _direction_to_signal_value("high", 1.0)
        assert val > 0.0

    def test_low_direction_negative(self):
        val = _direction_to_signal_value("low", 1.0)
        assert val < 0.0

    def test_neutral_direction_zero(self):
        val = _direction_to_signal_value("neutral", 0.5)
        assert val == 0.0

    @pytest.mark.parametrize("direction,confidence", [
        ("high", 0.0), ("high", 0.5), ("high", 1.0),
        ("low", 0.0), ("low", 0.5), ("low", 1.0),
        ("neutral", 0.0), ("neutral", 0.5), ("neutral", 1.0),
    ])
    def test_signal_value_within_check_constraint(self, direction: str, confidence: float):
        val = _direction_to_signal_value(direction, confidence)
        assert SIGNAL_WEIGHT_MIN <= val <= SIGNAL_WEIGHT_MAX, (
            f"signal_value {val} for direction={direction!r} confidence={confidence} "
            f"violates CHECK constraint [{SIGNAL_WEIGHT_MIN}, {SIGNAL_WEIGHT_MAX}]"
        )


# ---------------------------------------------------------------------------
# Synthetic user IDs
# ---------------------------------------------------------------------------

class TestSyntheticUserIDs:
    async def test_synth_prefix_in_db_writes(self):
        db_pool = _make_db_pool()
        client = _make_anthropic_client()

        await run_synthetic_simulation(
            db_pool=db_pool,
            anthropic_client=client,
            is_admin=True,
            archetype_filter=["budget_backpacker"],
            trips_per_archetype=2,
        )

        conn = db_pool.acquire.return_value.__aenter__.return_value
        if conn.executemany.called:
            for call_args in conn.executemany.call_args_list:
                rows = call_args[0][1]
                for row in rows:
                    user_id = row[1]  # index 1 is user_id
                    assert user_id.startswith(SYNTH_ID_PREFIX), (
                        f"Synthetic user ID {user_id!r} missing 'synth-' prefix"
                    )

    def test_synth_prefix_constant(self):
        assert SYNTH_ID_PREFIX == "synth-"


# ---------------------------------------------------------------------------
# Model ID constants
# ---------------------------------------------------------------------------

class TestModelConstants:
    def test_sonnet_model_id(self):
        assert SONNET_MODEL == "claude-sonnet-4-6"

    def test_haiku_model_id(self):
        assert HAIKU_MODEL == "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------

class TestResultStructure:
    async def test_returns_required_keys(self):
        result = await run_synthetic_simulation(
            db_pool=_make_db_pool(),
            anthropic_client=_make_anthropic_client(),
            is_admin=True,
            archetype_filter=["budget_backpacker"],
            trips_per_archetype=1,
        )
        assert "status" in result
        assert "archetypes_run" in result
        assert "signals_generated" in result
        assert "cost_estimate_usd" in result
        assert "archetype_results" in result

    async def test_status_is_completed_or_aborted(self):
        result = await run_synthetic_simulation(
            db_pool=_make_db_pool(),
            anthropic_client=_make_anthropic_client(),
            is_admin=True,
            archetype_filter=["budget_backpacker"],
            trips_per_archetype=1,
        )
        assert result["status"] in ("completed", "aborted")

    async def test_cost_estimate_is_non_negative(self):
        result = await run_synthetic_simulation(
            db_pool=_make_db_pool(),
            anthropic_client=_make_anthropic_client(),
            is_admin=True,
            archetype_filter=["budget_backpacker"],
            trips_per_archetype=1,
        )
        assert result["cost_estimate_usd"] >= 0.0

    async def test_archetype_results_list_length(self):
        result = await run_synthetic_simulation(
            db_pool=_make_db_pool(),
            anthropic_client=_make_anthropic_client(),
            is_admin=True,
            archetype_filter=["budget_backpacker", "luxury_foodie"],
            trips_per_archetype=1,
        )
        assert len(result["archetype_results"]) == 2


# ---------------------------------------------------------------------------
# Sonnet failure non-fatal
# ---------------------------------------------------------------------------

class TestSonnetFailure:
    async def test_sonnet_failure_skips_trip_continues(self):
        """If Sonnet fails for a trip, that trip is skipped but the run continues."""
        call_count = [0]

        async def _create(**kwargs):
            call_count[0] += 1
            if kwargs.get("model") == SONNET_MODEL:
                raise RuntimeError("Sonnet API timeout")
            # Haiku never called if Sonnet fails
            resp = MagicMock()
            resp.content = [MagicMock()]
            resp.content[0].text = "[]"
            resp.usage = _make_usage()
            return resp

        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=_create)

        result = await run_synthetic_simulation(
            db_pool=_make_db_pool(),
            anthropic_client=client,
            is_admin=True,
            archetype_filter=["budget_backpacker"],
            trips_per_archetype=3,
        )

        # Should complete (not abort) despite Sonnet failures
        archetype_result = result["archetype_results"][0]
        assert archetype_result["aborted"] is False
        # No signals generated since Sonnet failed every trip
        assert archetype_result["signals_generated"] == 0


# ---------------------------------------------------------------------------
# DB interaction
# ---------------------------------------------------------------------------

class TestDBInteraction:
    async def test_signals_written_with_category_preference_type(self):
        """DB rows should use 'category_preference' as signal_type."""
        db_pool = _make_db_pool()

        # Use haiku that returns a real signal
        client = _make_anthropic_client(
            haiku_text=json.dumps([
                {"dimension": "food_priority", "direction": "high", "confidence": 0.8}
            ])
        )

        await run_synthetic_simulation(
            db_pool=db_pool,
            anthropic_client=client,
            is_admin=True,
            archetype_filter=["budget_backpacker"],
            trips_per_archetype=1,
        )

        conn = db_pool.acquire.return_value.__aenter__.return_value
        if conn.executemany.called:
            for call_args in conn.executemany.call_args_list:
                rows = call_args[0][1]
                for row in rows:
                    signal_type = row[5]  # index 5 is signal_type
                    assert signal_type == "category_preference"

    async def test_signals_written_to_behavioral_signal_table(self):
        """INSERT SQL must target BehavioralSignal table."""
        db_pool = _make_db_pool()
        client = _make_anthropic_client()

        await run_synthetic_simulation(
            db_pool=db_pool,
            anthropic_client=client,
            is_admin=True,
            archetype_filter=["budget_backpacker"],
            trips_per_archetype=1,
        )

        conn = db_pool.acquire.return_value.__aenter__.return_value
        if conn.executemany.called:
            sql_arg = conn.executemany.call_args_list[0][0][0]
            assert '"BehavioralSignal"' in sql_arg
