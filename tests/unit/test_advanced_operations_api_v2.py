"""
Unit and integration tests for Advanced Operations API v2 endpoints:
- POST /v1/analytics/paths/sankey
- GET /v1/analytics/retention/matrix
- POST /v1/intelligence/churn/predict
- POST /v1/intelligence/rfm/segment
- POST /v1/identity/graph/stitch
- POST /v1/identity/gdpr/cascade-forget
- POST /v1/integrations/webhooks/dispatch
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
import respx
from cortex_api import auth as auth_module
from cortex_api.auth import Role
from cortex_api.main import app
from fastapi.testclient import TestClient

SECRET = "unit-test-secret-at-least-32-bytes-long!!"


def _auth_headers(role: Role = Role.CORTEX_ADMIN, tenant_id: str = "tenant_advanced_v2") -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": "user_v2_tester",
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


def test_sankey_path_endpoint(api_client: TestClient):
    resp = api_client.post(
        "/v1/analytics/paths/sankey",
        json={"max_path_length": 5, "lookback_days": 15},
        headers=_auth_headers(Role.CORTEX_VIEWER),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "links" in data
    assert "top_paths" in data
    assert "drop_off_points" in data
    assert "total_sessions_analyzed" in data


def test_retention_matrix_endpoint(api_client: TestClient):
    resp = api_client.get(
        "/v1/analytics/retention/matrix?horizons=0,1,3,7&lookback_days=30",
        headers=_auth_headers(Role.CORTEX_VIEWER),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "cohorts" in data
    assert "horizons" in data
    assert data["horizons"] == [0, 1, 3, 7]
    assert "average_retention" in data


def test_churn_predict_endpoint(api_client: TestClient):
    resp = api_client.post(
        "/v1/intelligence/churn/predict",
        json={"actor_id": "actor_test_99", "lookback_days": 30},
        headers=_auth_headers(Role.CORTEX_VIEWER),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["actor_id"] == "actor_test_99"
    assert "churn_probability" in data
    assert "risk_level" in data
    assert "risk_factors" in data


def test_rfm_segment_endpoint(api_client: TestClient):
    actors_payload = [
        {
            "actor_id": "c1",
            "last_seen_at": datetime.now(UTC).isoformat(),
            "frequency": 25,
            "monetary_value": 1200.0,
        },
        {
            "actor_id": "c2",
            "last_seen_at": (datetime.now(UTC) - timedelta(days=40)).isoformat(),
            "frequency": 2,
            "monetary_value": 50.0,
        },
    ]
    resp = api_client.post(
        "/v1/intelligence/rfm/segment",
        json={"actors_data": actors_payload},
        headers=_auth_headers(Role.CORTEX_VIEWER),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_profiles_scored"] == 2
    assert len(data["profiles"]) == 2
    assert data["profiles"][0]["tier"] in ("CHAMPION", "LOYAL_CUSTOMER", "POTENTIAL_LOYALIST")


def test_identity_stitch_and_gdpr_endpoints(api_client: TestClient):
    # 1. Stitch identities (Operator role required)
    stitch_payload = {
        "node_a_id": "vis_api_1",
        "node_a_type": "visitor_id",
        "node_b_id": "user_api@example.com",
        "node_b_type": "email",
        "confidence": 0.95,
        "metadata": {"browser": "Chrome"},
    }
    resp = api_client.post(
        "/v1/identity/graph/stitch",
        json=stitch_payload,
        headers=_auth_headers(Role.CORTEX_OPERATOR),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_nodes"] == 2
    assert data["primary_email"] == "user_api@example.com"
    assert data["confidence_score"] == 0.95

    # 2. Viewer role forbidden on stitch
    resp_forbidden = api_client.post(
        "/v1/identity/graph/stitch",
        json=stitch_payload,
        headers=_auth_headers(Role.CORTEX_VIEWER),
    )
    assert resp_forbidden.status_code == 403

    # 3. GDPR Cascade Forget (Admin role required)
    forget_payload = {
        "target_identifier": "user_api@example.com",
        "reason": "GDPR Article 17 request",
    }
    resp_forget = api_client.post(
        "/v1/identity/gdpr/cascade-forget",
        json=forget_payload,
        headers=_auth_headers(Role.CORTEX_ADMIN),
    )
    assert resp_forget.status_code == 200
    forget_data = resp_forget.json()
    assert forget_data["target_identifier"] == "user_api@example.com"
    assert forget_data["anonymized_node_count"] == 2
    assert len(forget_data["compliance_hash"]) == 64


def test_webhook_dispatch_endpoint(api_client: TestClient):
    target_url = "https://partner-gateway.io/cortex/webhooks"
    with respx.mock(base_url="https://partner-gateway.io") as respx_mock:
        respx_mock.post("/cortex/webhooks").respond(status_code=200, text='{"ok":true}')

        payload = {
            "endpoint_url": target_url,
            "event_type": "lead.qualified",
            "payload_data": {"lead_id": "ld_api_1", "score": 0.92},
            "webhook_secret": "whsec_api_test_secret_12345",
            "max_retries": 1,
        }
        resp = api_client.post(
            "/v1/integrations/webhooks/dispatch",
            json=payload,
            headers=_auth_headers(Role.CORTEX_OPERATOR),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "DELIVERED"
        assert data["http_status"] == 200
        assert "t=" in data["signature_header"]
