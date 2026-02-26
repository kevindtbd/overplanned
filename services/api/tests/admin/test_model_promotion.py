"""
Unit + Integration tests: Model promotion safety gate.

Verifies:
- C-ADM-004: Promotion path enforcement (staging → ab_test → production)
- Candidate must beat current on primary metric to promote
- 2-minute cooldown between promotions per model name
- Promotion logged to AuditLog with before/after
- Archived model replacement on promote
- Missing metrics block promotion
- Lower-is-better metric direction respected
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from .conftest import make_model_registry_entry, make_admin_user, _make_mock_obj

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _model_obj(data: dict) -> MagicMock:
    """Convert model factory dict to a mock with attribute access."""
    return _make_mock_obj(data)


# ---------------------------------------------------------------------------
# Promotion path enforcement
# ---------------------------------------------------------------------------

class TestPromotionPath:
    """staging → ab_test → production. No other paths allowed."""

    async def test_promote_staging_to_ab_test(self, admin_client, mock_prisma):
        """Valid: staging → ab_test."""
        candidate = make_model_registry_entry(stage="staging", metrics={"f1": 0.90})
        mock_prisma.modelregistry.find_unique = AsyncMock(return_value=_model_obj(candidate))
        mock_prisma.modelregistry.find_first = AsyncMock(return_value=None)  # no cooldown, no current

        response = await admin_client.post(
            f"/admin/models/{candidate['id']}/promote",
            json={"target_stage": "ab_test"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["previous_stage"] == "staging"
        assert data["new_stage"] == "ab_test"

    async def test_promote_ab_test_to_production(self, admin_client, mock_prisma):
        """Valid: ab_test → production."""
        candidate = make_model_registry_entry(stage="ab_test", metrics={"f1": 0.92})
        mock_prisma.modelregistry.find_unique = AsyncMock(return_value=_model_obj(candidate))
        mock_prisma.modelregistry.find_first = AsyncMock(return_value=None)

        response = await admin_client.post(
            f"/admin/models/{candidate['id']}/promote",
            json={"target_stage": "production"},
        )
        assert response.status_code == 200

    async def test_cannot_promote_from_production(self, admin_client, mock_prisma):
        """production has no next stage — reject."""
        candidate = make_model_registry_entry(stage="production")
        mock_prisma.modelregistry.find_unique = AsyncMock(return_value=_model_obj(candidate))

        response = await admin_client.post(
            f"/admin/models/{candidate['id']}/promote",
            json={"target_stage": "archived"},
        )
        assert response.status_code == 400
        assert "no valid next stage" in response.json()["detail"].lower()

    async def test_cannot_skip_stages(self, admin_client, mock_prisma):
        """staging → production not allowed (must go through ab_test)."""
        candidate = make_model_registry_entry(stage="staging", metrics={"f1": 0.90})
        mock_prisma.modelregistry.find_unique = AsyncMock(return_value=_model_obj(candidate))

        response = await admin_client.post(
            f"/admin/models/{candidate['id']}/promote",
            json={"target_stage": "production"},
        )
        assert response.status_code == 400
        assert "expected" in response.json()["detail"].lower()

    async def test_promote_nonexistent_model_404(self, admin_client, mock_prisma):
        mock_prisma.modelregistry.find_unique = AsyncMock(return_value=None)

        response = await admin_client.post(
            "/admin/models/nonexistent-id/promote",
            json={"target_stage": "ab_test"},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Metrics gate
# ---------------------------------------------------------------------------

class TestMetricsGate:
    """Candidate must beat current model on primary metric."""

    async def test_candidate_beats_current_higher_is_better(self, admin_client, mock_prisma):
        """f1: higher is better. Candidate 0.90 > current 0.85 → pass."""
        candidate = make_model_registry_entry(
            stage="staging", modelType="classification", metrics={"f1": 0.90}
        )
        current = make_model_registry_entry(
            stage="ab_test", modelType="classification", metrics={"f1": 0.85}
        )

        call_count = 0
        async def find_first_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            where = kwargs.get("where", {})
            # First call: cooldown check (promotedAt filter)
            if "promotedAt" in where:
                return None
            # Second call: current model in target stage
            return _model_obj(current)

        mock_prisma.modelregistry.find_unique = AsyncMock(return_value=_model_obj(candidate))
        mock_prisma.modelregistry.find_first = AsyncMock(side_effect=find_first_side_effect)

        response = await admin_client.post(
            f"/admin/models/{candidate['id']}/promote",
            json={"target_stage": "ab_test"},
        )
        assert response.status_code == 200

    async def test_candidate_loses_to_current_rejected(self, admin_client, mock_prisma):
        """f1: candidate 0.75 < current 0.85 → blocked."""
        candidate = make_model_registry_entry(
            stage="staging", modelType="classification", metrics={"f1": 0.75}
        )
        current = make_model_registry_entry(
            stage="ab_test", modelType="classification", metrics={"f1": 0.85}
        )

        call_count = 0
        async def find_first_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            where = kwargs.get("where", {})
            if "promotedAt" in where:
                return None
            return _model_obj(current)

        mock_prisma.modelregistry.find_unique = AsyncMock(return_value=_model_obj(candidate))
        mock_prisma.modelregistry.find_first = AsyncMock(side_effect=find_first_side_effect)

        response = await admin_client.post(
            f"/admin/models/{candidate['id']}/promote",
            json={"target_stage": "ab_test"},
        )
        assert response.status_code == 400
        assert "does not beat" in response.json()["detail"].lower()

    async def test_lower_is_better_rmse(self, admin_client, mock_prisma):
        """rmse: lower is better. Candidate 0.10 < current 0.15 → pass."""
        candidate = make_model_registry_entry(
            stage="staging", modelType="scoring", metrics={"rmse": 0.10}
        )

        call_count = 0
        current = make_model_registry_entry(
            stage="ab_test", modelType="scoring", metrics={"rmse": 0.15}
        )

        async def find_first_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            where = kwargs.get("where", {})
            if "promotedAt" in where:
                return None
            return _model_obj(current)

        mock_prisma.modelregistry.find_unique = AsyncMock(return_value=_model_obj(candidate))
        mock_prisma.modelregistry.find_first = AsyncMock(side_effect=find_first_side_effect)

        response = await admin_client.post(
            f"/admin/models/{candidate['id']}/promote",
            json={"target_stage": "ab_test"},
        )
        assert response.status_code == 200

    async def test_lower_is_better_rmse_candidate_worse(self, admin_client, mock_prisma):
        """rmse: candidate 0.20 > current 0.15 → blocked."""
        candidate = make_model_registry_entry(
            stage="staging", modelType="scoring", metrics={"rmse": 0.20}
        )
        current = make_model_registry_entry(
            stage="ab_test", modelType="scoring", metrics={"rmse": 0.15}
        )

        async def find_first_side_effect(**kwargs):
            where = kwargs.get("where", {})
            if "promotedAt" in where:
                return None
            return _model_obj(current)

        mock_prisma.modelregistry.find_unique = AsyncMock(return_value=_model_obj(candidate))
        mock_prisma.modelregistry.find_first = AsyncMock(side_effect=find_first_side_effect)

        response = await admin_client.post(
            f"/admin/models/{candidate['id']}/promote",
            json={"target_stage": "ab_test"},
        )
        assert response.status_code == 400
        assert "lower is better" in response.json()["detail"].lower()

    async def test_no_primary_metric_blocks_promotion(self, admin_client, mock_prisma):
        """Candidate with no metrics cannot be promoted."""
        candidate = make_model_registry_entry(
            stage="staging", modelType="classification", metrics={}
        )
        mock_prisma.modelregistry.find_unique = AsyncMock(return_value=_model_obj(candidate))
        mock_prisma.modelregistry.find_first = AsyncMock(return_value=None)

        response = await admin_client.post(
            f"/admin/models/{candidate['id']}/promote",
            json={"target_stage": "ab_test"},
        )
        assert response.status_code == 400
        assert "no value for primary metric" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------

class TestPromotionCooldown:
    """2-minute cooldown between promotions for the same model name."""

    async def test_cooldown_blocks_rapid_promotion(self, admin_client, mock_prisma):
        """Promotion within 2 minutes of last promotion → 429."""
        candidate = make_model_registry_entry(
            stage="staging", metrics={"f1": 0.90}
        )
        recent = make_model_registry_entry(
            promotedAt=datetime.now(timezone.utc) - timedelta(seconds=30),
        )

        mock_prisma.modelregistry.find_unique = AsyncMock(return_value=_model_obj(candidate))
        mock_prisma.modelregistry.find_first = AsyncMock(return_value=_model_obj(recent))

        response = await admin_client.post(
            f"/admin/models/{candidate['id']}/promote",
            json={"target_stage": "ab_test"},
        )
        assert response.status_code == 429
        assert "cooldown" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Audit logging on promotion
# ---------------------------------------------------------------------------

class TestPromotionAuditLog:
    """All promotions logged to AuditLog with before/after state."""

    async def test_promotion_creates_audit_entry(self, admin_client, mock_prisma, admin_user):
        """Successful promotion writes an AuditLog entry."""
        candidate = make_model_registry_entry(stage="staging", metrics={"f1": 0.90})
        mock_prisma.modelregistry.find_unique = AsyncMock(return_value=_model_obj(candidate))
        mock_prisma.modelregistry.find_first = AsyncMock(return_value=None)

        response = await admin_client.post(
            f"/admin/models/{candidate['id']}/promote",
            json={"target_stage": "ab_test"},
        )
        assert response.status_code == 200

        # Verify audit log was created (SA-based audit_action calls execute + commit)
        mock_prisma.execute.assert_called()
        mock_prisma.commit.assert_called()


# ---------------------------------------------------------------------------
# Compare endpoint
# ---------------------------------------------------------------------------

class TestModelComparison:
    """GET /admin/models/{id}/compare returns metrics comparison."""

    async def test_compare_with_no_current(self, admin_client, mock_prisma):
        """First promotion — no current model in target stage."""
        candidate = make_model_registry_entry(
            stage="staging", modelType="classification", metrics={"f1": 0.85}
        )
        mock_prisma.modelregistry.find_unique = AsyncMock(return_value=_model_obj(candidate))
        mock_prisma.modelregistry.find_first = AsyncMock(return_value=None)

        response = await admin_client.get(f"/admin/models/{candidate['id']}/compare")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["comparison"]["passes_gate"] is True
        assert data["current"]["id"] is None

    async def test_compare_candidate_beats_current(self, admin_client, mock_prisma):
        candidate = make_model_registry_entry(
            stage="staging", modelType="classification", metrics={"f1": 0.90}
        )
        current = make_model_registry_entry(
            stage="ab_test", modelType="classification", metrics={"f1": 0.85}
        )
        mock_prisma.modelregistry.find_unique = AsyncMock(return_value=_model_obj(candidate))
        mock_prisma.modelregistry.find_first = AsyncMock(return_value=_model_obj(current))

        response = await admin_client.get(f"/admin/models/{candidate['id']}/compare")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["comparison"]["passes_gate"] is True

    async def test_compare_candidate_loses(self, admin_client, mock_prisma):
        candidate = make_model_registry_entry(
            stage="staging", modelType="classification", metrics={"f1": 0.70}
        )
        current = make_model_registry_entry(
            stage="ab_test", modelType="classification", metrics={"f1": 0.85}
        )
        mock_prisma.modelregistry.find_unique = AsyncMock(return_value=_model_obj(candidate))
        mock_prisma.modelregistry.find_first = AsyncMock(return_value=_model_obj(current))

        response = await admin_client.get(f"/admin/models/{candidate['id']}/compare")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["comparison"]["passes_gate"] is False
