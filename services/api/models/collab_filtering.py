"""
Phase 6.7 -- Collaborative Filtering Warm Start

Collaborative filtering is used ONLY for persona initialization of cold users,
NOT for ranking. It finds warm users with similar onboarding profiles and uses
their behavioral centroids to initialize the new user's persona seed.

CRITICAL PRIVACY CONSTRAINT:
  You are not recommending "users like you also liked X" -- you are initializing
  "users like you started with these dimension values." No cross-user behavioral
  disclosure occurs in the output.

CPU-only: pure numpy, no PyTorch/TensorFlow.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollabFilterConfig:
    """Configuration for collaborative filtering warm start."""

    min_warm_users: int = 50
    n_neighbors: int = 10
    blend_weight: float = 0.6  # 0.6 * collab_centroid + 0.4 * archetype_prior


# SQL: count distinct users with 3+ completed trips
_WARM_USER_COUNT_SQL = """
SELECT COUNT(*) AS cnt FROM (
    SELECT "userId"
    FROM trips
    WHERE "status" = 'completed'
    GROUP BY "userId"
    HAVING COUNT(*) >= 3
) AS warm
"""

# SQL: fetch behavioral signal averages grouped by user + signalType
_WARM_USER_SIGNALS_SQL = """
SELECT bs."userId", bs."signalType", AVG(bs."signalValue") AS avg_value
FROM behavioral_signals bs
WHERE bs."userId" = ANY($1::text[])
GROUP BY bs."userId", bs."signalType"
"""


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors. Returns 0.0 for zero-norm vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _profile_to_vector(profile: dict, dimensions: list[str]) -> np.ndarray:
    """Convert a dimension -> value dict to a numpy vector using consistent ordering."""
    return np.array([float(profile.get(d, 0.0)) for d in dimensions], dtype=np.float64)


class CollabFilter:
    """Collaborative filtering for cold-user persona initialization.

    Finds warm users (3+ completed trips) whose onboarding profiles are most
    similar to the cold user, then blends their behavioral centroid with the
    archetype prior to produce a persona seed.
    """

    def __init__(self, config: CollabFilterConfig | None = None) -> None:
        self.config = config or CollabFilterConfig()

    async def is_active(self, pool) -> bool:
        """Check if enough warm users exist (>= min_warm_users)."""
        row = await pool.fetchrow(_WARM_USER_COUNT_SQL)
        if row is None:
            return False
        count = row["cnt"] if isinstance(row, dict) else row[0]
        return count >= self.config.min_warm_users

    def find_neighbors(
        self,
        user_profile: dict,
        warm_user_profiles: list[dict],
        k: int | None = None,
    ) -> list[str]:
        """Find k most similar warm users by cosine similarity on onboarding dimensions.

        Each profile dict must have a "user_id" key and dimension keys with float values.

        Returns:
            List of user_id strings for the k nearest neighbors.
        """
        k = k if k is not None else self.config.n_neighbors

        if not warm_user_profiles:
            return []

        # Collect all dimensions across all profiles (excluding user_id)
        all_dims: set[str] = set()
        for p in warm_user_profiles:
            all_dims.update(d for d in p if d != "user_id")
        for d in user_profile:
            if d != "user_id":
                all_dims.add(d)
        dimensions = sorted(all_dims)

        if not dimensions:
            return []

        user_vec = _profile_to_vector(user_profile, dimensions)

        scored: list[tuple[str, float]] = []
        for wp in warm_user_profiles:
            wp_vec = _profile_to_vector(wp, dimensions)
            sim = _cosine_similarity(user_vec, wp_vec)
            scored.append((wp["user_id"], sim))

        # Sort descending by similarity, take top k
        scored.sort(key=lambda x: x[1], reverse=True)
        return [uid for uid, _ in scored[:k]]

    async def compute_centroid(
        self, pool, user_ids: list[str]
    ) -> dict[str, float]:
        """Average behavioral signal weights across the neighbor set.

        Returns:
            dimension -> average value mapping.
        """
        if not user_ids:
            return {}

        rows = await pool.fetch(_WARM_USER_SIGNALS_SQL, user_ids)

        # Accumulate per-signalType: sum of avg_value per user, then average
        dim_values: dict[str, list[float]] = {}
        for row in rows:
            signal_type = row["signalType"] if isinstance(row, dict) else row[1]
            avg_val = row["avg_value"] if isinstance(row, dict) else row[2]
            dim_values.setdefault(signal_type, []).append(float(avg_val))

        centroid: dict[str, float] = {}
        for dim, vals in dim_values.items():
            centroid[dim] = float(np.mean(vals))

        return centroid

    async def initialize_persona(
        self,
        user_profile: dict,
        archetype_prior: dict,
        pool,
        warm_user_profiles: list[dict] | None = None,
    ) -> dict[str, float]:
        """Initialize a cold user's persona seed.

        If collaborative filtering is not active (< min_warm_users), returns
        the archetype_prior unchanged.

        Blend formula: 0.6 * collab_centroid + 0.4 * archetype_prior

        Returns:
            Dimension -> value mapping for the persona seed.
            PRIVACY: output contains only aggregated dimension values,
            never individual user behaviors or IDs.
        """
        if not await self.is_active(pool):
            logger.info("CollabFilter inactive (< %d warm users), using archetype prior", self.config.min_warm_users)
            return dict(archetype_prior)

        if warm_user_profiles is None:
            warm_user_profiles = []

        neighbor_ids = self.find_neighbors(user_profile, warm_user_profiles)

        if not neighbor_ids:
            return dict(archetype_prior)

        centroid = await self.compute_centroid(pool, neighbor_ids)

        if not centroid:
            return dict(archetype_prior)

        # Blend: 0.6 * centroid + 0.4 * archetype_prior
        blend_w = self.config.blend_weight
        all_dims = set(centroid.keys()) | set(archetype_prior.keys())
        result: dict[str, float] = {}
        for dim in all_dims:
            c_val = centroid.get(dim, 0.0)
            a_val = archetype_prior.get(dim, 0.0)
            result[dim] = blend_w * c_val + (1.0 - blend_w) * a_val

        return result
