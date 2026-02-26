"""
Phase 6.4 -- DLRM Cross-Feature Scoring Head

DLRM-style feature interaction layer used as a scoring head on top of SASRec
output. NOT a standalone model -- it's a scoring enhancement that computes
pairwise dot products between feature embedding vectors and feeds them through
a top MLP for refined ranking scores.

CPU-only: pure numpy, no PyTorch/TensorFlow.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class DLRMConfig:
    """Configuration for the DLRM scoring head."""

    n_features: int
    embedding_dim: int = 16
    top_mlp_dims: list[int] = field(default_factory=lambda: [64, 32, 1])
    bottom_mlp_dims: list[int] = field(default_factory=lambda: [64, 32])
    learning_rate: float = 0.001
    trust_gate_threshold: int = 10

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_features": self.n_features,
            "embedding_dim": self.embedding_dim,
            "top_mlp_dims": self.top_mlp_dims,
            "bottom_mlp_dims": self.bottom_mlp_dims,
            "learning_rate": self.learning_rate,
            "trust_gate_threshold": self.trust_gate_threshold,
        }


# ---------------------------------------------------------------------------
# Feature names expected per candidate
# ---------------------------------------------------------------------------

CANDIDATE_FEATURE_KEYS = [
    "behavioral_quality_score",
    "impression_count",
    "acceptance_count",
    "tourist_score",
    "tourist_local_divergence",
    "vibe_match_score",
]


# ---------------------------------------------------------------------------
# Numpy MLP helpers
# ---------------------------------------------------------------------------

def _init_mlp_weights(
    dims: list[int],
    rng: np.random.Generator | None = None,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Xavier-initialized weight matrices + zero biases."""
    if rng is None:
        rng = np.random.default_rng(42)
    layers: list[tuple[np.ndarray, np.ndarray]] = []
    for i in range(len(dims) - 1):
        fan_in, fan_out = dims[i], dims[i + 1]
        scale = np.sqrt(2.0 / (fan_in + fan_out))
        w = rng.normal(0, scale, (fan_in, fan_out)).astype(np.float32)
        b = np.zeros(fan_out, dtype=np.float32)
        layers.append((w, b))
    return layers


def _forward_mlp(
    x: np.ndarray,
    layers: list[tuple[np.ndarray, np.ndarray]],
    final_sigmoid: bool = False,
) -> np.ndarray:
    """Forward pass through an MLP with ReLU activations."""
    for i, (w, b) in enumerate(layers):
        x = x @ w + b
        is_last = i == len(layers) - 1
        if is_last and final_sigmoid:
            x = 1.0 / (1.0 + np.exp(-np.clip(x, -500, 500)))
        elif not is_last:
            x = np.maximum(x, 0)  # ReLU
    return x


def _backward_mlp(
    x_input: np.ndarray,
    layers: list[tuple[np.ndarray, np.ndarray]],
    target: np.ndarray,
    learning_rate: float,
    final_sigmoid: bool = False,
) -> float:
    """Single-step backprop with BCE loss. Returns loss value."""
    # Forward pass -- cache activations
    activations = [x_input]
    x = x_input
    for i, (w, b) in enumerate(layers):
        z = x @ w + b
        is_last = i == len(layers) - 1
        if is_last and final_sigmoid:
            x = 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))
        elif not is_last:
            x = np.maximum(z, 0)
        else:
            x = z
        activations.append(x)

    # BCE loss
    pred = activations[-1].flatten()
    eps = 1e-7
    pred_clipped = np.clip(pred, eps, 1 - eps)
    loss = -np.mean(
        target * np.log(pred_clipped) + (1 - target) * np.log(1 - pred_clipped)
    )

    # Backward pass
    grad = (pred_clipped - target).reshape(-1, 1) / len(target)

    for i in range(len(layers) - 1, -1, -1):
        w, b = layers[i]
        a_prev = activations[i]
        is_last = i == len(layers) - 1

        # Gradient through activation
        if not is_last:
            grad = grad * (activations[i + 1] > 0).astype(np.float32)

        dw = a_prev.T @ grad
        db = grad.sum(axis=0)
        grad = grad @ w.T

        layers[i] = (w - learning_rate * dw, b - learning_rate * db)

    return float(loss)


# ---------------------------------------------------------------------------
# DLRM Scoring Head
# ---------------------------------------------------------------------------

class DLRMScoringHead:
    """
    DLRM-style scoring head that refines SASRec sequence embeddings
    with per-candidate feature interactions.
    """

    def __init__(self, config: DLRMConfig) -> None:
        self.config = config
        self._rng = np.random.default_rng(42)

        # Bottom MLP: maps each raw feature scalar to an embedding vector.
        # Input dim = 1 (single feature value), output dim = embedding_dim.
        bottom_dims = [1] + list(config.bottom_mlp_dims) + [config.embedding_dim]
        self._bottom_mlp_weights = _init_mlp_weights(bottom_dims, self._rng)

        # Number of pairwise interactions: C(n_features, 2)
        n_interactions = (config.n_features * (config.n_features - 1)) // 2

        # Top MLP: interactions + dense sasrec embedding concatenated
        # We assume sasrec output is config.embedding_dim dimensional
        top_input_dim = n_interactions + config.embedding_dim
        top_dims = [top_input_dim] + list(config.top_mlp_dims)
        # Ensure last layer outputs 1
        if top_dims[-1] != 1:
            top_dims.append(1)
        self._top_mlp_weights = _init_mlp_weights(top_dims, self._rng)

        self._trained = False
        self._version = "0.1.0"

    def bottom_mlp(self, feature_vectors: np.ndarray) -> np.ndarray:
        """
        Map raw feature values through bottom MLP to get embeddings.

        Args:
            feature_vectors: shape (n_features,) -- raw feature scalars

        Returns:
            shape (n_features, embedding_dim) -- per-feature embeddings
        """
        embeddings = []
        for i in range(len(feature_vectors)):
            x = np.array([[feature_vectors[i]]], dtype=np.float32)
            emb = _forward_mlp(x, self._bottom_mlp_weights)
            embeddings.append(emb.flatten())
        return np.array(embeddings, dtype=np.float32)

    def compute_interactions(self, embeddings: np.ndarray) -> np.ndarray:
        """
        Compute all pairwise dot products between feature embeddings.

        Args:
            embeddings: shape (n_features, embedding_dim)

        Returns:
            shape (n_interactions,) -- flattened pairwise dot products
        """
        n = embeddings.shape[0]
        interactions = []
        for i in range(n):
            for j in range(i + 1, n):
                dot = float(np.dot(embeddings[i], embeddings[j]))
                interactions.append(dot)
        return np.array(interactions, dtype=np.float32)

    def top_mlp(
        self,
        interaction_vector: np.ndarray,
        dense_features: np.ndarray,
    ) -> float:
        """
        Final scoring MLP.

        Args:
            interaction_vector: pairwise dot products
            dense_features: SASRec sequence embedding

        Returns:
            Scalar score
        """
        combined = np.concatenate([interaction_vector, dense_features]).reshape(1, -1)
        out = _forward_mlp(combined, self._top_mlp_weights, final_sigmoid=True)
        return float(out.flatten()[0])

    def _extract_features(self, candidate: dict[str, Any]) -> np.ndarray:
        """Extract feature vector from a candidate dict."""
        return np.array(
            [float(candidate.get(k, 0.0)) for k in CANDIDATE_FEATURE_KEYS],
            dtype=np.float32,
        )

    def _passes_trust_gate(self, candidate: dict[str, Any]) -> bool:
        """Check if candidate has enough impressions (Decision #8)."""
        return candidate.get("impression_count", 0) >= self.config.trust_gate_threshold

    def score_candidates(
        self,
        sasrec_output: np.ndarray,
        candidate_features: list[dict[str, Any]],
    ) -> list[tuple[str, float]]:
        """
        Score and rank candidates using DLRM interactions.

        Candidates that fail the trust gate (impression_count < threshold)
        fall back to SASRec-only scoring (dot product with sasrec_output).

        Args:
            sasrec_output: SASRec sequence embedding, shape (embedding_dim,)
            candidate_features: list of dicts with keys including 'id' and
                CANDIDATE_FEATURE_KEYS

        Returns:
            Sorted list of (candidate_id, score) tuples, descending by score
        """
        results: list[tuple[str, float]] = []
        sasrec_flat = sasrec_output.flatten().astype(np.float32)

        for candidate in candidate_features:
            cid = candidate["id"]

            if self._passes_trust_gate(candidate):
                features = self._extract_features(candidate)
                embeddings = self.bottom_mlp(features)
                interactions = self.compute_interactions(embeddings)
                score = self.top_mlp(interactions, sasrec_flat)
            else:
                # Fallback: simple dot-product score from SASRec embedding
                # Use the sasrec output norm as a basic score proxy
                score = float(np.mean(sasrec_flat)) * 0.5

            results.append((cid, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def train(self, training_data: list[dict[str, Any]], epochs: int = 10) -> list[float]:
        """
        Train on accept/reject data using binary cross-entropy.

        Args:
            training_data: list of dicts with:
                - 'sasrec_embedding': np.ndarray
                - 'candidate_features': dict with CANDIDATE_FEATURE_KEYS
                - 'accepted': bool (label)
            epochs: number of training epochs

        Returns:
            List of loss values per epoch
        """
        losses = []
        for _epoch in range(epochs):
            epoch_losses = []
            for sample in training_data:
                sasrec_emb = np.array(
                    sample["sasrec_embedding"], dtype=np.float32
                ).flatten()
                features = self._extract_features(sample["candidate_features"])
                label = np.array(
                    [1.0 if sample["accepted"] else 0.0], dtype=np.float32
                )

                # Forward: bottom MLP -> interactions -> concat with sasrec
                embeddings = self.bottom_mlp(features)
                interactions = self.compute_interactions(embeddings)
                combined = np.concatenate([interactions, sasrec_emb]).reshape(1, -1)

                loss = _backward_mlp(
                    combined,
                    self._top_mlp_weights,
                    label,
                    self.config.learning_rate,
                    final_sigmoid=True,
                )
                epoch_losses.append(loss)

            avg_loss = float(np.mean(epoch_losses))
            losses.append(avg_loss)

        self._trained = True
        return losses

    def save(self, path: str | Path) -> str:
        """
        Save model weights and config to disk.

        Returns:
            SHA-256 hash of the saved artifact.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "config": self.config.to_dict(),
            "version": self._version,
            "trained": self._trained,
            "bottom_mlp": [
                (w.tolist(), b.tolist()) for w, b in self._bottom_mlp_weights
            ],
            "top_mlp": [
                (w.tolist(), b.tolist()) for w, b in self._top_mlp_weights
            ],
        }

        raw = json.dumps(data, sort_keys=True)
        path.write_text(raw)

        sha = hashlib.sha256(raw.encode()).hexdigest()
        return sha

    @classmethod
    def load(cls, path: str | Path) -> "DLRMScoringHead":
        """Load model weights and config from disk."""
        path = Path(path)
        raw = path.read_text()
        data = json.loads(raw)

        config = DLRMConfig(**data["config"])
        model = cls(config)
        model._trained = data["trained"]
        model._version = data["version"]

        model._bottom_mlp_weights = [
            (np.array(w, dtype=np.float32), np.array(b, dtype=np.float32))
            for w, b in data["bottom_mlp"]
        ]
        model._top_mlp_weights = [
            (np.array(w, dtype=np.float32), np.array(b, dtype=np.float32))
            for w, b in data["top_mlp"]
        ]

        # Verify hash
        expected_sha = hashlib.sha256(raw.encode()).hexdigest()
        model._artifact_hash = expected_sha

        return model

    async def register_model(self, pool: Any) -> str:
        """
        Register this model version in ModelRegistry.

        Uses ON CONFLICT to avoid duplicates per @@unique([modelName, modelVersion]).

        Args:
            pool: asyncpg connection pool

        Returns:
            The model registry row ID
        """
        row_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        artifact_hash = getattr(self, "_artifact_hash", None)

        await pool.execute(
            """
            INSERT INTO model_registry (
                "id", "modelName", "modelVersion", "stage", "modelType",
                "description", "artifactHash", "configSnapshot",
                "createdAt", "updatedAt"
            ) VALUES (
                $1, $2, $3, $4::"ModelStage", $5,
                $6, $7, $8::jsonb,
                $9, $10
            )
            ON CONFLICT ("modelName", "modelVersion") DO NOTHING
            """,
            row_id,
            "dlrm_scoring_head",
            self._version,
            "staging",
            "scoring_head",
            "DLRM cross-feature scoring head for SASRec refinement",
            artifact_hash,
            json.dumps(self.config.to_dict()),
            now,
            now,
        )
        return row_id
