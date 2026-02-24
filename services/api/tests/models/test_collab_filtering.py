"""
Tests for Phase 6.7 -- Collaborative Filtering Warm Start.

Covers:
- Cosine similarity (correct values, zero vectors, identical vectors)
- Neighbor finding (top-k, empty pool, all-zero profiles)
- Centroid computation (averaging behavior)
- Blend formula (0.6 * centroid + 0.4 * prior)
- Inactive when < 50 warm users
- Privacy: no cross-user behavioral disclosure in output
"""

import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock

from services.api.models.collab_filtering import (
    CollabFilter,
    CollabFilterConfig,
    _cosine_similarity,
    _profile_to_vector,
)


# ===================================================================
# Cosine similarity
# ===================================================================


class TestCosineSimilarity:
    """Core cosine similarity function."""

    def test_identical_vectors(self):
        a = np.array([1.0, 2.0, 3.0])
        result = _cosine_similarity(a, a)
        assert abs(result - 1.0) < 1e-9

    def test_orthogonal_vectors(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        result = _cosine_similarity(a, b)
        assert abs(result) < 1e-9

    def test_opposite_vectors(self):
        a = np.array([1.0, 0.0])
        b = np.array([-1.0, 0.0])
        result = _cosine_similarity(a, b)
        assert abs(result - (-1.0)) < 1e-9

    def test_zero_vector_returns_zero(self):
        a = np.array([0.0, 0.0])
        b = np.array([1.0, 2.0])
        assert _cosine_similarity(a, b) == 0.0

    def test_both_zero_vectors(self):
        a = np.array([0.0, 0.0])
        assert _cosine_similarity(a, a) == 0.0

    def test_known_value(self):
        a = np.array([1.0, 2.0, 3.0])
        b = np.array([4.0, 5.0, 6.0])
        expected = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
        result = _cosine_similarity(a, b)
        assert abs(result - expected) < 1e-9


# ===================================================================
# Profile to vector
# ===================================================================


class TestProfileToVector:
    def test_basic_conversion(self):
        profile = {"adventure": 0.8, "food": 0.6}
        dims = ["adventure", "food"]
        vec = _profile_to_vector(profile, dims)
        np.testing.assert_array_almost_equal(vec, [0.8, 0.6])

    def test_missing_dim_defaults_to_zero(self):
        profile = {"adventure": 0.8}
        dims = ["adventure", "food"]
        vec = _profile_to_vector(profile, dims)
        np.testing.assert_array_almost_equal(vec, [0.8, 0.0])


# ===================================================================
# Neighbor finding
# ===================================================================


class TestFindNeighbors:
    def setup_method(self):
        self.cf = CollabFilter(CollabFilterConfig(n_neighbors=2))

    def test_returns_k_neighbors(self):
        user_profile = {"adventure": 0.9, "food": 0.1}
        warm_profiles = [
            {"user_id": "u1", "adventure": 0.8, "food": 0.2},
            {"user_id": "u2", "adventure": 0.1, "food": 0.9},
            {"user_id": "u3", "adventure": 0.7, "food": 0.3},
        ]
        result = self.cf.find_neighbors(user_profile, warm_profiles, k=2)
        assert len(result) == 2
        # u1 and u3 should be closer to the adventure-heavy user
        assert "u1" in result
        assert "u3" in result

    def test_empty_pool_returns_empty(self):
        result = self.cf.find_neighbors({"adventure": 0.5}, [])
        assert result == []

    def test_k_larger_than_pool(self):
        user_profile = {"adventure": 0.5}
        warm_profiles = [
            {"user_id": "u1", "adventure": 0.8},
        ]
        result = self.cf.find_neighbors(user_profile, warm_profiles, k=10)
        assert result == ["u1"]

    def test_uses_config_k_by_default(self):
        cf = CollabFilter(CollabFilterConfig(n_neighbors=1))
        user_profile = {"adventure": 0.5}
        warm_profiles = [
            {"user_id": "u1", "adventure": 0.8},
            {"user_id": "u2", "adventure": 0.7},
        ]
        result = cf.find_neighbors(user_profile, warm_profiles)
        assert len(result) == 1


# ===================================================================
# Centroid computation
# ===================================================================


class TestComputeCentroid:
    @pytest.mark.asyncio
    async def test_averages_signals(self):
        cf = CollabFilter()
        pool = AsyncMock()
        pool.fetch = AsyncMock(return_value=[
            {"userId": "u1", "signalType": "adventure", "avg_value": 0.8},
            {"userId": "u2", "signalType": "adventure", "avg_value": 0.6},
            {"userId": "u1", "signalType": "food", "avg_value": 0.4},
        ])
        centroid = await cf.compute_centroid(pool, ["u1", "u2"])
        # adventure: mean(0.8, 0.6) = 0.7, food: mean(0.4) = 0.4
        assert abs(centroid["adventure"] - 0.7) < 1e-9
        assert abs(centroid["food"] - 0.4) < 1e-9

    @pytest.mark.asyncio
    async def test_empty_user_ids(self):
        cf = CollabFilter()
        pool = AsyncMock()
        centroid = await cf.compute_centroid(pool, [])
        assert centroid == {}


# ===================================================================
# Blend formula
# ===================================================================


class TestInitializePersona:
    @pytest.mark.asyncio
    async def test_blend_formula(self):
        """0.6 * centroid + 0.4 * prior"""
        cf = CollabFilter(CollabFilterConfig(min_warm_users=1, n_neighbors=1))

        pool = AsyncMock()
        pool.fetchrow = AsyncMock(return_value={"cnt": 5})
        pool.fetch = AsyncMock(return_value=[
            {"userId": "u1", "signalType": "adventure", "avg_value": 1.0},
        ])

        warm_profiles = [{"user_id": "u1", "adventure": 0.9}]
        user_profile = {"adventure": 0.8}
        prior = {"adventure": 0.5}

        result = await cf.initialize_persona(user_profile, prior, pool, warm_profiles)
        # centroid adventure = 1.0, prior adventure = 0.5
        # blend = 0.6 * 1.0 + 0.4 * 0.5 = 0.8
        assert abs(result["adventure"] - 0.8) < 1e-9

    @pytest.mark.asyncio
    async def test_inactive_returns_prior(self):
        """When < min_warm_users, return archetype_prior unchanged."""
        cf = CollabFilter(CollabFilterConfig(min_warm_users=50))
        pool = AsyncMock()
        pool.fetchrow = AsyncMock(return_value={"cnt": 10})

        prior = {"adventure": 0.7, "food": 0.3}
        result = await cf.initialize_persona({}, prior, pool)
        assert result == prior

    @pytest.mark.asyncio
    async def test_privacy_no_user_ids_in_output(self):
        """Output must contain only dimension values, never user IDs."""
        cf = CollabFilter(CollabFilterConfig(min_warm_users=1, n_neighbors=2))

        pool = AsyncMock()
        pool.fetchrow = AsyncMock(return_value={"cnt": 5})
        pool.fetch = AsyncMock(return_value=[
            {"userId": "u1", "signalType": "adventure", "avg_value": 0.8},
            {"userId": "u2", "signalType": "adventure", "avg_value": 0.6},
        ])

        warm_profiles = [
            {"user_id": "u1", "adventure": 0.9},
            {"user_id": "u2", "adventure": 0.7},
        ]
        user_profile = {"adventure": 0.8}
        prior = {"adventure": 0.5}

        result = await cf.initialize_persona(user_profile, prior, pool, warm_profiles)

        # Output should be dimension -> float, no user IDs anywhere
        for key in result:
            assert key != "user_id"
            assert not key.startswith("u")
        for val in result.values():
            assert isinstance(val, float)


# ===================================================================
# Active check
# ===================================================================


class TestIsActive:
    @pytest.mark.asyncio
    async def test_active_with_enough_users(self):
        cf = CollabFilter(CollabFilterConfig(min_warm_users=50))
        pool = AsyncMock()
        pool.fetchrow = AsyncMock(return_value={"cnt": 100})
        assert await cf.is_active(pool) is True

    @pytest.mark.asyncio
    async def test_inactive_below_threshold(self):
        cf = CollabFilter(CollabFilterConfig(min_warm_users=50))
        pool = AsyncMock()
        pool.fetchrow = AsyncMock(return_value={"cnt": 30})
        assert await cf.is_active(pool) is False

    @pytest.mark.asyncio
    async def test_inactive_none_result(self):
        cf = CollabFilter()
        pool = AsyncMock()
        pool.fetchrow = AsyncMock(return_value=None)
        assert await cf.is_active(pool) is False
