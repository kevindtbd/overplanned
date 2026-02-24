"""
Tests for Phase 6.4 -- DLRM Cross-Feature Scoring Head

Covers: interaction computation, trust gate, fallback behavior,
score ordering, train/save/load, register_model SQL.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import numpy as np
import pytest

from services.api.models.dlrm_scoring import (
    CANDIDATE_FEATURE_KEYS,
    DLRMConfig,
    DLRMScoringHead,
    _forward_mlp,
    _init_mlp_weights,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config():
    return DLRMConfig(n_features=6, embedding_dim=8)


@pytest.fixture
def model(config):
    return DLRMScoringHead(config)


@pytest.fixture
def sasrec_embedding():
    """Fake 8-dim SASRec output."""
    rng = np.random.default_rng(99)
    return rng.normal(0, 1, (8,)).astype(np.float32)


def _make_candidate(
    cid: str = "cand-1",
    impression_count: int = 20,
    **overrides,
) -> dict:
    base = {
        "id": cid,
        "behavioral_quality_score": 0.7,
        "impression_count": impression_count,
        "acceptance_count": 5,
        "tourist_score": 0.3,
        "tourist_local_divergence": 0.15,
        "vibe_match_score": 0.8,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestDLRMConfig:
    def test_defaults(self):
        cfg = DLRMConfig(n_features=6)
        assert cfg.embedding_dim == 16
        assert cfg.top_mlp_dims == [64, 32, 1]
        assert cfg.bottom_mlp_dims == [64, 32]
        assert cfg.trust_gate_threshold == 10

    def test_to_dict_roundtrip(self):
        cfg = DLRMConfig(n_features=4, embedding_dim=8)
        d = cfg.to_dict()
        cfg2 = DLRMConfig(**d)
        assert cfg2.n_features == 4
        assert cfg2.embedding_dim == 8


# ---------------------------------------------------------------------------
# MLP helpers
# ---------------------------------------------------------------------------

class TestMLPHelpers:
    def test_init_weights_shapes(self):
        layers = _init_mlp_weights([10, 8, 4])
        assert len(layers) == 2
        assert layers[0][0].shape == (10, 8)
        assert layers[0][1].shape == (8,)
        assert layers[1][0].shape == (8, 4)

    def test_forward_mlp_output_shape(self):
        layers = _init_mlp_weights([4, 8, 1])
        x = np.ones((1, 4), dtype=np.float32)
        out = _forward_mlp(x, layers, final_sigmoid=True)
        assert out.shape == (1, 1)
        assert 0.0 <= out[0, 0] <= 1.0

    def test_forward_sigmoid_bounds(self):
        layers = _init_mlp_weights([2, 1])
        # Large positive input
        x = np.array([[100.0, 100.0]], dtype=np.float32)
        out = _forward_mlp(x, layers, final_sigmoid=True)
        assert out[0, 0] <= 1.0
        assert out[0, 0] >= 0.0


# ---------------------------------------------------------------------------
# Bottom MLP
# ---------------------------------------------------------------------------

class TestBottomMLP:
    def test_output_shape(self, model):
        features = np.array([0.5, 10.0, 3.0, 0.2, 0.1, 0.8], dtype=np.float32)
        embeddings = model.bottom_mlp(features)
        assert embeddings.shape == (6, 8)  # 6 features, 8-dim embeddings

    def test_different_inputs_different_outputs(self, model):
        f1 = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        f2 = np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0], dtype=np.float32)
        e1 = model.bottom_mlp(f1)
        e2 = model.bottom_mlp(f2)
        assert not np.allclose(e1, e2)


# ---------------------------------------------------------------------------
# Interaction computation
# ---------------------------------------------------------------------------

class TestInteractions:
    def test_interaction_count(self, model):
        embeddings = np.ones((6, 8), dtype=np.float32)
        interactions = model.compute_interactions(embeddings)
        # C(6, 2) = 15
        assert interactions.shape == (15,)

    def test_orthogonal_embeddings_zero_interactions(self, model):
        # 2 orthogonal vectors
        e = np.array([[1, 0, 0, 0, 0, 0, 0, 0],
                       [0, 1, 0, 0, 0, 0, 0, 0]], dtype=np.float32)
        interactions = model.compute_interactions(e)
        assert interactions.shape == (1,)
        assert abs(interactions[0]) < 1e-6

    def test_identical_embeddings_positive_interactions(self, model):
        e = np.ones((3, 8), dtype=np.float32)
        interactions = model.compute_interactions(e)
        # C(3,2) = 3, all should be 8.0 (dot product of ones)
        assert interactions.shape == (3,)
        assert all(abs(v - 8.0) < 1e-5 for v in interactions)


# ---------------------------------------------------------------------------
# Trust gate
# ---------------------------------------------------------------------------

class TestTrustGate:
    def test_passes_with_enough_impressions(self, model):
        c = _make_candidate(impression_count=15)
        assert model._passes_trust_gate(c) is True

    def test_fails_below_threshold(self, model):
        c = _make_candidate(impression_count=5)
        assert model._passes_trust_gate(c) is False

    def test_exact_threshold_passes(self, model):
        c = _make_candidate(impression_count=10)
        assert model._passes_trust_gate(c) is True

    def test_missing_impression_count_fails(self, model):
        c = {"id": "x"}
        assert model._passes_trust_gate(c) is False


# ---------------------------------------------------------------------------
# Score candidates
# ---------------------------------------------------------------------------

class TestScoreCandidates:
    def test_returns_sorted_descending(self, model, sasrec_embedding):
        candidates = [
            _make_candidate("a", impression_count=20, behavioral_quality_score=0.9),
            _make_candidate("b", impression_count=20, behavioral_quality_score=0.1),
        ]
        results = model.score_candidates(sasrec_embedding, candidates)
        assert len(results) == 2
        assert results[0][1] >= results[1][1]

    def test_fallback_for_low_impressions(self, model, sasrec_embedding):
        candidates = [
            _make_candidate("trusted", impression_count=50),
            _make_candidate("untrusted", impression_count=2),
        ]
        results = model.score_candidates(sasrec_embedding, candidates)
        assert len(results) == 2
        # Both should have valid scores
        for cid, score in results:
            assert isinstance(score, float)

    def test_empty_candidates(self, model, sasrec_embedding):
        results = model.score_candidates(sasrec_embedding, [])
        assert results == []

    def test_all_below_trust_gate(self, model, sasrec_embedding):
        candidates = [
            _make_candidate("a", impression_count=1),
            _make_candidate("b", impression_count=2),
        ]
        results = model.score_candidates(sasrec_embedding, candidates)
        assert len(results) == 2
        # All fallback scores should be equal (same sasrec embedding)
        assert abs(results[0][1] - results[1][1]) < 1e-6


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

class TestTraining:
    def _make_training_data(self, n: int = 20, emb_dim: int = 8):
        rng = np.random.default_rng(42)
        data = []
        for i in range(n):
            data.append({
                "sasrec_embedding": rng.normal(0, 1, (emb_dim,)),
                "candidate_features": {
                    "behavioral_quality_score": rng.random(),
                    "impression_count": int(rng.integers(10, 100)),
                    "acceptance_count": int(rng.integers(0, 20)),
                    "tourist_score": rng.random(),
                    "tourist_local_divergence": rng.random() * 0.5,
                    "vibe_match_score": rng.random(),
                },
                "accepted": bool(i % 2 == 0),
            })
        return data

    def test_train_returns_losses(self, model):
        data = self._make_training_data()
        losses = model.train(data, epochs=3)
        assert len(losses) == 3
        assert all(isinstance(l, float) for l in losses)

    def test_train_marks_trained(self, model):
        assert model._trained is False
        data = self._make_training_data(n=5)
        model.train(data, epochs=1)
        assert model._trained is True

    def test_loss_decreases_over_epochs(self, model):
        data = self._make_training_data(n=30)
        losses = model.train(data, epochs=20)
        # Loss should generally decrease (first > last)
        assert losses[0] > losses[-1]


# ---------------------------------------------------------------------------
# Save / Load
# ---------------------------------------------------------------------------

class TestSaveLoad:
    def test_save_returns_sha256(self, model):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "model.json"
            sha = model.save(path)
            assert len(sha) == 64  # SHA-256 hex

    def test_load_roundtrip(self, model, sasrec_embedding):
        candidates = [_make_candidate("a")]
        scores_before = model.score_candidates(sasrec_embedding, candidates)

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "model.json"
            model.save(path)
            loaded = DLRMScoringHead.load(path)

        scores_after = loaded.score_candidates(sasrec_embedding, candidates)
        assert len(scores_before) == len(scores_after)
        assert abs(scores_before[0][1] - scores_after[0][1]) < 1e-5

    def test_saved_file_is_valid_json(self, model):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "model.json"
            model.save(path)
            data = json.loads(path.read_text())
            assert "config" in data
            assert "bottom_mlp" in data
            assert "top_mlp" in data

    def test_load_preserves_config(self, model):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "model.json"
            model.save(path)
            loaded = DLRMScoringHead.load(path)
            assert loaded.config.n_features == model.config.n_features
            assert loaded.config.embedding_dim == model.config.embedding_dim


# ---------------------------------------------------------------------------
# Register model SQL
# ---------------------------------------------------------------------------

class TestRegisterModel:
    @pytest.mark.asyncio
    async def test_register_calls_execute(self, model):
        pool = AsyncMock()
        pool.execute = AsyncMock(return_value=None)

        row_id = await model.register_model(pool)

        pool.execute.assert_called_once()
        sql = pool.execute.call_args[0][0]
        assert '"ModelRegistry"' in sql
        assert '"modelName"' in sql
        assert '"modelVersion"' in sql
        assert '$4::"ModelStage"' in sql
        assert 'ON CONFLICT ("modelName", "modelVersion") DO NOTHING' in sql

    @pytest.mark.asyncio
    async def test_register_passes_correct_values(self, model):
        pool = AsyncMock()
        pool.execute = AsyncMock(return_value=None)

        await model.register_model(pool)

        args = pool.execute.call_args[0]
        # args[1] = id, args[2] = modelName, args[3] = modelVersion, args[4] = stage
        assert args[2] == "dlrm_scoring_head"
        assert args[3] == model._version
        assert args[4] == "staging"
        assert args[5] == "scoring_head"
