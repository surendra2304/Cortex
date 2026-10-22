"""
Unit tests for Authenticated Server-Sent Events (SSE) Live Telemetry Stream.
"""

from datetime import UTC, datetime, timedelta
import json
import jwt
import pytest
from cortex_api import auth as auth_module
from cortex_api.main import app
from cortex_api.streaming_router import stream_manager
from fastapi.testclient import TestClient

SECRET = "unit-test-secret-at-least-32-bytes-long!!"


def _auth_token(tenant_id: str = "tenant_sse_test") -> str:
    return jwt.encode(
        {
            "sub": "sse_tester",
            "role": "cortex_viewer",
            "tenant_id": tenant_id,
            "exp": datetime.now(UTC) + timedelta(minutes=10),
        },
        SECRET,
        algorithm="HS256",
    )


@pytest.fixture(autouse=True)
def configure_auth(monkeypatch):
    monkeypatch.setattr(auth_module, "JWT_SECRET", SECRET)
    monkeypatch.setattr(auth_module, "DEV_AUTH_BYPASS", False)


def test_sse_stream_unauthorized():
    client = TestClient(app)
    resp = client.get("/v1/stream/sse")
    assert resp.status_code == 401


def test_sse_stream_connection_and_broadcast():
    client = TestClient(app)
    token = _auth_token(tenant_id="tenant_sse_acme")

    # Connect with token query parameter and bounded events
    response = client.get(f"/v1/stream/sse?token={token}&max_events=1")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "event: connection" in response.text
    assert "tenant_sse_acme" in response.text


@pytest.mark.asyncio
async def test_sse_stream_manager_broadcast_isolation():
    tenant_a = "tenant_stream_a"
    tenant_b = "tenant_stream_b"

    # Subscribe SSE queues
    q_a = stream_manager.subscribe_sse(tenant_a, {"events"})
    q_b = stream_manager.subscribe_sse(tenant_b, {"events"})

    try:
        # Broadcast event to tenant_a
        await stream_manager.broadcast_to_channel(
            channel="events",
            event_type="conversion",
            data={"order_id": "ord_100"},
            tenant_id=tenant_a,
        )

        # q_a should receive message
        assert not q_a.empty()
        msg_a = q_a.get_nowait()
        assert msg_a["tenant_id"] == tenant_a
        assert msg_a["data"]["order_id"] == "ord_100"

        # q_b must remain completely empty (zero cross-tenant leak)
        assert q_b.empty()
    finally:
        stream_manager.unsubscribe_sse(tenant_a, q_a)
        stream_manager.unsubscribe_sse(tenant_b, q_b)
