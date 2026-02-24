"""
BPR (Bayesian Personalized Ranking) model -- Phase 6.1.

CPU-only matrix factorization trained via SGD on BPR triplets.
Training data: Parquet files with columns (user_id, pos_item, neg_item, timestamp).

Architecture:
  - user_factors: (n_users, n_factors) latent matrix
  - item_factors: (n_items, n_factors) latent matrix
  - BPR-OPT loss: sum(ln(sigma(x_ui - x_uj))) - reg * (||W||^2)
  - SGD updates per triplet

No PyTorch, no TensorFlow, no GPU. Pure numpy.
"""

import hashlib
import json
import logging
import os
import pickle
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def _sigmoid(x: np.ndarray) -> np.ndarray:
    """Numerically stable sigmoid."""
    return np.where(
        x >= 0,
        1.0 / (1.0 + np.exp(-x)),
        np.exp(x) / (1.0 + np.exp(x)),
    )


@dataclass
class BPRConfig:
    """Hyperparameters for BPR training."""

    n_factors: int = 64
    learning_rate: float = 0.01
    reg: float = 0.001
    n_epochs: int = 50
    init_std: float = 0.01
    seed: int = 42


@dataclass
class BPRModel:
    """Bayesian Personalized Ranking via matrix factorization.

    Trains on (user, positive_item, negative_item) triplets using
    the BPR-OPT objective with SGD updates.
    """

    config: BPRConfig = field(default_factory=BPRConfig)

    # Populated during train()
    user_factors: np.ndarray | None = None
    item_factors: np.ndarray | None = None
    user_id_map: dict[str, int] = field(default_factory=dict)
    item_id_map: dict[str, int] = field(default_factory=dict)
    reverse_item_map: dict[int, str] = field(default_factory=dict)
    training_loss_history: list[float] = field(default_factory=list)

    def train(self, triplets: np.ndarray, user_ids: list[str], item_ids: list[str]) -> dict[str, Any]:
        """Train the BPR model on triplets.

        Args:
            triplets: (N, 3) array of (user_idx, pos_item_idx, neg_item_idx) integer indices.
            user_ids: ordered list of user ID strings (index -> id).
            item_ids: ordered list of item ID strings (index -> id).

        Returns:
            Metrics dict with final_loss, n_epochs, n_triplets, convergence info.
        """
        rng = np.random.RandomState(self.config.seed)

        n_users = len(user_ids)
        n_items = len(item_ids)

        self.user_id_map = {uid: idx for idx, uid in enumerate(user_ids)}
        self.item_id_map = {iid: idx for idx, iid in enumerate(item_ids)}
        self.reverse_item_map = {idx: iid for iid, idx in self.item_id_map.items()}

        # Initialize latent factors
        self.user_factors = rng.normal(0, self.config.init_std, (n_users, self.config.n_factors))
        self.item_factors = rng.normal(0, self.config.init_std, (n_items, self.config.n_factors))

        self.training_loss_history = []
        n_triplets = len(triplets)

        for epoch in range(self.config.n_epochs):
            # Shuffle triplets each epoch
            order = rng.permutation(n_triplets)
            epoch_loss = 0.0

            for idx in order:
                u, i, j = int(triplets[idx, 0]), int(triplets[idx, 1]), int(triplets[idx, 2])

                # Score difference
                x_uij = (
                    np.dot(self.user_factors[u], self.item_factors[i])
                    - np.dot(self.user_factors[u], self.item_factors[j])
                )

                # BPR gradient: (1 - sigmoid(x_uij))
                sig = float(_sigmoid(np.array([x_uij]))[0])
                grad_coeff = 1.0 - sig

                # SGD updates
                u_grad = grad_coeff * (self.item_factors[i] - self.item_factors[j]) - self.config.reg * self.user_factors[u]
                i_grad = grad_coeff * self.user_factors[u] - self.config.reg * self.item_factors[i]
                j_grad = -grad_coeff * self.user_factors[u] - self.config.reg * self.item_factors[j]

                self.user_factors[u] += self.config.learning_rate * u_grad
                self.item_factors[i] += self.config.learning_rate * i_grad
                self.item_factors[j] += self.config.learning_rate * j_grad

                # BPR-OPT loss component
                epoch_loss += -np.log(sig + 1e-10)

            avg_loss = epoch_loss / max(n_triplets, 1)
            self.training_loss_history.append(avg_loss)

            if epoch % 10 == 0 or epoch == self.config.n_epochs - 1:
                logger.info("BPR epoch %d/%d -- avg_loss=%.6f", epoch + 1, self.config.n_epochs, avg_loss)

        metrics = {
            "final_loss": self.training_loss_history[-1] if self.training_loss_history else None,
            "n_epochs": self.config.n_epochs,
            "n_triplets": n_triplets,
            "n_users": n_users,
            "n_items": n_items,
            "n_factors": self.config.n_factors,
            "loss_history": self.training_loss_history,
        }
        return metrics

    def train_from_parquet(self, parquet_path: str) -> dict[str, Any]:
        """Train from a Parquet file with columns: user_id, pos_item, neg_item, timestamp.

        Reads the Parquet file, builds ID maps, and delegates to train().
        """
        try:
            import pyarrow.parquet as pq
        except ImportError:
            raise ImportError("pyarrow is required to read Parquet files. Install with: pip install pyarrow")

        table = pq.read_table(parquet_path)
        df_dict = {col: table.column(col).to_pylist() for col in table.column_names}

        user_id_col = df_dict["user_id"]
        pos_item_col = df_dict["pos_item"]
        neg_item_col = df_dict["neg_item"]

        # Build unique ID lists
        unique_users = sorted(set(user_id_col))
        all_items = set(pos_item_col) | set(neg_item_col)
        unique_items = sorted(all_items)

        user_map = {uid: idx for idx, uid in enumerate(unique_users)}
        item_map = {iid: idx for idx, iid in enumerate(unique_items)}

        # Build triplet array
        n = len(user_id_col)
        triplets = np.zeros((n, 3), dtype=np.int32)
        for row in range(n):
            triplets[row, 0] = user_map[user_id_col[row]]
            triplets[row, 1] = item_map[pos_item_col[row]]
            triplets[row, 2] = item_map[neg_item_col[row]]

        return self.train(triplets, unique_users, unique_items)

    def predict(self, user_id: str, item_ids: list[str]) -> list[tuple[str, float]]:
        """Score and rank items for a user.

        Args:
            user_id: The user to score for.
            item_ids: Candidate item IDs to rank.

        Returns:
            List of (item_id, score) tuples sorted descending by score.
            Unknown items get score 0.0. Unknown users get score 0.0 for all items.
        """
        if self.user_factors is None or self.item_factors is None:
            raise RuntimeError("Model not trained. Call train() first.")

        if user_id not in self.user_id_map:
            # Cold-start: return items with zero scores
            return [(iid, 0.0) for iid in item_ids]

        u_idx = self.user_id_map[user_id]
        u_vec = self.user_factors[u_idx]

        results: list[tuple[str, float]] = []
        for iid in item_ids:
            if iid in self.item_id_map:
                i_idx = self.item_id_map[iid]
                score = float(np.dot(u_vec, self.item_factors[i_idx]))
            else:
                score = 0.0
            results.append((iid, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def save(self, artifact_path: str) -> str:
        """Serialize model to disk via pickle.

        Returns:
            SHA-256 hash of the artifact file.
        """
        os.makedirs(os.path.dirname(artifact_path) or ".", exist_ok=True)

        state = {
            "config": self.config,
            "user_factors": self.user_factors,
            "item_factors": self.item_factors,
            "user_id_map": self.user_id_map,
            "item_id_map": self.item_id_map,
            "reverse_item_map": self.reverse_item_map,
            "training_loss_history": self.training_loss_history,
        }
        with open(artifact_path, "wb") as f:
            pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)

        # Compute artifact hash
        sha = hashlib.sha256()
        with open(artifact_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha.update(chunk)
        return sha.hexdigest()

    @classmethod
    def load(cls, artifact_path: str) -> "BPRModel":
        """Deserialize model from disk."""
        with open(artifact_path, "rb") as f:
            state = pickle.load(f)

        model = cls(config=state["config"])
        model.user_factors = state["user_factors"]
        model.item_factors = state["item_factors"]
        model.user_id_map = state["user_id_map"]
        model.item_id_map = state["item_id_map"]
        model.reverse_item_map = state["reverse_item_map"]
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
        model_type: str = "bpr",
        stage: str = "staging",
        training_data_range: dict | None = None,
    ) -> str:
        """Write model metadata to the ModelRegistry table.

        Args:
            pool: asyncpg connection pool.
            model_name: e.g. "bpr-v1".
            version: e.g. "1.0.0".
            artifact_path: path where the model artifact is saved.
            metrics_dict: training metrics (loss, AUC, etc.).
            description: human-readable description.
            model_type: model type string.
            stage: ModelStage enum value (staging, ab_test, production, archived).
            training_data_range: optional JSON dict with date range info.

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
            "n_factors": self.config.n_factors,
            "learning_rate": self.config.learning_rate,
            "reg": self.config.reg,
            "n_epochs": self.config.n_epochs,
        }

        await pool.execute(
            """
            INSERT INTO "ModelRegistry" (
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
            description or f"BPR model {model_name} v{version}",
            artifact_path,
            artifact_hash,
            json.dumps(config_snapshot),
            json.dumps(metrics_dict),
            now,
            json.dumps(training_data_range) if training_data_range else None,
            now,
            now,
        )

        logger.info("Registered BPR model %s v%s (id=%s, stage=%s)", model_name, version, row_id, stage)
        return row_id
