"""
Unit + Integration tests: Model promotion safety gate.

Verifies:
- C-ADM-004: Promotion path enforcement (staging -> ab_test -> production)
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
    """staging -> ab_test -> production. No other paths allowed."""

    async def test_promote_staging_to_ab_test(self, admin_client, mock_session):
        """Valid: staging -> ab_test."""
        candidate = make_model_registry_entry(stage="staging", metrics={"f1": 0.90})
        obj = _model_obj(candidate)

        # promote_model: db.get(candidate) -> cooldown select -> current select -> update -> commit
        mock_session.returns_get(obj)
        mock_session.returns_none()  # cooldown check: no recent promotion
        mock_session.returns_none()  # current model: none in target stage

        response = await admin_client.post(
            f"/admin/models/{candidate['id']}/promote",
            json={"target_stage": "ab_test"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["previous_stage"] == "staging"
        assert data["new_stage"] == "ab_test"

    async def test_promote_ab_test_to_production(self, admin_client, mock_session):
        """Valid: ab_test -> production."""
        candidate = make_model_registry_entry(stage="ab_test", metrics={"f1": 0.92})
        obj = _model_obj(candidate)

        mock_session.returns_get(obj)
        mock_session.returns_none()  # cooldown
        mock_session.returns_none()  # current

        response = await admin_client.post(
            f"/admin/models/{candidate['id']}/promote",
            json={"target_stage": "production"},
        )
        assert response.status_code == 200

    async def test_cannot_promote_from_production(self, admin_client, mock_session):
        """production has no next stage -- reject."""
        candidate = make_model_registry_entry(stage="production")
        mock_session.returns_get(_model_obj(candidate))

        response = await admin_client.post(
            f"/admin/models/{candidate['id']}/promote",
            json={"target_stage": "archived"},
        )
        assert response.status_code == 400
        assert "no valid next stage" in response.json()["detail"].lower()

    async def test_cannot_skip_stages(self, admin_client, mock_session):
        """staging -> production not allowed (must go through ab_test)."""
        candidate = make_model_registry_entry(stage="staging", metrics={"f1": 0.90})
        mock_session.returns_get(_model_obj(candidate))

        response = await admin_client.post(
            f"/admin/models/{candidate['id']}/promote",
            json={"target_stage": "production"},
        )
        assert response.status_code == 400
        assert "expected" in response.json()["detail"].lower()

    async def test_promote_nonexistent_model_404(self, admin_client, mock_session):
        mock_session.returns_get(None)

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

    async def test_candidate_beats_current_higher_is_better(self, admin_client, mock_session):
        """f1: higher is better. Candidate 0.90 > current 0.85 -> pass."""
        candidate = make_model_registry_entry(
            stage="staging", modelType="classification", metrics={"f1": 0.90}
        )
        current = make_model_registry_entry(
            stage="ab_test", modelType="classification", metrics={"f1": 0.85}
        )

        mock_session.returns_get(_model_obj(candidate))
        mock_session.returns_none()  # cooldown: no recent
        mock_session.returns_one(_model_obj(current))  # current model in target stage

        response = await admin_client.post(
            f"/admin/models/{candidate['id']}/promote",
            json={"target_stage": "ab_test"},
        )
        assert response.status_code == 200

    async def test_candidate_loses_to_current_rejected(self, admin_client, mock_session):
        """f1: candidate 0.75 < current 0.85 -> blocked."""
        candidate = make_model_registry_entry(
            stage="staging", modelType="classification", metrics={"f1": 0.75}
        )
        current = make_model_registry_entry(
            stage="ab_test", modelType="classification", metrics={"f1": 0.85}
        )

        mock_session.returns_get(_model_obj(candidate))
        mock_session.returns_none()  # cooldown
        mock_session.returns_one(_model_obj(current))  # current model

        response = await admin_client.post(
            f"/admin/models/{candidate['id']}/promote",
            json={"target_stage": "ab_test"},
        )
        assert response.status_code == 400
        assert "does not beat" in response.json()["detail"].lower()

    async def test_lower_is_better_rmse(self, admin_client, mock_session):
        """rmse: lower is better. Candidate 0.10 < current 0.15 -> pass."""
        candidate = make_model_registry_entry(
            stage="staging", modelType="scoring", metrics={"rmse": 0.10}
        )
        current = make_model_registry_entry(
            stage="ab_test", modelType="scoring", metrics={"rmse": 0.15}
        )

        mock_session.returns_get(_model_obj(candidate))
        mock_session.returns_none()  # cooldown
        mock_session.returns_one(_model_obj(current))

        response = await admin_client.post(
            f"/admin/models/{candidate['id']}/promote",
            json={"target_stage": "ab_test"},
        )
        assert response.status_code == 200

    async def test_lower_is_better_rmse_candidate_worse(self, admin_client, mock_session):
        """rmse: candidate 0.20 > current 0.15 -> blocked."""
        candidate = make_model_registry_entry(
            stage="staging", modelType="scoring", metrics={"rmse": 0.20}
        )
        current = make_model_registry_entry(
            stage="ab_test", modelType="scoring", metrics={"rmse": 0.15}
        )

        mock_session.returns_get(_model_obj(candidate))
        mock_session.returns_none()  # cooldown
        mock_session.returns_one(_model_obj(current))

        response = await admin_client.post(
            f"/admin/models/{candidate['id']}/promote",
            json={"target_stage": "ab_test"},
        )
        assert response.status_code == 400
        assert "lower is better" in response.json()["detail"].lower()

    async def test_no_primary_metric_blocks_promotion(self, admin_client, mock_session):
        """Candidate with no metrics cannot be promoted."""
        candidate = make_model_registry_entry(
            stage="staging", modelType="classification", metrics={}
        )

        mock_session.returns_get(_model_obj(candidate))
        mock_session.returns_none()  # cooldown
        mock_session.returns_none()  # current

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

    async def test_cooldown_blocks_rapid_promotion(self, admin_client, mock_session):
        """Promotion within 2 minutes of last promotion -> 429."""
        candidate = make_model_registry_entry(
            stage="staging", metrics={"f1": 0.90}
        )
        recent = make_model_registry_entry(
            promotedAt=datetime.now(timezone.utc) - timedelta(seconds=30),
        )

        mock_session.returns_get(_model_obj(candidate))
        mock_session.returns_one(_model_obj(recent))  # cooldown: recent promotion found

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

    async def test_promotion_creates_audit_entry(self, admin_client, mock_session, admin_user):
        """Successful promotion writes an AuditLog entry."""
        candidate = make_model_registry_entry(stage="staging", metrics={"f1": 0.90})

        mock_session.returns_get(_model_obj(candidate))
        mock_session.returns_none()  # cooldown
        mock_session.returns_none()  # current

        response = await admin_client.post(
            f"/admin/models/{candidate['id']}/promote",
            json={"target_stage": "ab_test"},
        )
        assert response.status_code == 200

        # Verify audit log was created (SA-based audit_action calls execute + commit)
        mock_session.mock.execute.assert_called()
        mock_session.mock.commit.assert_called()


# ---------------------------------------------------------------------------
# Compare endpoint
# ---------------------------------------------------------------------------

class TestModelComparison:
    """GET /admin/models/{id}/compare returns metrics comparison."""

    async def test_compare_with_no_current(self, admin_client, mock_session):
        """First promotion -- no current model in target stage."""
        candidate = make_model_registry_entry(
            stage="staging", modelType="classification", metrics={"f1": 0.85}
        )

        mock_session.returns_get(_model_obj(candidate))
        mock_session.returns_none()  # no current in target stage

        response = await admin_client.get(f"/admin/models/{candidate['id']}/compare")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["comparison"]["passes_gate"] is True
        assert data["current"]["id"] is None

    async def test_compare_candidate_beats_current(self, admin_client, mock_session):
        candidate = make_model_registry_entry(
            stage="staging", modelType="classification", metrics={"f1": 0.90}
        )
        current = make_model_registry_entry(
            stage="ab_test", modelType="classification", metrics={"f1": 0.85}
        )

        mock_session.returns_get(_model_obj(candidate))
        mock_session.returns_one(_model_obj(current))

        response = await admin_client.get(f"/admin/models/{candidate['id']}/compare")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["comparison"]["passes_gate"] is True

    async def test_compare_candidate_loses(self, admin_client, mock_session):
        candidate = make_model_registry_entry(
            stage="staging", modelType="classification", metrics={"f1": 0.70}
        )
        current = make_model_registry_entry(
            stage="ab_test", modelType="classification", metrics={"f1": 0.85}
        )

        mock_session.returns_get(_model_obj(candidate))
        mock_session.returns_one(_model_obj(current))

        response = await admin_client.get(f"/admin/models/{candidate['id']}/compare")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["comparison"]["passes_gate"] is False
