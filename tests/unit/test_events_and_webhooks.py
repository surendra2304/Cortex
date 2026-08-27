import os
import sys
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/event_schema/src"))
sys.path.insert(0, os.path.abspath("apps/api/src"))
sys.path.insert(0, os.path.abspath("apps/worker/src"))

from fastapi.testclient import TestClient
from nexus_api.main import app
from nexus_api.config import get_db_session, get_redis_client
from nexus_worker.main import process_event


def test_events_gateway_with_db_and_redis_mocks():
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()

    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()
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
        "occurred_at": datetime.utcnow().isoformat(),
        "actor": {"type": "visitor", "id": "vis_live_456"},
        "source": "web-sdk",
        "data": {"cart_value": 249.99}
    }

    res = client.post("/v1/events", json=payload, headers={"X-Nexus-Public-Key": "pk_test_live"})
    assert res.status_code == 200
    assert res.json()["status"] == "accepted"
    assert res.json()["event_id"] == "evt_stream_test_1"

    # Verify DB insertion call
    assert mock_db.add.called
    assert mock_db.commit.called

    # Verify Redis rate limit & stream push call
    assert mock_redis.incr.called
    assert mock_redis.xadd.called

    # Clean up overrides
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_worker_process_event():
    sample_payload = '{"type": "pricing_view", "tenant_id": "tenant_1", "site_id": "site_1"}'
    # Test worker parser execution without exception
    await process_event("1724770000000-0", sample_payload)
