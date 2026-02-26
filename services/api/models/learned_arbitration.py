"""
Phase 6.9 -- Learned Arbitration (DATA-GATED)

Train a small gradient-boosted classifier on arbitration features to predict
which ranker to trust. Replaces rule-based arbitration with a learned classifier.

DATA-GATED: Requires 1,500+ ArbitrationEvent rows with outcome data before
training. Full infrastructure is built but marked as not-yet-active.

CPU-only: pure numpy AdaBoost with decision stumps, no sklearn/PyTorch/TensorFlow.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LearnedArbConfig:
    """Configuration for learned arbitration."""

    min_events: int = 1500
    n_estimators: int = 100
    learning_rate: float = 0.1
    max_depth: int = 3  # unused for stumps, reserved for future tree depth


# SQL: check if enough ArbitrationEvent rows exist
_READINESS_SQL = """
SELECT COUNT(*) AS cnt FROM arbitration_events WHERE "accepted" IS NOT NULL
"""

# SQL: fetch training data
_TRAINING_DATA_SQL = """
SELECT "arbitrationRule", "servedSource", "accepted", "agreementScore", "contextSnapshot"
FROM arbitration_events
WHERE "accepted" IS NOT NULL
ORDER BY "createdAt" ASC
"""

# Known arbitration rules for one-hot encoding
_KNOWN_RULES = [
    "ml_preferred",
    "llm_preferred",
    "agreement_high",
    "agreement_low",
    "fallback",
]


class DecisionStump:
    """A single decision stump: splits on one feature at one threshold."""

    def __init__(self) -> None:
        self.feature_idx: int = 0
        self.threshold: float = 0.0
        self.polarity: int = 1  # 1 or -1
        self.alpha: float = 0.0

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict +1 or -1 for each sample."""
        n_samples = X.shape[0]
        predictions = np.ones(n_samples, dtype=np.float64)
        if self.polarity == 1:
            predictions[X[:, self.feature_idx] < self.threshold] = -1.0
        else:
            predictions[X[:, self.feature_idx] >= self.threshold] = -1.0
        return predictions

    def to_dict(self) -> dict:
        return {
            "feature_idx": self.feature_idx,
            "threshold": float(self.threshold),
            "polarity": self.polarity,
            "alpha": float(self.alpha),
        }

    @classmethod
    def from_dict(cls, d: dict) -> DecisionStump:
        stump = cls()
        stump.feature_idx = d["feature_idx"]
        stump.threshold = d["threshold"]
        stump.polarity = d["polarity"]
        stump.alpha = d["alpha"]
        return stump


def _train_adaboost(
    X: np.ndarray,
    y: np.ndarray,
    n_estimators: int = 100,
    learning_rate: float = 0.1,
) -> list[DecisionStump]:
    """Train AdaBoost with decision stumps.

    Args:
        X: Feature matrix (n_samples, n_features)
        y: Labels, +1 or -1 (n_samples,)
        n_estimators: Number of stumps
        learning_rate: Shrinkage factor for alpha

    Returns:
        List of trained DecisionStump instances.
    """
    n_samples, n_features = X.shape
    weights = np.ones(n_samples, dtype=np.float64) / n_samples
    stumps: list[DecisionStump] = []

    for _ in range(n_estimators):
        best_stump = DecisionStump()
        best_error = float("inf")

        for feat_idx in range(n_features):
            feature_vals = X[:, feat_idx]
            thresholds = np.unique(feature_vals)

            for threshold in thresholds:
                for polarity in [1, -1]:
                    predictions = np.ones(n_samples, dtype=np.float64)
                    if polarity == 1:
                        predictions[feature_vals < threshold] = -1.0
                    else:
                        predictions[feature_vals >= threshold] = -1.0

                    err = float(np.sum(weights * (predictions != y)))
                    if err < best_error:
                        best_error = err
                        best_stump.feature_idx = feat_idx
                        best_stump.threshold = float(threshold)
                        best_stump.polarity = polarity

        # Compute alpha
        eps = max(best_error, 1e-10)
        if eps >= 1.0:
            # Cannot improve further
            break
        alpha = learning_rate * 0.5 * np.log((1 - eps) / eps)
        best_stump.alpha = float(alpha)

        # Update weights
        preds = best_stump.predict(X)
        weights *= np.exp(-alpha * y * preds)
        weights /= np.sum(weights)

        stumps.append(best_stump)

    return stumps


def _adaboost_predict(stumps: list[DecisionStump], X: np.ndarray) -> np.ndarray:
    """Predict raw scores (not thresholded) from AdaBoost ensemble."""
    n_samples = X.shape[0]
    scores = np.zeros(n_samples, dtype=np.float64)
    for stump in stumps:
        scores += stump.alpha * stump.predict(X)
    return scores


def _sigmoid(x: np.ndarray) -> np.ndarray:
    """Numerically stable sigmoid."""
    return np.where(
        x >= 0,
        1.0 / (1.0 + np.exp(-x)),
        np.exp(x) / (1.0 + np.exp(x)),
    )


# Default vibe dimensions used in persona seeds
_VIBE_DIMENSIONS = [
    "adventure",
    "culture",
    "food",
    "nightlife",
    "nature",
    "relaxation",
    "shopping",
    "local",
]


class LearnedArbitrator:
    """Data-gated learned arbitration model.

    Trains AdaBoost with decision stumps on ArbitrationEvent data to predict
    whether the ML-ranked recommendation will be accepted by the user.
    Replaces rule-based arbitration once 1,500+ events are collected.
    """

    def __init__(self, config: LearnedArbConfig | None = None) -> None:
        self.config = config or LearnedArbConfig()
        self._stumps: list[DecisionStump] = []
        self._trained = False

    @property
    def is_trained(self) -> bool:
        return self._trained and len(self._stumps) > 0

    async def is_ready(self, pool) -> bool:
        """Check if enough ArbitrationEvent rows with outcomes exist."""
        row = await pool.fetchrow(_READINESS_SQL)
        if row is None:
            return False
        count = row["cnt"] if isinstance(row, dict) else row[0]
        return count >= self.config.min_events

    def extract_features(self, event: dict) -> np.ndarray:
        """Extract feature vector from an ArbitrationEvent dict.

        Features (in order):
          0: agreementScore (float)
          1: ml_confidence (from contextSnapshot, default 0.5)
          2: user_signal_count (from contextSnapshot, default 0)
          3: trip_count (from contextSnapshot, default 0)
          4..4+len(_KNOWN_RULES)-1: one-hot arbitrationRule
          4+len(_KNOWN_RULES)..end: persona vibe dimensions from contextSnapshot
        """
        features: list[float] = []

        # Continuous features
        features.append(float(event.get("agreementScore", 0.0) or 0.0))

        ctx = event.get("contextSnapshot") or {}
        if isinstance(ctx, str):
            try:
                ctx = json.loads(ctx)
            except (json.JSONDecodeError, TypeError):
                ctx = {}

        features.append(float(ctx.get("ml_confidence", 0.5)))
        features.append(float(ctx.get("user_signal_count", 0)))
        features.append(float(ctx.get("trip_count", 0)))

        # One-hot encode arbitration rule
        rule = event.get("arbitrationRule", "")
        for known_rule in _KNOWN_RULES:
            features.append(1.0 if rule == known_rule else 0.0)

        # Persona vibe dimensions from contextSnapshot
        persona = ctx.get("persona", {})
        if isinstance(persona, str):
            try:
                persona = json.loads(persona)
            except (json.JSONDecodeError, TypeError):
                persona = {}
        for dim in _VIBE_DIMENSIONS:
            features.append(float(persona.get(dim, 0.0)))

        return np.array(features, dtype=np.float64)

    async def train(self, pool) -> dict:
        """Fetch ArbitrationEvents, extract features, train AdaBoost.

        Returns:
            Training metrics: accuracy, auc_approx, n_events.
        """
        rows = await pool.fetch(_TRAINING_DATA_SQL)

        if not rows:
            raise ValueError("No training data available")

        # Build feature matrix and labels
        X_list: list[np.ndarray] = []
        y_list: list[float] = []

        for row in rows:
            event = dict(row) if not isinstance(row, dict) else row
            features = self.extract_features(event)
            X_list.append(features)
            accepted = event.get("accepted", False)
            y_list.append(1.0 if accepted else -1.0)

        X = np.array(X_list, dtype=np.float64)
        y = np.array(y_list, dtype=np.float64)

        n_events = len(y_list)

        # Train AdaBoost
        self._stumps = _train_adaboost(
            X, y,
            n_estimators=self.config.n_estimators,
            learning_rate=self.config.learning_rate,
        )
        self._trained = True

        # Compute training metrics
        raw_scores = _adaboost_predict(self._stumps, X)
        predictions = np.sign(raw_scores)
        # Handle zeros (assign to +1)
        predictions[predictions == 0] = 1.0
        accuracy = float(np.mean(predictions == y))

        # AUC approximation: sort by score, compute concordance
        auc_approx = self._compute_auc_approx(raw_scores, y)

        metrics = {
            "accuracy": accuracy,
            "auc_approx": auc_approx,
            "n_events": n_events,
            "n_estimators": len(self._stumps),
        }
        logger.info("LearnedArbitrator trained: %s", metrics)
        return metrics

    def _compute_auc_approx(self, scores: np.ndarray, labels: np.ndarray) -> float:
        """Approximate AUC via concordance of pairs."""
        pos_scores = scores[labels == 1.0]
        neg_scores = scores[labels == -1.0]

        if len(pos_scores) == 0 or len(neg_scores) == 0:
            return 0.5

        concordant = 0
        total = len(pos_scores) * len(neg_scores)
        for ps in pos_scores:
            concordant += int(np.sum(ps > neg_scores))
            concordant += int(np.sum(ps == neg_scores)) * 0.5

        return concordant / total if total > 0 else 0.5

    def predict(self, features: np.ndarray) -> float:
        """Predict confidence that ML source will be accepted.

        Args:
            features: Feature vector from extract_features().

        Returns:
            Float in [0.0, 1.0], calibrated via sigmoid.
        """
        if not self.is_trained:
            raise RuntimeError("Model not trained. Call train() first.")

        X = features.reshape(1, -1)
        raw_score = _adaboost_predict(self._stumps, X)[0]
        return float(_sigmoid(np.array([raw_score]))[0])

    def save(self, path: str | Path) -> str:
        """Save model to JSON file. Returns SHA-256 hash of artifact."""
        if not self.is_trained:
            raise RuntimeError("Model not trained. Call train() first.")

        artifact = {
            "stumps": [s.to_dict() for s in self._stumps],
            "config": {
                "n_estimators": self.config.n_estimators,
                "learning_rate": self.config.learning_rate,
                "max_depth": self.config.max_depth,
            },
        }
        data = json.dumps(artifact, indent=2, sort_keys=True)

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)

        sha = hashlib.sha256(data.encode()).hexdigest()
        logger.info("LearnedArbitrator saved to %s (hash=%s)", path, sha[:12])
        return sha

    def load(self, path: str | Path) -> str:
        """Load model from JSON file. Returns SHA-256 hash of artifact."""
        path = Path(path)
        data = path.read_text()
        sha = hashlib.sha256(data.encode()).hexdigest()

        artifact = json.loads(data)
        self._stumps = [DecisionStump.from_dict(d) for d in artifact["stumps"]]
        self._trained = True

        logger.info("LearnedArbitrator loaded from %s (hash=%s)", path, sha[:12])
        return sha

    async def register_model(self, pool, artifact_path: str, artifact_hash: str) -> None:
        """Register the trained model in ModelRegistry with stage='staging'."""
        register_sql = """
        INSERT INTO model_registry (
            "id", "modelName", "modelVersion", "stage", "modelType",
            "description", "artifactPath", "artifactHash",
            "configSnapshot", "createdAt", "updatedAt"
        )
        VALUES (
            gen_random_uuid(),
            'learned_arbitrator',
            $1,
            $2::"ModelStage",
            'classifier',
            'AdaBoost decision stump ensemble for arbitration',
            $3,
            $4,
            $5,
            NOW(),
            NOW()
        )
        ON CONFLICT ("modelName", "modelVersion") DO NOTHING
        """
        version = f"v1-{artifact_hash[:8]}"
        config_json = json.dumps({
            "n_estimators": self.config.n_estimators,
            "learning_rate": self.config.learning_rate,
            "max_depth": self.config.max_depth,
        })
        await pool.execute(
            register_sql,
            version,
            "staging",
            artifact_path,
            artifact_hash,
            config_json,
        )
        logger.info("LearnedArbitrator registered as %s (stage=staging)", version)
