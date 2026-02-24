"""
Tests for BPR (Bayesian Personalized Ranking) model -- Phase 6.1.

Covers:
  - Training convergence on synthetic data
  - Prediction correctness and ranking
  - Save/load roundtrip via pickle
  - Model registration SQL (mocked DB pool)
  - Edge cases (empty input, single item, unknown user, cold start)
"""

import json
import os
import tempfile
import uuid
from unittest.mock import AsyncMock, MagicMock, call

import numpy as np
import pytest

from services.api.models.bpr_model import BPRModel, BPRConfig, _sigmoid


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def small_config():
    """Small BPR config for fast tests."""
    return BPRConfig(
        n_factors=8,
        learning_rate=0.05,
        reg=0.001,
        n_epochs=20,
        init_std=0.1,
        seed=42,
    )


@pytest.fixture
def synthetic_data():
    """Synthetic BPR triplets: 5 users, 10 items, 100 triplets.

    Users 0-2 prefer items 0-4. Users 3-4 prefer items 5-9.
    """
    rng = np.random.RandomState(123)
    user_ids = [f"user-{i}" for i in range(5)]
    item_ids = [f"item-{i}" for i in range(10)]

    triplets = []
    for _ in range(100):
        u = rng.randint(0, 5)
        if u < 3:
            pos = rng.randint(0, 5)
            neg = rng.randint(5, 10)
        else:
            pos = rng.randint(5, 10)
            neg = rng.randint(0, 5)
        triplets.append([u, pos, neg])

    return np.array(triplets, dtype=np.int32), user_ids, item_ids


@pytest.fixture
def trained_model(small_config, synthetic_data):
    """Pre-trained BPR model on synthetic data."""
    triplets, user_ids, item_ids = synthetic_data
    model = BPRModel(config=small_config)
    model.train(triplets, user_ids, item_ids)
    return model, user_ids, item_ids


@pytest.fixture
def mock_pool():
    """Mock asyncpg pool for register_model tests."""
    pool = AsyncMock()
    pool.execute = AsyncMock(return_value=None)
    return pool


# ---------------------------------------------------------------------------
# 1. Training convergence
# ---------------------------------------------------------------------------

class TestBPRTraining:
    """BPR training convergence and metric correctness."""

    def test_training_returns_metrics(self, small_config, synthetic_data):
        triplets, user_ids, item_ids = synthetic_data
        model = BPRModel(config=small_config)
        metrics = model.train(triplets, user_ids, item_ids)

        assert "final_loss" in metrics
        assert "n_epochs" in metrics
        assert "n_triplets" in metrics
        assert metrics["n_epochs"] == 20
        assert metrics["n_triplets"] == 100
        assert metrics["n_users"] == 5
        assert metrics["n_items"] == 10

    def test_loss_decreases_over_training(self, small_config, synthetic_data):
        """Loss should decrease from early to late epochs."""
        triplets, user_ids, item_ids = synthetic_data
        model = BPRModel(config=small_config)
        metrics = model.train(triplets, user_ids, item_ids)

        history = metrics["loss_history"]
        # First 3 epochs avg should be higher than last 3
        early_avg = np.mean(history[:3])
        late_avg = np.mean(history[-3:])
        assert late_avg < early_avg, f"Loss did not decrease: early={early_avg:.4f} late={late_avg:.4f}"

    def test_factors_initialized_correctly(self, small_config, synthetic_data):
        triplets, user_ids, item_ids = synthetic_data
        model = BPRModel(config=small_config)
        model.train(triplets, user_ids, item_ids)

        assert model.user_factors is not None
        assert model.item_factors is not None
        assert model.user_factors.shape == (5, 8)
        assert model.item_factors.shape == (10, 8)

    def test_id_maps_populated(self, small_config, synthetic_data):
        triplets, user_ids, item_ids = synthetic_data
        model = BPRModel(config=small_config)
        model.train(triplets, user_ids, item_ids)

        assert len(model.user_id_map) == 5
        assert len(model.item_id_map) == 10
        assert len(model.reverse_item_map) == 10
        for uid in user_ids:
            assert uid in model.user_id_map
        for iid in item_ids:
            assert iid in model.item_id_map

    def test_single_epoch_training(self, synthetic_data):
        triplets, user_ids, item_ids = synthetic_data
        config = BPRConfig(n_factors=4, n_epochs=1, seed=42)
        model = BPRModel(config=config)
        metrics = model.train(triplets, user_ids, item_ids)

        assert metrics["n_epochs"] == 1
        assert len(metrics["loss_history"]) == 1


# ---------------------------------------------------------------------------
# 2. Prediction correctness
# ---------------------------------------------------------------------------

class TestBPRPrediction:
    """BPR prediction scoring and ranking."""

    def test_predict_returns_ranked_list(self, trained_model):
        model, user_ids, item_ids = trained_model
        results = model.predict(user_ids[0], item_ids)

        assert len(results) == 10
        # Sorted descending
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)

    def test_predict_user_preferences(self, trained_model):
        """Users 0-2 should prefer items 0-4 over items 5-9."""
        model, user_ids, item_ids = trained_model
        results = model.predict(user_ids[0], item_ids)

        # Top 5 should mostly be items 0-4
        top_5_ids = {iid for iid, _ in results[:5]}
        preferred = {f"item-{i}" for i in range(5)}
        overlap = len(top_5_ids & preferred)
        assert overlap >= 3, f"Expected >= 3 preferred items in top 5, got {overlap}"

    def test_predict_subset_of_items(self, trained_model):
        model, user_ids, item_ids = trained_model
        subset = item_ids[:3]
        results = model.predict(user_ids[0], subset)
        assert len(results) == 3

    def test_predict_unknown_user_returns_zeros(self, trained_model):
        model, _, item_ids = trained_model
        results = model.predict("unknown-user-xyz", item_ids)
        assert len(results) == len(item_ids)
        for _, score in results:
            assert score == 0.0

    def test_predict_unknown_item_gets_zero_score(self, trained_model):
        model, user_ids, _ = trained_model
        results = model.predict(user_ids[0], ["unknown-item-abc"])
        assert len(results) == 1
        assert results[0][1] == 0.0

    def test_predict_empty_items_returns_empty(self, trained_model):
        model, user_ids, _ = trained_model
        results = model.predict(user_ids[0], [])
        assert results == []

    def test_predict_raises_before_training(self):
        model = BPRModel()
        with pytest.raises(RuntimeError, match="not trained"):
            model.predict("user-1", ["item-1"])


# ---------------------------------------------------------------------------
# 3. Save/load roundtrip
# ---------------------------------------------------------------------------

class TestBPRSaveLoad:
    """Pickle serialization roundtrip."""

    def test_save_creates_file(self, trained_model):
        model, _, _ = trained_model
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "bpr.pkl")
            artifact_hash = model.save(path)
            assert os.path.exists(path)
            assert len(artifact_hash) == 64  # SHA-256 hex

    def test_save_load_roundtrip(self, trained_model):
        model, user_ids, item_ids = trained_model
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "bpr.pkl")
            model.save(path)

            loaded = BPRModel.load(path)

            assert loaded.config.n_factors == model.config.n_factors
            assert loaded.config.learning_rate == model.config.learning_rate
            assert len(loaded.user_id_map) == len(model.user_id_map)
            assert len(loaded.item_id_map) == len(model.item_id_map)
            np.testing.assert_array_almost_equal(loaded.user_factors, model.user_factors)
            np.testing.assert_array_almost_equal(loaded.item_factors, model.item_factors)

    def test_loaded_model_predicts_same(self, trained_model):
        model, user_ids, item_ids = trained_model
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "bpr.pkl")
            model.save(path)
            loaded = BPRModel.load(path)

            original = model.predict(user_ids[0], item_ids)
            restored = loaded.predict(user_ids[0], item_ids)

            assert len(original) == len(restored)
            for (oid, oscore), (rid, rscore) in zip(original, restored):
                assert oid == rid
                assert abs(oscore - rscore) < 1e-10

    def test_save_creates_subdirectories(self, trained_model):
        model, _, _ = trained_model
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sub", "dir", "bpr.pkl")
            model.save(path)
            assert os.path.exists(path)


# ---------------------------------------------------------------------------
# 4. Model registration SQL
# ---------------------------------------------------------------------------

class TestBPRRegistration:
    """ModelRegistry SQL via mocked asyncpg pool."""

    @pytest.mark.asyncio
    async def test_register_model_calls_execute(self, trained_model, mock_pool):
        model, _, _ = trained_model
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "bpr.pkl")
            model.save(path)

            row_id = await model.register_model(
                pool=mock_pool,
                model_name="bpr-v1",
                version="1.0.0",
                artifact_path=path,
                metrics_dict={"final_loss": 0.5, "auc": 0.82},
            )

            mock_pool.execute.assert_called_once()
            assert isinstance(row_id, str)
            # Validate UUID format
            uuid.UUID(row_id)

    @pytest.mark.asyncio
    async def test_register_model_sql_uses_correct_table(self, trained_model, mock_pool):
        model, _, _ = trained_model
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "bpr.pkl")
            model.save(path)

            await model.register_model(
                pool=mock_pool,
                model_name="bpr-v1",
                version="1.0.0",
                artifact_path=path,
                metrics_dict={"final_loss": 0.5},
            )

            sql = mock_pool.execute.call_args[0][0]
            assert '"ModelRegistry"' in sql
            assert '"modelName"' in sql
            assert '"modelVersion"' in sql
            assert '"configSnapshot"' in sql
            assert '"artifactHash"' in sql
            assert '"ModelStage"' in sql

    @pytest.mark.asyncio
    async def test_register_model_passes_correct_args(self, trained_model, mock_pool):
        model, _, _ = trained_model
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "bpr.pkl")
            model.save(path)

            await model.register_model(
                pool=mock_pool,
                model_name="bpr-v1",
                version="2.0.0",
                artifact_path=path,
                metrics_dict={"final_loss": 0.3},
                stage="ab_test",
                model_type="bpr",
            )

            args = mock_pool.execute.call_args[0]
            # args[0] = SQL, args[1] = id, args[2] = modelName, etc.
            assert args[2] == "bpr-v1"
            assert args[3] == "2.0.0"
            assert args[4] == "ab_test"
            assert args[5] == "bpr"

    @pytest.mark.asyncio
    async def test_register_model_config_snapshot_is_json(self, trained_model, mock_pool):
        model, _, _ = trained_model
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "bpr.pkl")
            model.save(path)

            await model.register_model(
                pool=mock_pool,
                model_name="bpr-v1",
                version="1.0.0",
                artifact_path=path,
                metrics_dict={"final_loss": 0.5},
            )

            args = mock_pool.execute.call_args[0]
            config_json = json.loads(args[9])  # configSnapshot
            assert "n_factors" in config_json
            assert "learning_rate" in config_json

            metrics_json = json.loads(args[10])  # metrics
            assert "final_loss" in metrics_json


# ---------------------------------------------------------------------------
# 5. Edge cases
# ---------------------------------------------------------------------------

class TestBPREdgeCases:
    """Edge cases and boundary conditions."""

    def test_single_triplet(self):
        config = BPRConfig(n_factors=4, n_epochs=5, seed=42)
        model = BPRModel(config=config)
        triplets = np.array([[0, 0, 1]], dtype=np.int32)
        metrics = model.train(triplets, ["u0"], ["i0", "i1"])
        assert metrics["n_triplets"] == 1
        assert model.user_factors.shape == (1, 4)

    def test_sigmoid_stability(self):
        """Sigmoid should not overflow for extreme values."""
        x = np.array([-1000, -100, 0, 100, 1000])
        result = _sigmoid(x)
        assert not np.any(np.isnan(result))
        assert not np.any(np.isinf(result))
        assert result[0] < 0.01
        assert abs(result[2] - 0.5) < 1e-6
        assert result[4] > 0.99

    def test_many_items_few_users(self):
        config = BPRConfig(n_factors=4, n_epochs=3, seed=42)
        model = BPRModel(config=config)
        rng = np.random.RandomState(42)
        n_items = 100
        triplets = np.column_stack([
            np.zeros(50, dtype=np.int32),
            rng.randint(0, n_items, 50),
            rng.randint(0, n_items, 50),
        ])
        user_ids = ["user-0"]
        item_ids = [f"item-{i}" for i in range(n_items)]
        metrics = model.train(triplets, user_ids, item_ids)
        assert metrics["n_items"] == 100
        assert metrics["n_users"] == 1

    def test_predict_mixed_known_unknown_items(self, trained_model):
        model, user_ids, _ = trained_model
        items = ["item-0", "unknown-1", "item-5", "unknown-2"]
        results = model.predict(user_ids[0], items)
        assert len(results) == 4
        result_dict = dict(results)
        assert result_dict["unknown-1"] == 0.0
        assert result_dict["unknown-2"] == 0.0
        # Known items should have non-zero scores (very likely after training)
        assert result_dict["item-0"] != 0.0 or result_dict["item-5"] != 0.0
