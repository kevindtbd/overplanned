"""
Unit tests: Cost alerting thresholds.

Verifies:
- GET /admin/pipeline/alerts returns threshold status with spend
- PUT /admin/pipeline/alerts updates thresholds and audit-logs
- exceeded flag computed correctly
- pct_used calculated correctly
- disabled thresholds never show as exceeded
"""

import pytest
from unittest.mock import AsyncMock

from .conftest import make_cost_alert_config, make_admin_user

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# GET /admin/pipeline/alerts
# ---------------------------------------------------------------------------

class TestGetCostAlerts:
    """Read cost alert thresholds with today's spend."""

    async def test_returns_alert_status(self, admin_client, mock_prisma):
        mock_prisma.query_raw = AsyncMock(return_value=[
            {
                "pipeline_stage": "seed_enrichment",
                "daily_limit_usd": 50.0,
                "enabled": True,
                "current_spend_usd": 25.0,
            },
            {
                "pipeline_stage": "llm_narration",
                "daily_limit_usd": 100.0,
                "enabled": True,
                "current_spend_usd": 110.0,
            },
        ])

        response = await admin_client.get("/admin/pipeline/alerts")
        assert response.status_code == 200
        alerts = response.json()["data"]
        assert len(alerts) == 2

        # First alert: under limit
        seed = alerts[0]
        assert seed["pipeline_stage"] == "seed_enrichment"
        assert seed["exceeded"] is False
        assert seed["pct_used"] == 50.0

        # Second alert: over limit
        narration = alerts[1]
        assert narration["pipeline_stage"] == "llm_narration"
        assert narration["exceeded"] is True
        assert narration["pct_used"] == 110.0

    async def test_disabled_alert_never_exceeded(self, admin_client, mock_prisma):
        mock_prisma.query_raw = AsyncMock(return_value=[
            {
                "pipeline_stage": "experimental",
                "daily_limit_usd": 10.0,
                "enabled": False,
                "current_spend_usd": 999.0,
            },
        ])

        response = await admin_client.get("/admin/pipeline/alerts")
        assert response.status_code == 200
        alert = response.json()["data"][0]
        assert alert["exceeded"] is False  # disabled → never exceeded

    async def test_zero_limit_pct_used_zero(self, admin_client, mock_prisma):
        mock_prisma.query_raw = AsyncMock(return_value=[
            {
                "pipeline_stage": "free_tier",
                "daily_limit_usd": 0.0,
                "enabled": True,
                "current_spend_usd": 5.0,
            },
        ])

        response = await admin_client.get("/admin/pipeline/alerts")
        assert response.status_code == 200
        alert = response.json()["data"][0]
        assert alert["pct_used"] == 0.0  # avoid division by zero

    async def test_empty_alerts(self, admin_client, mock_prisma):
        mock_prisma.query_raw = AsyncMock(return_value=[])

        response = await admin_client.get("/admin/pipeline/alerts")
        assert response.status_code == 200
        assert response.json()["data"] == []


# ---------------------------------------------------------------------------
# PUT /admin/pipeline/alerts
# ---------------------------------------------------------------------------

class TestUpdateCostAlerts:
    """Update cost alert thresholds with audit logging."""

    async def test_update_thresholds(self, admin_client, mock_prisma):
        # Before state
        mock_prisma.query_raw = AsyncMock(return_value=[
            {"pipeline_stage": "seed_enrichment", "daily_limit_usd": 50.0, "enabled": True},
        ])

        response = await admin_client.put(
            "/admin/pipeline/alerts",
            json={
                "thresholds": [
                    {"pipeline_stage": "seed_enrichment", "daily_limit_usd": 75.0, "enabled": True},
                    {"pipeline_stage": "llm_narration", "daily_limit_usd": 200.0, "enabled": True},
                ]
            },
        )
        assert response.status_code == 200
        assert response.json()["data"]["updated"] == 2

        # Verify upserts happened
        assert mock_prisma.execute_raw.call_count == 2

    async def test_update_triggers_audit_log(self, admin_client, mock_prisma):
        mock_prisma.query_raw = AsyncMock(return_value=[])

        response = await admin_client.put(
            "/admin/pipeline/alerts",
            json={
                "thresholds": [
                    {"pipeline_stage": "seed_enrichment", "daily_limit_usd": 100.0},
                ]
            },
        )
        assert response.status_code == 200

        # Audit entry created (SA-based audit_action calls execute + commit)
        mock_prisma.execute.assert_called()
        mock_prisma.commit.assert_called()


# ---------------------------------------------------------------------------
# LLM Costs endpoint
# ---------------------------------------------------------------------------

class TestLLMCosts:
    """GET /admin/pipeline/llm-costs reads telemetry data."""

    async def test_returns_cost_summary(self, admin_client, mock_prisma):
        mock_prisma.query_raw = AsyncMock(return_value=[
            {
                "model": "claude-sonnet-4-6",
                "date": "2026-02-19",
                "pipeline_stage": "narration",
                "call_count": 150,
                "total_cost_usd": 12.50,
                "avg_latency_ms": 450.0,
                "total_input_tokens": 300000,
                "total_output_tokens": 75000,
            },
        ])

        response = await admin_client.get("/admin/pipeline/llm-costs?days=7")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total_cost_usd"] == 12.50
        assert data["total_calls"] == 150
        assert len(data["rows"]) == 1

    async def test_invalid_days_rejected(self, admin_client, mock_prisma):
        response = await admin_client.get("/admin/pipeline/llm-costs?days=0")
        assert response.status_code == 400

        response = await admin_client.get("/admin/pipeline/llm-costs?days=91")
        assert response.status_code == 400
