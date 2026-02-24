"""
Tests for Phase 6.9 -- Learned Arbitration (DATA-GATED).

Covers:
- Readiness check (>= 1500 events, < 1500 events)
- Feature extraction (known rules, context snapshot, persona dims)
- Train returns metrics (accuracy, auc_approx, n_events)
- Predict returns confidence in [0, 1]
- Not ready with < 1500 events
- Save/load round-trip with hash verification
- SQL structure validation
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import numpy as np
import pytest

from services.api.models.learned_arbitration import (
    DecisionStump,
    LearnedArbConfig,
    LearnedArbitrator,
    _KNOWN_RULES,
    _READINESS_SQL,
    _TRAINING_DATA_SQL,
    _train_adaboost,
    _sigmoid,
)


# ===================================================================
# Readiness check
# ===================================================================


class TestIsReady:
    @pytest.mark.asyncio
    async def test_ready_with_enough_events(self):
        arb = LearnedArbitrator(LearnedArbConfig(min_events=1500))
        pool = AsyncMock()
        pool.fetchrow = AsyncMock(return_value={"cnt": 2000})
        assert await arb.is_ready(pool) is True

    @pytest.mark.asyncio
    async def test_not_ready_below_threshold(self):
        arb = LearnedArbitrator(LearnedArbConfig(min_events=1500))
        pool = AsyncMock()
        pool.fetchrow = AsyncMock(return_value={"cnt": 500})
        assert await arb.is_ready(pool) is False

    @pytest.mark.asyncio
    async def test_not_ready_none_result(self):
        arb = LearnedArbitrator()
        pool = AsyncMock()
        pool.fetchrow = AsyncMock(return_value=None)
        assert await arb.is_ready(pool) is False


# ===================================================================
# Feature extraction
# ===================================================================


class TestExtractFeatures:
    def test_basic_extraction(self):
        arb = LearnedArbitrator()
        event = {
            "agreementScore": 0.75,
            "arbitrationRule": "ml_preferred",
            "contextSnapshot": {
                "ml_confidence": 0.8,
                "user_signal_count": 42,
                "trip_count": 3,
                "persona": {"adventure": 0.9, "food": 0.6},
            },
        }
        features = arb.extract_features(event)
        assert isinstance(features, np.ndarray)
        # 4 continuous + 5 one-hot + 8 vibe dims = 17
        assert len(features) == 17
        # agreementScore
        assert features[0] == 0.75
        # ml_confidence
        assert features[1] == 0.8
        # user_signal_count
        assert features[2] == 42.0
        # trip_count
        assert features[3] == 3.0
        # one-hot: ml_preferred is index 0 in _KNOWN_RULES
        assert features[4] == 1.0
        assert features[5] == 0.0  # llm_preferred

    def test_unknown_rule_all_zeros(self):
        arb = LearnedArbitrator()
        event = {
            "agreementScore": 0.5,
            "arbitrationRule": "unknown_rule",
            "contextSnapshot": {},
        }
        features = arb.extract_features(event)
        # One-hot should be all zeros for unknown rule
        one_hot_start = 4
        one_hot_end = 4 + len(_KNOWN_RULES)
        assert np.sum(features[one_hot_start:one_hot_end]) == 0.0

    def test_string_context_snapshot(self):
        """contextSnapshot can be a JSON string."""
        arb = LearnedArbitrator()
        event = {
            "agreementScore": 0.5,
            "arbitrationRule": "fallback",
            "contextSnapshot": json.dumps({"ml_confidence": 0.3}),
        }
        features = arb.extract_features(event)
        assert features[1] == 0.3

    def test_null_context_defaults(self):
        arb = LearnedArbitrator()
        event = {
            "agreementScore": None,
            "contextSnapshot": None,
        }
        features = arb.extract_features(event)
        assert features[0] == 0.0  # agreementScore defaults to 0
        assert features[1] == 0.5  # ml_confidence defaults to 0.5


# ===================================================================
# Training
# ===================================================================


class TestTrain:
    @pytest.mark.asyncio
    async def test_train_returns_metrics(self):
        arb = LearnedArbitrator(LearnedArbConfig(min_events=1, n_estimators=5))
        pool = AsyncMock()

        # Create synthetic training data
        events = []
        for i in range(50):
            events.append({
                "arbitrationRule": "ml_preferred" if i % 2 == 0 else "llm_preferred",
                "servedSource": "ml" if i % 2 == 0 else "llm",
                "accepted": i % 2 == 0,  # ML preferred events are accepted
                "agreementScore": 0.5 + (i % 10) * 0.05,
                "contextSnapshot": {
                    "ml_confidence": 0.7 if i % 2 == 0 else 0.3,
                    "user_signal_count": i,
                    "trip_count": i // 10,
                    "persona": {"adventure": 0.5},
                },
            })
        pool.fetch = AsyncMock(return_value=events)

        metrics = await arb.train(pool)
        assert "accuracy" in metrics
        assert "auc_approx" in metrics
        assert "n_events" in metrics
        assert metrics["n_events"] == 50
        assert 0.0 <= metrics["accuracy"] <= 1.0
        assert 0.0 <= metrics["auc_approx"] <= 1.0
        assert arb.is_trained is True

    @pytest.mark.asyncio
    async def test_train_no_data_raises(self):
        arb = LearnedArbitrator()
        pool = AsyncMock()
        pool.fetch = AsyncMock(return_value=[])
        with pytest.raises(ValueError, match="No training data"):
            await arb.train(pool)


# ===================================================================
# Prediction
# ===================================================================


class TestPredict:
    @pytest.mark.asyncio
    async def test_predict_returns_confidence(self):
        arb = LearnedArbitrator(LearnedArbConfig(n_estimators=10))
        pool = AsyncMock()

        events = []
        for i in range(30):
            events.append({
                "arbitrationRule": "ml_preferred",
                "servedSource": "ml",
                "accepted": True,
                "agreementScore": 0.8,
                "contextSnapshot": {"ml_confidence": 0.9},
            })
        pool.fetch = AsyncMock(return_value=events)

        await arb.train(pool)

        features = arb.extract_features({
            "agreementScore": 0.8,
            "arbitrationRule": "ml_preferred",
            "contextSnapshot": {"ml_confidence": 0.9},
        })
        confidence = arb.predict(features)
        assert 0.0 <= confidence <= 1.0

    def test_predict_untrained_raises(self):
        arb = LearnedArbitrator()
        features = np.zeros(17)
        with pytest.raises(RuntimeError, match="not trained"):
            arb.predict(features)


# ===================================================================
# Save / Load
# ===================================================================


class TestSaveLoad:
    @pytest.mark.asyncio
    async def test_round_trip(self):
        arb = LearnedArbitrator(LearnedArbConfig(n_estimators=5))
        pool = AsyncMock()

        events = [
            {
                "arbitrationRule": "ml_preferred",
                "servedSource": "ml",
                "accepted": True,
                "agreementScore": 0.8,
                "contextSnapshot": {},
            }
        ] * 20
        pool.fetch = AsyncMock(return_value=events)
        await arb.train(pool)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "model.json"
            hash1 = arb.save(str(path))

            arb2 = LearnedArbitrator()
            hash2 = arb2.load(str(path))

            assert hash1 == hash2
            assert arb2.is_trained is True

    def test_save_untrained_raises(self):
        arb = LearnedArbitrator()
        with pytest.raises(RuntimeError, match="not trained"):
            arb.save("/tmp/model.json")


# ===================================================================
# SQL structure
# ===================================================================


class TestSQLStructure:
    def test_readiness_sql_references_arbitration_event(self):
        assert '"ArbitrationEvent"' in _READINESS_SQL
        assert '"accepted"' in _READINESS_SQL

    def test_training_sql_has_required_columns(self):
        assert '"arbitrationRule"' in _TRAINING_DATA_SQL
        assert '"servedSource"' in _TRAINING_DATA_SQL
        assert '"accepted"' in _TRAINING_DATA_SQL
        assert '"agreementScore"' in _TRAINING_DATA_SQL
        assert '"contextSnapshot"' in _TRAINING_DATA_SQL
        assert '"createdAt"' in _TRAINING_DATA_SQL


# ===================================================================
# Decision stump serialization
# ===================================================================


class TestDecisionStump:
    def test_round_trip(self):
        stump = DecisionStump()
        stump.feature_idx = 3
        stump.threshold = 0.42
        stump.polarity = -1
        stump.alpha = 0.15

        d = stump.to_dict()
        restored = DecisionStump.from_dict(d)
        assert restored.feature_idx == 3
        assert restored.threshold == 0.42
        assert restored.polarity == -1
        assert restored.alpha == 0.15


# ===================================================================
# Sigmoid
# ===================================================================


class TestSigmoid:
    def test_zero_gives_half(self):
        result = _sigmoid(np.array([0.0]))
        assert abs(result[0] - 0.5) < 1e-9

    def test_large_positive(self):
        result = _sigmoid(np.array([100.0]))
        assert abs(result[0] - 1.0) < 1e-6

    def test_large_negative(self):
        result = _sigmoid(np.array([-100.0]))
        assert abs(result[0]) < 1e-6
