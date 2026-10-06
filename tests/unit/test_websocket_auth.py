"""Regression tests for WebSocket authentication (audit defect C3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from cortex_api import auth as auth_module
from cortex_api.main import app
from fastapi.testclient import TestClient
from jose import jwt
from starlette.websockets import WebSocketDisconnect

SECRET = "unit-test-secret-for-websocket-auth"


def _token(tenant_id: str = "tenant_live", secret: str = SECRET, **extra) -> str:
    claims = {
        "sub": "socket-user",
        "role": "cortex_viewer",
        "tenant_id": tenant_id,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    claims.update(extra)
    return jwt.encode(claims, secret, algorithm="HS256")


@pytest.fixture
def configured_secret(monkeypatch):
    monkeypatch.setattr(auth_module, "JWT_SECRET", SECRET)
    monkeypatch.setattr(auth_module, "OIDC_JWKS_URL", "")
    monkeypatch.setattr(auth_module, "DEV_AUTH_BYPASS", False)
    yield


def test_forged_token_is_rejected(configured_secret):
    """The exact exploit from Phase 2: unsigned claims must not select a tenant."""
    client = TestClient(app)
    forged = jwt.encode({"tenant_id": "tenant_live"}, "not-the-real-secret", algorithm="HS256")
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect(f"/ws/v1/live?token={forged}") as websocket:
            websocket.receive_text()
    assert excinfo.value.code == 1008


@pytest.mark.asyncio
async def test_alg_none_token_is_rejected_at_auth_layer(configured_secret):
    """An unsigned token must not authenticate even though it is validly shaped.

    Asserted directly against the auth layer (the transport level is covered by
    ``test_forged_token_is_rejected``) so the close code and reason are visible.
    """
    from cortex_api.ws_auth import WS_POLICY_VIOLATION, authenticate_websocket

    class RecordingSocket:
        def __init__(self):
            self.closed_with = None

        async def close(self, code=None, reason=None):
            self.closed_with = (code, reason)

    signed_elsewhere = jwt.encode({"tenant_id": "tenant_live"}, "attacker-secret", algorithm="HS256")
    socket = RecordingSocket()
    tenant = await authenticate_websocket(socket, signed_elsewhere)
    assert tenant is None
    assert socket.closed_with is not None
    code, reason = socket.closed_with
    assert code == WS_POLICY_VIOLATION
    assert "signature" in reason.lower()


def test_missing_token_is_rejected_in_production_mode(configured_secret):
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws/v1/live") as websocket:
            websocket.receive_text()
    assert excinfo.value.code == 1008


def test_valid_token_connects(configured_secret):
    client = TestClient(app)
    with client.websocket_connect(f"/ws/v1/live?token={_token()}") as websocket:
        websocket.send_json({"action": "ping"})
        for _ in range(6):
            message = websocket.receive_json()
            if message.get("type") == "pong":
                break
        else:  # pragma: no cover - defensive
            pytest.fail("no pong received on an authenticated socket")


def test_dev_bypass_ignores_forged_tenant_claim(monkeypatch):
    """Even under the development bypass, unverified claims never choose a tenant."""
    from cortex_api.streaming_router import stream_manager

    stream_manager.tenant_subscriptions.pop("tenant_live", None)
    stream_manager.tenant_buffers.pop("tenant_live", None)

    monkeypatch.setattr(auth_module, "JWT_SECRET", "")
    monkeypatch.setattr(auth_module, "OIDC_JWKS_URL", "")
    monkeypatch.setattr(auth_module, "DEV_AUTH_BYPASS", True)

    client = TestClient(app)
    forged = jwt.encode({"tenant_id": "tenant_live"}, "whatever", algorithm="HS256")
    with client.websocket_connect(f"/ws/v1/live?token={forged}") as websocket:
        websocket.send_json({"action": "ping"})
        for _ in range(6):
            message = websocket.receive_json()
            if message.get("type") == "pong":
                break
        else:  # pragma: no cover - defensive
            pytest.fail("no pong received")

    # The forged claim must never create tenant-scoped subscription state.
    assert "tenant_live" not in stream_manager.tenant_subscriptions
    assert "tenant_live" not in stream_manager.tenant_buffers
