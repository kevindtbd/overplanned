"""
SASRec (Self-Attentive Sequential Recommendation) -- Phase 6.3.

CPU-only self-attention model for sequential recommendation.
Re-ranks candidates from Two-Tower retrieval using the user's action sequence.

Architecture:
  - Item embeddings + positional embeddings
  - Multi-head self-attention (2 heads, 64 dim) with causal masking
  - Layer norm + residual connections
  - Next-item prediction via cross-entropy loss

No PyTorch, no TensorFlow, no GPU, no cuda(). Pure numpy.
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


def _layer_norm(x: np.ndarray, gamma: np.ndarray, beta: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """Layer normalization over the last axis."""
    mean = np.mean(x, axis=-1, keepdims=True)
    var = np.var(x, axis=-1, keepdims=True)
    return gamma * (x - mean) / np.sqrt(var + eps) + beta


def _softmax(x: np.ndarray) -> np.ndarray:
    """Numerically stable softmax over last axis."""
    shifted = x - np.max(x, axis=-1, keepdims=True)
    exp_x = np.exp(shifted)
    return exp_x / np.sum(exp_x, axis=-1, keepdims=True)


def _gelu(x: np.ndarray) -> np.ndarray:
    """GELU activation approximation."""
    return 0.5 * x * (1.0 + np.tanh(np.sqrt(2.0 / np.pi) * (x + 0.044715 * x ** 3)))


@dataclass
class SASRecConfig:
    """Hyperparameters for SASRec."""

    max_seq_len: int = 50
    n_items: int = 0  # Set during training
    embedding_dim: int = 64
    n_heads: int = 2
    n_layers: int = 2
    dropout_rate: float = 0.0  # No dropout at inference; placeholder for future
    learning_rate: float = 0.001
    reg: float = 0.0001
    n_epochs: int = 50
    init_std: float = 0.02
    seed: int = 42


@dataclass
class SASRecModel:
    """Self-Attentive Sequential Recommendation model.

    Uses multi-head self-attention over the user's interaction sequence
    with causal masking to predict the next item. Re-ranks candidates
    from the Two-Tower retrieval stage.
    """

    config: SASRecConfig = field(default_factory=SASRecConfig)

    # Embeddings
    item_embeddings: np.ndarray | None = None  # (n_items + 1, d) -- index 0 = padding
    position_embeddings: np.ndarray | None = None  # (max_seq_len, d)

    # Attention layers: list of layer params
    attention_layers: list[dict[str, np.ndarray]] = field(default_factory=list)

    # ID maps
    item_id_map: dict[str, int] = field(default_factory=dict)  # str -> 1-indexed
    reverse_item_map: dict[int, str] = field(default_factory=dict)

    training_loss_history: list[float] = field(default_factory=list)

    def _init_weights(self, rng: np.random.RandomState) -> None:
        """Initialize all model parameters."""
        d = self.config.embedding_dim
        n_items = self.config.n_items
        max_len = self.config.max_seq_len
        n_heads = self.config.n_heads
        std = self.config.init_std

        # Item embedding: index 0 is padding (zeros)
        self.item_embeddings = np.zeros((n_items + 1, d))
        self.item_embeddings[1:] = rng.normal(0, std, (n_items, d))

        # Positional embeddings
        self.position_embeddings = rng.normal(0, std, (max_len, d))

        # Attention layers
        head_dim = d // n_heads
        self.attention_layers = []
        for _ in range(self.config.n_layers):
            layer = {
                # Multi-head attention
                "W_q": rng.normal(0, std, (n_heads, d, head_dim)),
                "W_k": rng.normal(0, std, (n_heads, d, head_dim)),
                "W_v": rng.normal(0, std, (n_heads, d, head_dim)),
                "W_o": rng.normal(0, std, (n_heads * head_dim, d)),
                # Layer norm 1 (pre-attention)
                "ln1_gamma": np.ones(d),
                "ln1_beta": np.zeros(d),
                # Layer norm 2 (pre-FFN)
                "ln2_gamma": np.ones(d),
                "ln2_beta": np.zeros(d),
                # Feed-forward
                "W_ff1": rng.normal(0, std, (d, d * 4)),
                "b_ff1": np.zeros(d * 4),
                "W_ff2": rng.normal(0, std, (d * 4, d)),
                "b_ff2": np.zeros(d),
            }
            self.attention_layers.append(layer)

    def _causal_mask(self, seq_len: int) -> np.ndarray:
        """Create causal attention mask. 1 = attend, 0 = mask."""
        mask = np.tril(np.ones((seq_len, seq_len)))
        return mask

    def _multi_head_attention(
        self,
        x: np.ndarray,
        layer: dict[str, np.ndarray],
        mask: np.ndarray,
    ) -> np.ndarray:
        """Multi-head self-attention with causal masking.

        Args:
            x: (seq_len, d) input sequence.
            layer: dict of attention weights.
            mask: (seq_len, seq_len) causal mask.

        Returns:
            (seq_len, d) attended output.
        """
        n_heads = self.config.n_heads
        d = self.config.embedding_dim
        head_dim = d // n_heads
        seq_len = x.shape[0]

        # Compute Q, K, V for each head
        heads_out = []
        for h in range(n_heads):
            Q = x @ layer["W_q"][h]  # (seq_len, head_dim)
            K = x @ layer["W_k"][h]  # (seq_len, head_dim)
            V = x @ layer["W_v"][h]  # (seq_len, head_dim)

            # Scaled dot-product attention
            scores = (Q @ K.T) / np.sqrt(head_dim)  # (seq_len, seq_len)

            # Apply causal mask: set masked positions to -inf
            scores = np.where(mask > 0, scores, -1e9)

            attn_weights = _softmax(scores)  # (seq_len, seq_len)
            head_out = attn_weights @ V  # (seq_len, head_dim)
            heads_out.append(head_out)

        # Concatenate heads and project
        concat = np.concatenate(heads_out, axis=-1)  # (seq_len, n_heads * head_dim)
        output = concat @ layer["W_o"]  # (seq_len, d)
        return output

    def _feed_forward(self, x: np.ndarray, layer: dict[str, np.ndarray]) -> np.ndarray:
        """Position-wise feed-forward network."""
        hidden = _gelu(x @ layer["W_ff1"] + layer["b_ff1"])
        return hidden @ layer["W_ff2"] + layer["b_ff2"]

    def _forward(self, item_indices: np.ndarray) -> np.ndarray:
        """Forward pass through the SASRec model.

        Args:
            item_indices: (seq_len,) array of 1-indexed item indices (0 = padding).

        Returns:
            (seq_len, d) output representations.
        """
        seq_len = len(item_indices)
        effective_len = min(seq_len, self.config.max_seq_len)

        # Truncate to max_seq_len (take most recent)
        if seq_len > self.config.max_seq_len:
            item_indices = item_indices[-self.config.max_seq_len:]
            effective_len = self.config.max_seq_len

        # Get embeddings
        x = self.item_embeddings[item_indices]  # (seq_len, d)
        x = x + self.position_embeddings[:effective_len]  # Add positional

        # Create causal mask
        mask = self._causal_mask(effective_len)

        # Padding mask: zero out positions where item_indices == 0
        padding_mask = (item_indices != 0).astype(np.float64)  # (seq_len,)
        # Expand to (seq_len, seq_len): position j can attend to position i only if i is not padding
        attn_mask = mask * padding_mask[np.newaxis, :]  # broadcast rows

        # Apply transformer layers
        for layer in self.attention_layers:
            # Pre-norm architecture
            normed = _layer_norm(x, layer["ln1_gamma"], layer["ln1_beta"])
            attn_out = self._multi_head_attention(normed, layer, attn_mask)
            x = x + attn_out  # Residual connection

            normed2 = _layer_norm(x, layer["ln2_gamma"], layer["ln2_beta"])
            ff_out = self._feed_forward(normed2, layer)
            x = x + ff_out  # Residual connection

        # Mask out padding positions
        x = x * padding_mask[:, np.newaxis]

        return x

    def train(
        self,
        sequences: list[list[str]],
        item_ids: list[str],
    ) -> dict[str, Any]:
        """Train SASRec on user action sequences.

        For each sequence [a, b, c, d], we use [a, b, c] as input
        and [b, c, d] as targets (next-item prediction).

        Args:
            sequences: list of user action sequences (each is list of item ID strings).
            item_ids: all unique item IDs.

        Returns:
            Training metrics dict.
        """
        rng = np.random.RandomState(self.config.seed)

        # Build ID maps (1-indexed, 0 = padding)
        self.item_id_map = {iid: idx + 1 for idx, iid in enumerate(item_ids)}
        self.reverse_item_map = {idx + 1: iid for idx, iid in enumerate(item_ids)}
        self.config.n_items = len(item_ids)

        self._init_weights(rng)

        # Filter sequences with at least 2 items
        valid_sequences = [seq for seq in sequences if len(seq) >= 2]
        if not valid_sequences:
            logger.warning("No valid sequences (need length >= 2). Skipping training.")
            return {"final_loss": None, "n_epochs": 0, "n_sequences": 0}

        self.training_loss_history = []
        n_items_total = self.config.n_items

        for epoch in range(self.config.n_epochs):
            epoch_loss = 0.0
            total_predictions = 0

            rng.shuffle(valid_sequences)

            for seq in valid_sequences:
                # Map to indices
                indices = []
                for item_id in seq:
                    if item_id in self.item_id_map:
                        indices.append(self.item_id_map[item_id])
                if len(indices) < 2:
                    continue

                # Truncate
                indices = indices[-self.config.max_seq_len - 1:]

                input_seq = np.array(indices[:-1], dtype=np.int32)
                target_seq = np.array(indices[1:], dtype=np.int32)
                seq_len = len(input_seq)

                # Forward pass
                output = self._forward(input_seq)  # (seq_len, d)

                # Compute logits: dot product with all item embeddings
                # output @ item_embeddings.T -> (seq_len, n_items + 1)
                logits = output @ self.item_embeddings.T  # (seq_len, n_items + 1)

                # Cross-entropy loss per position
                for t in range(seq_len):
                    target = target_seq[t]
                    if target == 0:
                        continue

                    probs = _softmax(logits[t:t + 1])[0]  # (n_items + 1,)
                    loss = -np.log(probs[target] + 1e-10)
                    epoch_loss += loss
                    total_predictions += 1

                    # Gradient of cross-entropy w.r.t. logits
                    grad_logits = probs.copy()
                    grad_logits[target] -= 1.0  # (n_items + 1,)

                    # Update item embeddings (simplified SGD on output layer)
                    # d_item_emb = output[t] * grad_logits[item_idx]
                    for item_idx in range(1, n_items_total + 1):
                        self.item_embeddings[item_idx] -= (
                            self.config.learning_rate * grad_logits[item_idx] * output[t]
                            + self.config.reg * self.item_embeddings[item_idx]
                        )

                    # Update output representation -> propagate back through position embeddings
                    grad_output = grad_logits @ self.item_embeddings  # (d,)
                    self.position_embeddings[t] -= self.config.learning_rate * (
                        grad_output + self.config.reg * self.position_embeddings[t]
                    )

            avg_loss = epoch_loss / max(total_predictions, 1)
            self.training_loss_history.append(avg_loss)

            if epoch % 10 == 0 or epoch == self.config.n_epochs - 1:
                logger.info(
                    "SASRec epoch %d/%d -- avg_loss=%.6f (predictions=%d)",
                    epoch + 1, self.config.n_epochs, avg_loss, total_predictions,
                )

        metrics = {
            "final_loss": self.training_loss_history[-1] if self.training_loss_history else None,
            "n_epochs": self.config.n_epochs,
            "n_sequences": len(valid_sequences),
            "n_items": n_items_total,
            "embedding_dim": self.config.embedding_dim,
            "n_heads": self.config.n_heads,
            "n_layers": self.config.n_layers,
            "max_seq_len": self.config.max_seq_len,
            "loss_history": self.training_loss_history,
        }
        return metrics

    def predict(
        self,
        user_sequence: list[str],
        candidate_items: list[str],
    ) -> list[tuple[str, float]]:
        """Re-rank candidate items based on user's action sequence.

        Args:
            user_sequence: list of item IDs the user has interacted with (ordered).
            candidate_items: list of candidate item IDs to re-rank.

        Returns:
            List of (item_id, score) tuples sorted descending.
        """
        if self.item_embeddings is None:
            raise RuntimeError("Model not trained. Call train() first.")

        if not candidate_items:
            return []

        if not user_sequence:
            # Cold start: return candidates with zero scores
            return [(iid, 0.0) for iid in candidate_items]

        # Map sequence to indices
        indices = []
        for item_id in user_sequence:
            if item_id in self.item_id_map:
                indices.append(self.item_id_map[item_id])
        if not indices:
            return [(iid, 0.0) for iid in candidate_items]

        # Truncate to max_seq_len
        indices = indices[-self.config.max_seq_len:]
        input_seq = np.array(indices, dtype=np.int32)

        # Forward pass
        output = self._forward(input_seq)  # (seq_len, d)

        # Use the last position's output as the user representation
        user_repr = output[-1]  # (d,)

        # Score candidates
        results: list[tuple[str, float]] = []
        for item_id in candidate_items:
            if item_id in self.item_id_map:
                idx = self.item_id_map[item_id]
                item_emb = self.item_embeddings[idx]
                score = float(np.dot(user_repr, item_emb))
            else:
                score = 0.0
            results.append((item_id, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def save(self, artifact_path: str) -> str:
        """Serialize model to disk. Returns SHA-256 hash."""
        os.makedirs(os.path.dirname(artifact_path) or ".", exist_ok=True)

        state = {
            "config": self.config,
            "item_embeddings": self.item_embeddings,
            "position_embeddings": self.position_embeddings,
            "attention_layers": self.attention_layers,
            "item_id_map": self.item_id_map,
            "reverse_item_map": self.reverse_item_map,
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
    def load(cls, artifact_path: str) -> "SASRecModel":
        """Deserialize model from disk."""
        with open(artifact_path, "rb") as f:
            state = pickle.load(f)

        model = cls(config=state["config"])
        model.item_embeddings = state["item_embeddings"]
        model.position_embeddings = state["position_embeddings"]
        model.attention_layers = state["attention_layers"]
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
        model_type: str = "sasrec",
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
            "max_seq_len": self.config.max_seq_len,
            "embedding_dim": self.config.embedding_dim,
            "n_heads": self.config.n_heads,
            "n_layers": self.config.n_layers,
            "learning_rate": self.config.learning_rate,
            "reg": self.config.reg,
            "n_epochs": self.config.n_epochs,
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
            description or f"SASRec model {model_name} v{version}",
            artifact_path,
            artifact_hash,
            json.dumps(config_snapshot),
            json.dumps(metrics_dict),
            now,
            json.dumps(training_data_range) if training_data_range else None,
            now,
            now,
        )

        logger.info("Registered SASRec model %s v%s (id=%s, stage=%s)", model_name, version, row_id, stage)
        return row_id
