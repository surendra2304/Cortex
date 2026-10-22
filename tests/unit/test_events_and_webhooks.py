import os
import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/event_schema/src"))
sys.path.insert(0, os.path.abspath("apps/api/src"))
sys.path.insert(0, os.path.abspath("apps/worker/src"))

from cortex_api.config import get_db_session, get_redis_client
from cortex_api.main import app
from cortex_core.orchestrator import Orchestrator
from cortex_worker.main import process_event
from fastapi.testclient import TestClient


def test_events_gateway_rejects_unprovisioned_public_key():
    """Regression (audit C1): an unknown public key must never be accepted.

    The previous version of this test asserted ``200 accepted`` for a key that
    no database had ever issued, which silently locked in the anonymous
    ingestion vulnerability. Verified end-to-end coverage lives in
    ``tests/unit/test_ingestion_security.py``.
    """
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=None)

    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock(return_value=True)
    mock_redis.xadd = AsyncMock(return_value="1724770000000-0")

    async def override_db():
        yield mock_db

    async def override_redis():
        return mock_redis

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_redis_client] = override_redis

    client = TestClient(app)
    payload = {
        "event_id": "evt_stream_test_1",
        "tenant_id": "tenant_live",
        "site_id": "site_live",
        "type": "checkout_intent",
        "occurred_at": datetime.now(UTC).isoformat(),
        "actor": {"type": "visitor", "id": "vis_live_456"},
        "source": "web-sdk",
        "data": {"cart_value": 249.99},
        "consent": {"analytics": True},
    }

    res = client.post("/v1/events", json=payload, headers={"X-Cortex-Public-Key": "pk_test_live"})
    assert res.status_code == 401
    assert not mock_db.add.called, "unauthenticated payload must not reach the event store"
    assert not mock_redis.xadd.called

    missing = client.post("/v1/events", json=payload)
    assert missing.status_code == 401

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_worker_process_event():
    orchestrator = Orchestrator()
    sample_payload = '{"event_id": "evt_sample_99", "tenant_id": "tenant_1", "site_id": "site_1", "type": "pricing_view", "occurred_at": "2026-08-27T10:00:00Z", "actor": {"type": "visitor", "id": "vis_99"}, "source": "web", "data": {}}'
    result = await process_event("1724770000000-0", sample_payload, orchestrator)
    assert result is not None
    assert result["status"] == "success"
