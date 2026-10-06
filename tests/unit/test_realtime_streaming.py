import os
import sys
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from jose import jwt

for p in [
    "packages/core/src",
    "packages/event_schema/src",
    "packages/agents/src",
    "packages/ai_universe_adapter/src",
    "packages/tool_runtime/src",
    "packages/integrations/src",
    "packages/policy_engine/src",
    "packages/workflow_engine/src",
    "packages/identity/src",
    "packages/analytics/src",
    "packages/intelligence/src",
    "packages/memory/src",
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(p))

from cortex_api.main import app
from cortex_api.streaming_router import stream_manager


def _exp():
    return datetime.now(UTC) + timedelta(minutes=5)


@pytest.mark.asyncio
async def test_streaming_manager_broadcast_and_ring_buffer():
    await stream_manager.broadcast_to_channel(
        channel="visitors",
        event_type="page_view",
        data={"visitor_id": "vis_stream_1", "path": "/pricing"},
        trace_id="trc_stream_test",
    )

    buffer = stream_manager.channel_buffers.get("visitors", [])
    assert len(buffer) > 0
    last_msg = buffer[-1]
    assert last_msg["channel"] == "visitors"
    assert last_msg["type"] == "page_view"
    assert last_msg["data"]["visitor_id"] == "vis_stream_1"
    assert last_msg["trace_id"] == "trc_stream_test"


def test_websocket_endpoint_connection_handshake():
    """The stream authenticates with a signed JWT (audit C3: `token=dev_test` removed)."""
    from cortex_api import auth as auth_module

    secret = "unit-streaming-secret"
    original_secret, original_bypass = auth_module.JWT_SECRET, auth_module.DEV_AUTH_BYPASS
    auth_module.JWT_SECRET = secret
    auth_module.DEV_AUTH_BYPASS = False
    try:
        token = jwt.encode(
            {"sub": "usr_stream", "role": "cortex_viewer", "tenant_id": "tenant_stream", "exp": _exp()},
            secret,
            algorithm="HS256",
        )
        client = TestClient(app)
        with client.websocket_connect(f"/ws/v1/live?token={token}") as websocket:
            # Drain any initial replayed messages
            websocket.send_json({"action": "ping"})
            # Read messages until we get pong
            received_types = []
            for _ in range(5):
                msg = websocket.receive_json()
                received_types.append(msg.get("type"))
                if msg.get("type") == "pong":
                    break
            assert "pong" in received_types
            assert stream_manager.tenant_subscriptions.get("tenant_stream"), "socket must be tenant-scoped"
    finally:
        auth_module.JWT_SECRET, auth_module.DEV_AUTH_BYPASS = original_secret, original_bypass
