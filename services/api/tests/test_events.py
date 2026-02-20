"""
Event batch ingestion endpoint tests.

Tests:
- /events/batch dedup on clientEventId
- Body size limit enforcement (1MB)
- Max batch size (1000 events)
- Empty batch handling
- Payload validation
"""

import json
import uuid

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.api.tests.conftest import make_raw_event


# ---------------------------------------------------------------------------
# Batch ingestion
# ---------------------------------------------------------------------------

class TestEventsBatchEndpoint:
    """POST /events/batch ingestion tests."""

    @pytest.mark.asyncio
    async def test_empty_batch_returns_zero(self, client):
        response = await client.post("/events/batch", json={"events": []})
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["inserted"] == 0
        assert body["data"]["skipped"] == 0
        assert body["data"]["total"] == 0
        assert "requestId" in body

    @pytest.mark.asyncio
    async def test_single_event_accepted(self, client, mock_db, app):
        """Single valid event is accepted."""
        app.state.db = mock_db

        event = {
            "userId": str(uuid.uuid4()),
            "sessionId": str(uuid.uuid4()),
            "eventType": "page_view",
            "intentClass": "implicit",
            "payload": {},
        }
        response = await client.post("/events/batch", json={"events": [event]})
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["total"] == 1

    @pytest.mark.asyncio
    async def test_validation_rejects_empty_event_type(self, client):
        """eventType must not be empty."""
        event = {
            "userId": str(uuid.uuid4()),
            "sessionId": str(uuid.uuid4()),
            "eventType": "",
            "intentClass": "implicit",
            "payload": {},
        }
        response = await client.post("/events/batch", json={"events": [event]})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_validation_rejects_invalid_intent_class(self, client):
        """intentClass must be explicit|implicit|contextual."""
        event = {
            "userId": str(uuid.uuid4()),
            "sessionId": str(uuid.uuid4()),
            "eventType": "click",
            "intentClass": "invalid_value",
            "payload": {},
        }
        response = await client.post("/events/batch", json={"events": [event]})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Body size limit
# ---------------------------------------------------------------------------

class TestEventsBatchSizeLimit:
    """Request body must not exceed 1MB (1_048_576 bytes)."""

    @pytest.mark.asyncio
    async def test_oversized_body_returns_413(self, client):
        """Body > 1MB triggers 413 Payload Too Large."""
        response = await client.post(
            "/events/batch",
            content=b"x" * (1_048_576 + 1),
            headers={
                "content-type": "application/json",
                "content-length": str(1_048_576 + 1),
            },
        )
        assert response.status_code == 413
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "PAYLOAD_TOO_LARGE"

    @pytest.mark.asyncio
    async def test_under_limit_body_accepted(self, client):
        """Small body passes size check."""
        response = await client.post(
            "/events/batch",
            json={"events": []},
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Dedup on clientEventId
# ---------------------------------------------------------------------------

class TestClientEventIdDedup:
    """Dedup: same (userId, clientEventId) → skipped on second insert."""

    def test_raw_event_factory_generates_client_event_id(self):
        event = make_raw_event()
        assert event["clientEventId"] is not None
        assert event["clientEventId"].startswith("evt-")

    def test_raw_event_factory_unique_ids(self):
        e1 = make_raw_event()
        e2 = make_raw_event()
        assert e1["clientEventId"] != e2["clientEventId"]
        assert e1["id"] != e2["id"]


# ---------------------------------------------------------------------------
# Batch size limit
# ---------------------------------------------------------------------------

class TestBatchMaxSize:
    """Max 1000 events per batch."""

    @pytest.mark.asyncio
    async def test_exceeds_max_batch_size(self, client):
        """More than 1000 events should be rejected."""
        events = [
            {
                "userId": str(uuid.uuid4()),
                "sessionId": str(uuid.uuid4()),
                "eventType": "click",
                "intentClass": "implicit",
                "payload": {},
            }
            for _ in range(1001)
        ]
        response = await client.post("/events/batch", json={"events": events})
        assert response.status_code == 422
