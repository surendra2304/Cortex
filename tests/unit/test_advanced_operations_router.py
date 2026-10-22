"""Unit and integration tests for the Advanced Operations Router (cortex_api.advanced_operations_router)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cortex_api import auth as auth_module
from cortex_api.auth import Role
from cortex_api.main import app
from cortex_upgrade.dlq import global_dlq
from cortex_upgrade.models import FailureKind
from fastapi.testclient import TestClient

SECRET = "unit-test-secret-at-least-32-bytes-long!!"


def _auth_headers(role: Role = Role.CORTEX_ADMIN, tenant_id: str = "tenant_test") -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": "user_tester",
            "role": role.value,
            "tenant_id": tenant_id,
            "exp": datetime.now(UTC) + timedelta(minutes=10),
        },
        SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def configure_auth(monkeypatch):
    monkeypatch.setattr(auth_module, "JWT_SECRET", SECRET)
    monkeypatch.setattr(auth_module, "OIDC_JWKS_URL", "")
    monkeypatch.setattr(auth_module, "DEV_AUTH_BYPASS", False)


def test_canary_status_and_advance_endpoints():
    client = TestClient(app)

    # 1. Status (viewer allowed)
    resp = client.get(
        "/v1/canary/status?deployment_id=deploy_canary_test",
        headers=_auth_headers(Role.CORTEX_VIEWER),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["deployment_id"] == "deploy_canary_test"
    assert data["current_stage"] == "0%"

    # 2. Advance without admin role -> 403 Forbidden
    resp_forbidden = client.post(
        "/v1/canary/advance",
        json={"deployment_id": "deploy_canary_test"},
        headers=_auth_headers(Role.CORTEX_VIEWER),
    )
    assert resp_forbidden.status_code == 403

    # 3. Advance with admin role -> 200 OK
    resp_adv = client.post(
        "/v1/canary/advance",
        json={"deployment_id": "deploy_canary_test"},
        headers=_auth_headers(Role.CORTEX_ADMIN),
    )
    assert resp_adv.status_code == 200
    adv_data = resp_adv.json()
    assert adv_data["ok"] is True
    assert adv_data["state"]["current_stage"] == "5%"

    # 4. Rollback
    resp_rb = client.post(
        "/v1/canary/rollback",
        json={"deployment_id": "deploy_canary_test", "reason": "Test rollback"},
        headers=_auth_headers(Role.CORTEX_ADMIN),
    )
    assert resp_rb.status_code == 200
    rb_data = resp_rb.json()
    assert rb_data["ok"] is True
    assert rb_data["transition"]["to_stage"] == "0%"


@pytest.mark.asyncio
async def test_dlq_endpoints_with_tenant_isolation():
    client = TestClient(app)

    # Quarantine messages for tenant_alpha and tenant_beta
    msg_a = await global_dlq.quarantine(
        stream_id="stream_a_1",
        tenant_id="tenant_alpha",
        payload={"bad": "alpha"},
        failure_kind=FailureKind.INVALID,
        error_details="Bad schema",
    )
    msg_b = await global_dlq.quarantine(
        stream_id="stream_b_1",
        tenant_id="tenant_beta",
        payload={"bad": "beta"},
        failure_kind=FailureKind.TIMEOUT,
        error_details="Timeout",
    )

    # 1. Listing for tenant_alpha
    resp_a = client.get(
        "/v1/dlq/messages",
        headers=_auth_headers(Role.CORTEX_OPERATOR, tenant_id="tenant_alpha"),
    )
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert data_a["tenant_id"] == "tenant_alpha"
    msg_ids_a = [m["message_id"] for m in data_a["messages"]]
    assert msg_a.message_id in msg_ids_a
    assert msg_b.message_id not in msg_ids_a  # Must NOT leak tenant_beta!

    # 2. Metrics for tenant_alpha
    resp_m = client.get(
        "/v1/dlq/metrics",
        headers=_auth_headers(Role.CORTEX_OPERATOR, tenant_id="tenant_alpha"),
    )
    assert resp_m.status_code == 200
    assert resp_m.json()["tenant_id"] == "tenant_alpha"

    # 3. Cross-tenant replay attempt -> 404 Not Found
    resp_cross_replay = client.post(
        f"/v1/dlq/replay/{msg_b.message_id}",
        headers=_auth_headers(Role.CORTEX_ADMIN, tenant_id="tenant_alpha"),
    )
    assert resp_cross_replay.status_code == 404

    # 4. Same-tenant replay -> 200 OK
    resp_replay = client.post(
        f"/v1/dlq/replay/{msg_a.message_id}",
        headers=_auth_headers(Role.CORTEX_ADMIN, tenant_id="tenant_alpha"),
    )
    assert resp_replay.status_code == 200
    assert resp_replay.json()["ok"] is True

    # 5. Same-tenant purge -> 200 OK
    resp_purge = client.delete(
        f"/v1/dlq/messages/{msg_a.message_id}",
        headers=_auth_headers(Role.CORTEX_ADMIN, tenant_id="tenant_alpha"),
    )
    assert resp_purge.status_code == 200
    assert resp_purge.json()["status"] == "purged"


def test_attribution_endpoint(api_client):
    client = api_client

    # Request attribution report
    resp = client.get(
        "/v1/analytics/multi-touch-attribution?model=linear&lookback_days=14",
        headers=_auth_headers(Role.CORTEX_VIEWER, tenant_id="tenant_test"),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["tenant_id"] == "tenant_test"
    assert data["model"] == "linear"
    assert "report" in data


def test_experiment_promote_endpoint():
    client = TestClient(app)

    resp = client.post(
        "/v1/experiments/promote",
        json={"experiment_id": "exp_hero_v3", "winning_variant": "variant_dark"},
        headers=_auth_headers(Role.CORTEX_ADMIN, tenant_id="tenant_test"),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in {"promoted", "concluded"}
    assert data["winning_variant"] == "variant_dark"
