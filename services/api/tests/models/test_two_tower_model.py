"""
Tests for Two-Tower Retrieval Model -- Phase 6.2.

Covers:
  - Embedding dimension correctness
  - Retrieval ranking quality
  - ActivitySearchService protocol compliance
  - Save/load roundtrip
  - Model registration SQL
  - Edge cases (empty candidates, cold start)
"""

import json
import os
import tempfile
import uuid
from abc import ABC
from unittest.mock import AsyncMock

import numpy as np
import pytest

from services.api.models.two_tower_model import (
    TwoTowerModel,
    TwoTowerConfig,
    ActivitySearchService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def small_config():
    return TwoTowerConfig(
        user_feature_dim=8,
        item_feature_dim=8,
        embedding_dim=16,
        learning_rate=0.05,
        reg=0.001,
        n_epochs=30,
        temperature=0.1,
        init_std=0.1,
        seed=42,
    )


@pytest.fixture
def synthetic_data():
    """Synthetic training data: 10 users, 20 items, 50 positive pairs.

    Users 0-4 have features aligned with items 0-9.
    Users 5-9 have features aligned with items 10-19.
    """
    rng = np.random.RandomState(123)

    n_users = 10
    n_items = 20
    feat_dim = 8

    user_features = rng.randn(n_users, feat_dim)
    item_features = rng.randn(n_items, feat_dim)

    # Make user/item features correlated for matching pairs
    for u in range(5):
        user_features[u] = item_features[u] + rng.randn(feat_dim) * 0.1
    for u in range(5, 10):
        user_features[u] = item_features[u + 5] + rng.randn(feat_dim) * 0.1

    # Positive pairs: user -> preferred item
    pairs = []
    for _ in range(50):
        u = rng.randint(0, 10)
        if u < 5:
            i = rng.randint(0, 10)
        else:
            i = rng.randint(10, 20)
        pairs.append([u, i])

    positive_pairs = np.array(pairs, dtype=np.int32)
    item_ids = [f"item-{i}" for i in range(n_items)]

    return user_features, item_features, positive_pairs, item_ids


@pytest.fixture
def trained_model(small_config, synthetic_data):
    user_features, item_features, positive_pairs, item_ids = synthetic_data
    model = TwoTowerModel(config=small_config)
    model.train(user_features, item_features, positive_pairs, item_ids)
    return model, user_features, item_features, item_ids


@pytest.fixture
def mock_pool():
    pool = AsyncMock()
    pool.execute = AsyncMock(return_value=None)
    return pool


# ---------------------------------------------------------------------------
# 1. Embedding dimensions
# ---------------------------------------------------------------------------

class TestTwoTowerDimensions:
    """Verify weight matrix dimensions are correct."""

    def test_weight_dimensions(self, trained_model):
        model, _, _, _ = trained_model
        cfg = model.config
        assert model.W_user.shape == (cfg.embedding_dim, cfg.user_feature_dim)
        assert model.b_user.shape == (cfg.embedding_dim,)
        assert model.W_item.shape == (cfg.embedding_dim, cfg.item_feature_dim)
        assert model.b_item.shape == (cfg.embedding_dim,)

    def test_user_tower_output_dim(self, trained_model):
        model, user_features, _, _ = trained_model
        u_emb = model._user_tower(user_features[:1])
        assert u_emb.shape == (1, model.config.embedding_dim)

    def test_item_tower_output_dim(self, trained_model):
        model, _, item_features, _ = trained_model
        i_emb = model._item_tower(item_features[:1])
        assert i_emb.shape == (1, model.config.embedding_dim)

    def test_user_and_item_towers_same_dim(self, trained_model):
        model, user_features, item_features, _ = trained_model
        u_emb = model._user_tower(user_features[:1])
        i_emb = model._item_tower(item_features[:1])
        assert u_emb.shape[1] == i_emb.shape[1]


# ---------------------------------------------------------------------------
# 2. Training
# ---------------------------------------------------------------------------

class TestTwoTowerTraining:

    def test_training_returns_metrics(self, small_config, synthetic_data):
        user_features, item_features, positive_pairs, item_ids = synthetic_data
        model = TwoTowerModel(config=small_config)
        metrics = model.train(user_features, item_features, positive_pairs, item_ids)

        assert "final_loss" in metrics
        assert metrics["n_users"] == 10
        assert metrics["n_items"] == 20
        assert metrics["n_pairs"] == 50

    def test_loss_decreases(self, small_config, synthetic_data):
        user_features, item_features, positive_pairs, item_ids = synthetic_data
        model = TwoTowerModel(config=small_config)
        metrics = model.train(user_features, item_features, positive_pairs, item_ids)

        history = metrics["loss_history"]
        early = np.mean(history[:5])
        late = np.mean(history[-5:])
        assert late < early, f"Loss did not decrease: early={early:.4f} late={late:.4f}"

    def test_feature_dim_mismatch_raises(self, small_config):
        model = TwoTowerModel(config=small_config)
        wrong_dim = np.random.randn(5, 99)  # wrong dim
        item_features = np.random.randn(10, 8)
        pairs = np.array([[0, 0]], dtype=np.int32)
        with pytest.raises(AssertionError, match="user_features dim"):
            model.train(wrong_dim, item_features, pairs, [f"i-{i}" for i in range(10)])


# ---------------------------------------------------------------------------
# 3. Retrieval ranking
# ---------------------------------------------------------------------------

class TestTwoTowerPrediction:

    def test_predict_returns_ranked_list(self, trained_model):
        model, user_features, _, item_ids = trained_model
        candidates = [
            {"id": item_ids[i], "features": model.item_features_cache[i]}
            for i in range(5)
        ]
        results = model.predict(user_features[0], candidates)
        assert len(results) == 5
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)

    def test_predict_empty_candidates(self, trained_model):
        model, user_features, _, _ = trained_model
        results = model.predict(user_features[0], [])
        assert results == []

    def test_predict_raises_before_training(self):
        model = TwoTowerModel()
        with pytest.raises(RuntimeError, match="not trained"):
            model.predict(np.zeros(8), [{"id": "x", "features": np.zeros(8)}])

    def test_predict_single_candidate(self, trained_model):
        model, user_features, _, item_ids = trained_model
        candidates = [{"id": item_ids[0], "features": model.item_features_cache[0]}]
        results = model.predict(user_features[0], candidates)
        assert len(results) == 1
        assert results[0][0] == item_ids[0]


# ---------------------------------------------------------------------------
# 4. ActivitySearchService protocol
# ---------------------------------------------------------------------------

class TestActivitySearchServiceProtocol:

    def test_two_tower_is_subclass(self):
        assert issubclass(TwoTowerModel, ActivitySearchService)

    def test_two_tower_instance_check(self, trained_model):
        model, _, _, _ = trained_model
        assert isinstance(model, ActivitySearchService)

    def test_search_returns_top_k(self, trained_model):
        model, user_features, _, item_ids = trained_model
        candidates = [
            {"id": item_ids[i], "features": model.item_features_cache[i]}
            for i in range(20)
        ]
        results = model.search(user_features[0], candidates, top_k=5)
        assert len(results) == 5

    def test_search_respects_top_k(self, trained_model):
        model, user_features, _, item_ids = trained_model
        candidates = [
            {"id": item_ids[i], "features": model.item_features_cache[i]}
            for i in range(20)
        ]
        for k in [1, 3, 10, 20]:
            results = model.search(user_features[0], candidates, top_k=k)
            assert len(results) == k

    def test_activity_search_service_is_abc(self):
        assert issubclass(ActivitySearchService, ABC)


# ---------------------------------------------------------------------------
# 5. Save/load roundtrip
# ---------------------------------------------------------------------------

class TestTwoTowerSaveLoad:

    def test_save_creates_file(self, trained_model):
        model, _, _, _ = trained_model
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "two_tower.pkl")
            h = model.save(path)
            assert os.path.exists(path)
            assert len(h) == 64

    def test_save_load_roundtrip(self, trained_model):
        model, user_features, _, item_ids = trained_model
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "two_tower.pkl")
            model.save(path)
            loaded = TwoTowerModel.load(path)

            np.testing.assert_array_almost_equal(loaded.W_user, model.W_user)
            np.testing.assert_array_almost_equal(loaded.W_item, model.W_item)
            np.testing.assert_array_almost_equal(loaded.b_user, model.b_user)
            np.testing.assert_array_almost_equal(loaded.b_item, model.b_item)
            assert loaded.config.embedding_dim == model.config.embedding_dim

    def test_loaded_model_predicts_same(self, trained_model):
        model, user_features, _, item_ids = trained_model
        candidates = [
            {"id": item_ids[i], "features": model.item_features_cache[i]}
            for i in range(10)
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "two_tower.pkl")
            model.save(path)
            loaded = TwoTowerModel.load(path)

            orig = model.predict(user_features[0], candidates)
            rest = loaded.predict(user_features[0], candidates)

            for (oid, os_), (rid, rs_) in zip(orig, rest):
                assert oid == rid
                assert abs(os_ - rs_) < 1e-10


# ---------------------------------------------------------------------------
# 6. Model registration SQL
# ---------------------------------------------------------------------------

class TestTwoTowerRegistration:

    @pytest.mark.asyncio
    async def test_register_model_calls_execute(self, trained_model, mock_pool):
        model, _, _, _ = trained_model
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tt.pkl")
            model.save(path)

            row_id = await model.register_model(
                pool=mock_pool,
                model_name="two-tower-v1",
                version="1.0.0",
                artifact_path=path,
                metrics_dict={"final_loss": 0.3},
            )
            mock_pool.execute.assert_called_once()
            uuid.UUID(row_id)

    @pytest.mark.asyncio
    async def test_register_model_sql_structure(self, trained_model, mock_pool):
        model, _, _, _ = trained_model
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tt.pkl")
            model.save(path)

            await model.register_model(
                pool=mock_pool,
                model_name="two-tower-v1",
                version="1.0.0",
                artifact_path=path,
                metrics_dict={"final_loss": 0.3},
            )

            sql = mock_pool.execute.call_args[0][0]
            assert 'model_registry' in sql
            assert '"modelName"' in sql
            assert '"modelVersion"' in sql
            assert '"ModelStage"' in sql
            assert '"artifactHash"' in sql
            assert '"configSnapshot"' in sql
            assert 'ON CONFLICT ("modelName", "modelVersion") DO NOTHING' in sql

    @pytest.mark.asyncio
    async def test_register_model_config_snapshot(self, trained_model, mock_pool):
        model, _, _, _ = trained_model
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tt.pkl")
            model.save(path)

            await model.register_model(
                pool=mock_pool,
                model_name="two-tower-v1",
                version="1.0.0",
                artifact_path=path,
                metrics_dict={"final_loss": 0.3},
            )

            args = mock_pool.execute.call_args[0]
            config = json.loads(args[9])
            assert "embedding_dim" in config
            assert "temperature" in config
            assert "user_feature_dim" in config
