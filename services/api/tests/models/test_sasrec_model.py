"""
Tests for SASRec (Self-Attentive Sequential Recommendation) -- Phase 6.3.

Covers:
  - Attention masking (causal)
  - Sequence prediction correctness
  - Re-ranking from Two-Tower output
  - Positional embeddings
  - Save/load roundtrip
  - Model registration SQL
  - Edge cases (empty sequence, single item, unknown items, cold start)
"""

import json
import os
import tempfile
import uuid
from unittest.mock import AsyncMock

import numpy as np
import pytest

from services.api.models.sasrec_model import (
    SASRecModel,
    SASRecConfig,
    _layer_norm,
    _softmax,
    _gelu,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def small_config():
    return SASRecConfig(
        max_seq_len=10,
        embedding_dim=16,
        n_heads=2,
        n_layers=1,
        learning_rate=0.01,
        reg=0.0001,
        n_epochs=15,
        init_std=0.1,
        seed=42,
    )


@pytest.fixture
def item_ids():
    return [f"item-{i}" for i in range(20)]


@pytest.fixture
def synthetic_sequences(item_ids):
    """Synthetic user sequences with sequential patterns.

    Pattern: items in order (0->1->2->3) or (10->11->12->13).
    """
    rng = np.random.RandomState(123)
    sequences = []
    for _ in range(30):
        if rng.random() < 0.5:
            start = rng.randint(0, 7)
            seq = [item_ids[start + i] for i in range(rng.randint(3, 6))]
        else:
            start = rng.randint(10, 17)
            seq = [item_ids[min(start + i, 19)] for i in range(rng.randint(3, 6))]
        sequences.append(seq)
    return sequences


@pytest.fixture
def trained_model(small_config, synthetic_sequences, item_ids):
    model = SASRecModel(config=small_config)
    model.train(synthetic_sequences, item_ids)
    return model


@pytest.fixture
def mock_pool():
    pool = AsyncMock()
    pool.execute = AsyncMock(return_value=None)
    return pool


# ---------------------------------------------------------------------------
# 1. Attention masking
# ---------------------------------------------------------------------------

class TestCausalMasking:

    def test_causal_mask_shape(self, small_config):
        model = SASRecModel(config=small_config)
        mask = model._causal_mask(5)
        assert mask.shape == (5, 5)

    def test_causal_mask_lower_triangular(self, small_config):
        model = SASRecModel(config=small_config)
        mask = model._causal_mask(5)
        # Upper triangle (excluding diagonal) should be 0
        for i in range(5):
            for j in range(5):
                if j > i:
                    assert mask[i, j] == 0.0
                else:
                    assert mask[i, j] == 1.0

    def test_causal_mask_diagonal_is_one(self, small_config):
        model = SASRecModel(config=small_config)
        mask = model._causal_mask(8)
        for i in range(8):
            assert mask[i, i] == 1.0

    def test_causal_mask_first_position(self, small_config):
        """First position can only attend to itself."""
        model = SASRecModel(config=small_config)
        mask = model._causal_mask(5)
        assert mask[0, 0] == 1.0
        assert np.sum(mask[0]) == 1.0

    def test_causal_mask_last_position(self, small_config):
        """Last position can attend to all positions."""
        model = SASRecModel(config=small_config)
        n = 5
        mask = model._causal_mask(n)
        assert np.sum(mask[n - 1]) == n


# ---------------------------------------------------------------------------
# 2. Sequence prediction
# ---------------------------------------------------------------------------

class TestSequencePrediction:

    def test_predict_returns_ranked_list(self, trained_model, item_ids):
        sequence = item_ids[:3]
        candidates = item_ids[3:8]
        results = trained_model.predict(sequence, candidates)
        assert len(results) == 5
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)

    def test_predict_all_candidates(self, trained_model, item_ids):
        sequence = item_ids[:5]
        results = trained_model.predict(sequence, item_ids)
        assert len(results) == 20

    def test_predict_empty_sequence_returns_zeros(self, trained_model, item_ids):
        results = trained_model.predict([], item_ids[:5])
        assert len(results) == 5
        for _, score in results:
            assert score == 0.0

    def test_predict_empty_candidates(self, trained_model, item_ids):
        results = trained_model.predict(item_ids[:3], [])
        assert results == []

    def test_predict_unknown_items_get_zero(self, trained_model, item_ids):
        sequence = item_ids[:3]
        candidates = ["unknown-a", "unknown-b"]
        results = trained_model.predict(sequence, candidates)
        assert len(results) == 2
        for _, score in results:
            assert score == 0.0

    def test_predict_raises_before_training(self):
        model = SASRecModel()
        with pytest.raises(RuntimeError, match="not trained"):
            model.predict(["item-0"], ["item-1"])


# ---------------------------------------------------------------------------
# 3. Re-ranking
# ---------------------------------------------------------------------------

class TestReranking:

    def test_rerank_changes_order(self, trained_model, item_ids):
        """SASRec should potentially reorder candidates compared to input order."""
        sequence = item_ids[:5]
        candidates = item_ids[5:15]
        results = trained_model.predict(sequence, candidates)
        result_ids = [r[0] for r in results]
        # At least verify it returns all candidates
        assert set(result_ids) == set(candidates)

    def test_different_sequences_give_different_rankings(self, trained_model, item_ids):
        """Different user histories should produce different rankings."""
        candidates = item_ids[5:15]
        results_a = trained_model.predict(item_ids[:3], candidates)
        results_b = trained_model.predict(item_ids[10:13], candidates)

        scores_a = [s for _, s in results_a]
        scores_b = [s for _, s in results_b]
        # Scores should differ (not identical rankings)
        assert scores_a != scores_b


# ---------------------------------------------------------------------------
# 4. Positional embeddings
# ---------------------------------------------------------------------------

class TestPositionalEmbeddings:

    def test_position_embeddings_shape(self, trained_model):
        assert trained_model.position_embeddings.shape == (
            trained_model.config.max_seq_len,
            trained_model.config.embedding_dim,
        )

    def test_position_embeddings_different(self, trained_model):
        """Each position should have a unique embedding."""
        pe = trained_model.position_embeddings
        for i in range(pe.shape[0] - 1):
            assert not np.allclose(pe[i], pe[i + 1]), f"Positions {i} and {i+1} are identical"

    def test_item_embeddings_shape(self, trained_model, item_ids):
        # n_items + 1 for padding at index 0
        assert trained_model.item_embeddings.shape == (
            len(item_ids) + 1,
            trained_model.config.embedding_dim,
        )

    def test_padding_embedding_is_zero(self, trained_model):
        """Index 0 (padding) should be zeros."""
        np.testing.assert_array_equal(
            trained_model.item_embeddings[0],
            np.zeros(trained_model.config.embedding_dim),
        )


# ---------------------------------------------------------------------------
# 5. Utility functions
# ---------------------------------------------------------------------------

class TestUtilityFunctions:

    def test_layer_norm_output_shape(self):
        x = np.random.randn(5, 16)
        gamma = np.ones(16)
        beta = np.zeros(16)
        result = _layer_norm(x, gamma, beta)
        assert result.shape == x.shape

    def test_layer_norm_zero_mean(self):
        x = np.random.randn(3, 16)
        gamma = np.ones(16)
        beta = np.zeros(16)
        result = _layer_norm(x, gamma, beta)
        means = np.mean(result, axis=-1)
        np.testing.assert_array_almost_equal(means, 0.0, decimal=5)

    def test_softmax_sums_to_one(self):
        x = np.random.randn(4, 10)
        result = _softmax(x)
        sums = np.sum(result, axis=-1)
        np.testing.assert_array_almost_equal(sums, 1.0)

    def test_softmax_non_negative(self):
        x = np.random.randn(3, 8)
        result = _softmax(x)
        assert np.all(result >= 0)

    def test_gelu_at_zero(self):
        result = _gelu(np.array([0.0]))
        assert abs(result[0]) < 1e-6


# ---------------------------------------------------------------------------
# 6. Training
# ---------------------------------------------------------------------------

class TestSASRecTraining:

    def test_training_returns_metrics(self, small_config, synthetic_sequences, item_ids):
        model = SASRecModel(config=small_config)
        metrics = model.train(synthetic_sequences, item_ids)

        assert "final_loss" in metrics
        assert "n_epochs" in metrics
        assert metrics["n_items"] == 20
        assert metrics["embedding_dim"] == 16
        assert metrics["n_heads"] == 2

    def test_loss_decreases(self, small_config, synthetic_sequences, item_ids):
        model = SASRecModel(config=small_config)
        metrics = model.train(synthetic_sequences, item_ids)

        history = metrics["loss_history"]
        early = np.mean(history[:3])
        late = np.mean(history[-3:])
        assert late < early, f"Loss did not decrease: early={early:.4f} late={late:.4f}"

    def test_empty_sequences_skip(self, small_config, item_ids):
        """Sequences shorter than 2 items should be skipped."""
        model = SASRecModel(config=small_config)
        short_seqs = [["item-0"], [], ["item-1"]]
        metrics = model.train(short_seqs, item_ids)
        assert metrics["n_sequences"] == 0

    def test_id_maps_populated(self, trained_model, item_ids):
        assert len(trained_model.item_id_map) == 20
        for iid in item_ids:
            assert iid in trained_model.item_id_map
            idx = trained_model.item_id_map[iid]
            assert idx >= 1  # 0 is padding
            assert trained_model.reverse_item_map[idx] == iid


# ---------------------------------------------------------------------------
# 7. Save/load roundtrip
# ---------------------------------------------------------------------------

class TestSASRecSaveLoad:

    def test_save_creates_file(self, trained_model):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sasrec.pkl")
            h = trained_model.save(path)
            assert os.path.exists(path)
            assert len(h) == 64

    def test_save_load_roundtrip(self, trained_model, item_ids):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sasrec.pkl")
            trained_model.save(path)
            loaded = SASRecModel.load(path)

            assert loaded.config.embedding_dim == trained_model.config.embedding_dim
            assert loaded.config.n_heads == trained_model.config.n_heads
            assert len(loaded.item_id_map) == len(trained_model.item_id_map)
            np.testing.assert_array_almost_equal(
                loaded.item_embeddings, trained_model.item_embeddings
            )
            np.testing.assert_array_almost_equal(
                loaded.position_embeddings, trained_model.position_embeddings
            )

    def test_loaded_model_predicts_same(self, trained_model, item_ids):
        sequence = item_ids[:5]
        candidates = item_ids[5:15]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sasrec.pkl")
            trained_model.save(path)
            loaded = SASRecModel.load(path)

            orig = trained_model.predict(sequence, candidates)
            rest = loaded.predict(sequence, candidates)

            for (oid, os_), (rid, rs_) in zip(orig, rest):
                assert oid == rid
                assert abs(os_ - rs_) < 1e-10

    def test_attention_layers_preserved(self, trained_model):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sasrec.pkl")
            trained_model.save(path)
            loaded = SASRecModel.load(path)

            assert len(loaded.attention_layers) == len(trained_model.attention_layers)
            for orig_layer, load_layer in zip(
                trained_model.attention_layers, loaded.attention_layers
            ):
                for key in orig_layer:
                    np.testing.assert_array_almost_equal(
                        orig_layer[key], load_layer[key]
                    )


# ---------------------------------------------------------------------------
# 8. Model registration SQL
# ---------------------------------------------------------------------------

class TestSASRecRegistration:

    @pytest.mark.asyncio
    async def test_register_model_calls_execute(self, trained_model, mock_pool):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sasrec.pkl")
            trained_model.save(path)

            row_id = await trained_model.register_model(
                pool=mock_pool,
                model_name="sasrec-v1",
                version="1.0.0",
                artifact_path=path,
                metrics_dict={"final_loss": 2.1},
            )
            mock_pool.execute.assert_called_once()
            uuid.UUID(row_id)

    @pytest.mark.asyncio
    async def test_register_model_sql_structure(self, trained_model, mock_pool):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sasrec.pkl")
            trained_model.save(path)

            await trained_model.register_model(
                pool=mock_pool,
                model_name="sasrec-v1",
                version="1.0.0",
                artifact_path=path,
                metrics_dict={"final_loss": 2.1},
            )

            sql = mock_pool.execute.call_args[0][0]
            assert 'model_registry' in sql
            assert '"modelName"' in sql
            assert '"modelVersion"' in sql
            assert '"ModelStage"' in sql
            assert '"configSnapshot"' in sql
            assert '"artifactHash"' in sql
            assert 'ON CONFLICT ("modelName", "modelVersion") DO NOTHING' in sql

    @pytest.mark.asyncio
    async def test_register_model_config_snapshot(self, trained_model, mock_pool):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sasrec.pkl")
            trained_model.save(path)

            await trained_model.register_model(
                pool=mock_pool,
                model_name="sasrec-v1",
                version="1.0.0",
                artifact_path=path,
                metrics_dict={"final_loss": 2.1},
            )

            args = mock_pool.execute.call_args[0]
            config = json.loads(args[9])
            assert "embedding_dim" in config
            assert "n_heads" in config
            assert "n_layers" in config
            assert "max_seq_len" in config

    @pytest.mark.asyncio
    async def test_register_model_passes_stage(self, trained_model, mock_pool):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sasrec.pkl")
            trained_model.save(path)

            await trained_model.register_model(
                pool=mock_pool,
                model_name="sasrec-v1",
                version="1.0.0",
                artifact_path=path,
                metrics_dict={"final_loss": 2.1},
                stage="ab_test",
            )

            args = mock_pool.execute.call_args[0]
            assert args[4] == "ab_test"


# ---------------------------------------------------------------------------
# 9. Forward pass internals
# ---------------------------------------------------------------------------

class TestForwardPass:

    def test_forward_output_shape(self, trained_model, item_ids):
        indices = np.array([
            trained_model.item_id_map[item_ids[i]] for i in range(5)
        ], dtype=np.int32)
        output = trained_model._forward(indices)
        assert output.shape == (5, trained_model.config.embedding_dim)

    def test_forward_with_padding(self, trained_model, item_ids):
        """Padding positions (index 0) should produce zero output."""
        indices = np.array([0, 0, trained_model.item_id_map[item_ids[0]]], dtype=np.int32)
        output = trained_model._forward(indices)
        # Padding positions should be zeroed
        np.testing.assert_array_almost_equal(output[0], 0.0)
        np.testing.assert_array_almost_equal(output[1], 0.0)

    def test_forward_truncates_long_sequence(self, trained_model, item_ids):
        """Sequences longer than max_seq_len get truncated to most recent."""
        # Create sequence longer than max_seq_len (10)
        long_indices = np.array([
            trained_model.item_id_map[item_ids[i % 20]] for i in range(15)
        ], dtype=np.int32)
        output = trained_model._forward(long_indices)
        assert output.shape == (trained_model.config.max_seq_len, trained_model.config.embedding_dim)
