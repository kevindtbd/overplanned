"""
Two-Tower Retrieval Model -- Phase 6.2.

CPU-only two-tower architecture for candidate retrieval.
Replaces Qdrant cosine-similarity for personalized activity retrieval.

Architecture:
  - User tower:  user_embedding  = ReLU(W_user @ user_features + b_user)
  - Item tower:  item_embedding  = ReLU(W_item @ item_features + b_item)
  - Scoring: dot product similarity between user and item embeddings
  - Training: contrastive loss with in-batch negatives

No PyTorch, no TensorFlow, no GPU. Pure numpy.
"""

import hashlib
import json
import logging
import os
import pickle
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

import numpy as np

logger = logging.getLogger(__name__)


class ActivitySearchService(ABC):
    """Protocol/ABC for activity retrieval services.

    Two-Tower implements this to replace Qdrant cosine similarity.
    Any retrieval backend can implement this interface.
    """

    @abstractmethod
    def search(
        self,
        user_features: np.ndarray,
        candidate_items: list[dict[str, Any]],
        top_k: int = 20,
    ) -> list[tuple[str, float]]:
        """Retrieve and rank candidate activities for a user.

        Args:
            user_features: Feature vector for the user.
            candidate_items: List of dicts with 'id' and 'features' keys.
            top_k: Number of results to return.

        Returns:
            List of (item_id, score) tuples sorted descending by score.
        """
        ...


def _relu(x: np.ndarray) -> np.ndarray:
    """ReLU activation."""
    return np.maximum(0, x)


def _relu_grad(x: np.ndarray) -> np.ndarray:
    """Gradient of ReLU."""
    return (x > 0).astype(np.float64)


def _softmax(x: np.ndarray) -> np.ndarray:
    """Numerically stable softmax over last axis."""
    shifted = x - np.max(x, axis=-1, keepdims=True)
    exp_x = np.exp(shifted)
    return exp_x / np.sum(exp_x, axis=-1, keepdims=True)


@dataclass
class TwoTowerConfig:
    """Hyperparameters for Two-Tower training."""

    user_feature_dim: int = 32
    item_feature_dim: int = 32
    embedding_dim: int = 64
    learning_rate: float = 0.01
    reg: float = 0.001
    n_epochs: int = 50
    temperature: float = 0.1
    init_std: float = 0.01
    seed: int = 42


@dataclass
class TwoTowerModel(ActivitySearchService):
    """Two-Tower retrieval model with contrastive learning.

    User tower and item tower project features into a shared
    embedding space. Dot product similarity scores retrieval.
    """

    config: TwoTowerConfig = field(default_factory=TwoTowerConfig)

    # Tower weights (populated during train)
    W_user: np.ndarray | None = None
    b_user: np.ndarray | None = None
    W_item: np.ndarray | None = None
    b_item: np.ndarray | None = None

    # ID maps
    item_id_map: dict[str, int] = field(default_factory=dict)
    item_features_cache: np.ndarray | None = None

    training_loss_history: list[float] = field(default_factory=list)

    def _user_tower(self, features: np.ndarray) -> np.ndarray:
        """Compute user embedding: ReLU(W_user @ features + b_user)."""
        return _relu(features @ self.W_user.T + self.b_user)

    def _item_tower(self, features: np.ndarray) -> np.ndarray:
        """Compute item embedding: ReLU(W_item @ features + b_item)."""
        return _relu(features @ self.W_item.T + self.b_item)

    def train(
        self,
        user_features: np.ndarray,
        item_features: np.ndarray,
        positive_pairs: np.ndarray,
        item_ids: list[str],
    ) -> dict[str, Any]:
        """Train the two-tower model with contrastive loss.

        Args:
            user_features: (n_users, user_feature_dim) array.
            item_features: (n_items, item_feature_dim) array.
            positive_pairs: (N, 2) array of (user_idx, item_idx) positive pairs.
            item_ids: ordered list of item ID strings.

        Returns:
            Metrics dict.
        """
        rng = np.random.RandomState(self.config.seed)

        n_users, u_dim = user_features.shape
        n_items, i_dim = item_features.shape

        assert u_dim == self.config.user_feature_dim, (
            f"user_features dim {u_dim} != config {self.config.user_feature_dim}"
        )
        assert i_dim == self.config.item_feature_dim, (
            f"item_features dim {i_dim} != config {self.config.item_feature_dim}"
        )

        self.item_id_map = {iid: idx for idx, iid in enumerate(item_ids)}
        self.item_features_cache = item_features.copy()

        # Initialize weights
        e_dim = self.config.embedding_dim
        self.W_user = rng.normal(0, self.config.init_std, (e_dim, u_dim))
        self.b_user = np.zeros(e_dim)
        self.W_item = rng.normal(0, self.config.init_std, (e_dim, i_dim))
        self.b_item = np.zeros(e_dim)

        self.training_loss_history = []
        n_pairs = len(positive_pairs)

        for epoch in range(self.config.n_epochs):
            order = rng.permutation(n_pairs)
            epoch_loss = 0.0

            # Mini-batch: process all pairs, use in-batch negatives
            batch_size = min(64, n_pairs)
            for start in range(0, n_pairs, batch_size):
                end = min(start + batch_size, n_pairs)
                batch_indices = order[start:end]
                bs = len(batch_indices)

                u_indices = positive_pairs[batch_indices, 0]
                i_indices = positive_pairs[batch_indices, 1]

                # Forward pass
                u_feats = user_features[u_indices]  # (bs, u_dim)
                i_feats = item_features[i_indices]  # (bs, i_dim)

                u_pre = u_feats @ self.W_user.T + self.b_user  # (bs, e_dim)
                i_pre = i_feats @ self.W_item.T + self.b_item  # (bs, e_dim)

                u_emb = _relu(u_pre)  # (bs, e_dim)
                i_emb = _relu(i_pre)  # (bs, e_dim)

                # In-batch negatives: similarity matrix (bs, bs)
                sim_matrix = (u_emb @ i_emb.T) / self.config.temperature

                # Contrastive loss: cross-entropy where positive is on diagonal
                labels = np.arange(bs)
                log_probs = sim_matrix - np.log(np.sum(np.exp(sim_matrix - np.max(sim_matrix, axis=1, keepdims=True)), axis=1, keepdims=True)) - np.max(sim_matrix, axis=1, keepdims=True)
                # Correct log softmax
                shifted = sim_matrix - np.max(sim_matrix, axis=1, keepdims=True)
                log_sum_exp = np.log(np.sum(np.exp(shifted), axis=1))
                loss_per_sample = -(shifted[np.arange(bs), labels] - log_sum_exp)
                batch_loss = np.mean(loss_per_sample)
                epoch_loss += batch_loss * bs

                # Backward pass
                probs = _softmax(sim_matrix)  # (bs, bs)
                probs[np.arange(bs), labels] -= 1.0  # gradient of CE w.r.t. logits
                probs /= bs

                # Gradient through similarity
                d_u_emb = (probs @ i_emb) / self.config.temperature  # (bs, e_dim)
                d_i_emb = (probs.T @ u_emb) / self.config.temperature  # (bs, e_dim)

                # Gradient through ReLU
                d_u_pre = d_u_emb * _relu_grad(u_pre)  # (bs, e_dim)
                d_i_pre = d_i_emb * _relu_grad(i_pre)  # (bs, e_dim)

                # Weight gradients
                dW_user = d_u_pre.T @ u_feats + self.config.reg * self.W_user  # (e_dim, u_dim)
                db_user = np.sum(d_u_pre, axis=0) + self.config.reg * self.b_user
                dW_item = d_i_pre.T @ i_feats + self.config.reg * self.W_item  # (e_dim, i_dim)
                db_item = np.sum(d_i_pre, axis=0) + self.config.reg * self.b_item

                # SGD update
                self.W_user -= self.config.learning_rate * dW_user
                self.b_user -= self.config.learning_rate * db_user
                self.W_item -= self.config.learning_rate * dW_item
                self.b_item -= self.config.learning_rate * db_item

            avg_loss = epoch_loss / max(n_pairs, 1)
            self.training_loss_history.append(avg_loss)

            if epoch % 10 == 0 or epoch == self.config.n_epochs - 1:
                logger.info(
                    "TwoTower epoch %d/%d -- avg_loss=%.6f",
                    epoch + 1, self.config.n_epochs, avg_loss,
                )

        metrics = {
            "final_loss": self.training_loss_history[-1] if self.training_loss_history else None,
            "n_epochs": self.config.n_epochs,
            "n_pairs": n_pairs,
            "n_users": n_users,
            "n_items": n_items,
            "embedding_dim": self.config.embedding_dim,
            "loss_history": self.training_loss_history,
        }
        return metrics

    def predict(
        self,
        user_features: np.ndarray,
        candidate_items: list[dict[str, Any]],
    ) -> list[tuple[str, float]]:
        """Score and rank candidate items for a user.

        Args:
            user_features: (user_feature_dim,) feature vector for one user.
            candidate_items: list of dicts with 'id' (str) and 'features' (np.ndarray).

        Returns:
            List of (item_id, score) sorted descending.
        """
        if self.W_user is None or self.W_item is None:
            raise RuntimeError("Model not trained. Call train() first.")

        if len(candidate_items) == 0:
            return []

        u_emb = self._user_tower(user_features.reshape(1, -1))[0]  # (e_dim,)

        results: list[tuple[str, float]] = []
        for item in candidate_items:
            item_feats = item["features"]
            i_emb = self._item_tower(item_feats.reshape(1, -1))[0]
            score = float(np.dot(u_emb, i_emb))
            results.append((item["id"], score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def search(
        self,
        user_features: np.ndarray,
        candidate_items: list[dict[str, Any]],
        top_k: int = 20,
    ) -> list[tuple[str, float]]:
        """ActivitySearchService interface implementation."""
        ranked = self.predict(user_features, candidate_items)
        return ranked[:top_k]

    def save(self, artifact_path: str) -> str:
        """Serialize model to disk. Returns SHA-256 hash."""
        os.makedirs(os.path.dirname(artifact_path) or ".", exist_ok=True)

        state = {
            "config": self.config,
            "W_user": self.W_user,
            "b_user": self.b_user,
            "W_item": self.W_item,
            "b_item": self.b_item,
            "item_id_map": self.item_id_map,
            "item_features_cache": self.item_features_cache,
            "training_loss_history": self.training_loss_history,
        }
        with open(artifact_path, "wb") as f:
            pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)

        sha = hashlib.sha256()
        with open(artifact_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha.update(chunk)
        return sha.hexdigest()

    @classmethod
    def load(cls, artifact_path: str) -> "TwoTowerModel":
        """Deserialize model from disk."""
        with open(artifact_path, "rb") as f:
            state = pickle.load(f)

        model = cls(config=state["config"])
        model.W_user = state["W_user"]
        model.b_user = state["b_user"]
        model.W_item = state["W_item"]
        model.b_item = state["b_item"]
        model.item_id_map = state["item_id_map"]
        model.item_features_cache = state["item_features_cache"]
        model.training_loss_history = state["training_loss_history"]
        return model

    async def register_model(
        self,
        pool,
        model_name: str,
        version: str,
        artifact_path: str,
        metrics_dict: dict[str, Any],
        description: str | None = None,
        model_type: str = "two_tower",
        stage: str = "staging",
        training_data_range: dict | None = None,
    ) -> str:
        """Write model metadata to the ModelRegistry table.

        Returns:
            The UUID of the newly created ModelRegistry row.
        """
        artifact_hash = None
        if os.path.exists(artifact_path):
            sha = hashlib.sha256()
            with open(artifact_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha.update(chunk)
            artifact_hash = sha.hexdigest()

        row_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        config_snapshot = {
            "user_feature_dim": self.config.user_feature_dim,
            "item_feature_dim": self.config.item_feature_dim,
            "embedding_dim": self.config.embedding_dim,
            "learning_rate": self.config.learning_rate,
            "reg": self.config.reg,
            "n_epochs": self.config.n_epochs,
            "temperature": self.config.temperature,
        }

        await pool.execute(
            """
            INSERT INTO model_registry (
                "id", "modelName", "modelVersion", "stage", "modelType",
                "description", "artifactPath", "artifactHash",
                "configSnapshot", "metrics", "evaluatedAt",
                "trainingDataRange", "parentVersionId",
                "promotedAt", "promotedBy",
                "createdAt", "updatedAt"
            ) VALUES (
                $1, $2, $3, $4::\"ModelStage\", $5,
                $6, $7, $8,
                $9, $10, $11,
                $12, NULL,
                NULL, NULL,
                $13, $14
            )
            ON CONFLICT ("modelName", "modelVersion") DO NOTHING
            """,
            row_id,
            model_name,
            version,
            stage,
            model_type,
            description or f"Two-Tower model {model_name} v{version}",
            artifact_path,
            artifact_hash,
            json.dumps(config_snapshot),
            json.dumps(metrics_dict),
            now,
            json.dumps(training_data_range) if training_data_range else None,
            now,
            now,
        )

        logger.info("Registered Two-Tower model %s v%s (id=%s, stage=%s)", model_name, version, row_id, stage)
        return row_id
