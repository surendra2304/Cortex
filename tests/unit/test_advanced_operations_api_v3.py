"""
Unit and integration tests for Advanced Operations API v3 endpoints:
- GET /v1/feature-flags
- POST /v1/feature-flags
- POST /v1/feature-flags/evaluate
- DELETE /v1/feature-flags/{key}
- GET /v1/intelligence/audiences
- POST /v1/intelligence/audiences
- POST /v1/intelligence/audiences/{segment_id}/evaluate
- POST /v1/intelligence/audiences/{segment_id}/export
- POST /v1/incidents/remediate
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import jwt
import pytest
from cortex_api import auth as auth_module
from cortex_api.auth import Role
from fastapi.testclient import TestClient

SECRET = "unit-test-secret-at-least-32-bytes-long!!"


def _auth_headers(role: Role = Role.CORTEX_ADMIN, tenant_id: str = "tenant_adv_v3") -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": "tester_v3",
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


def test_feature_flags_api_lifecycle(api_client: TestClient):
    # 1. Create flag (Admin required)
    create_payload = {
        "key": "api_v3_feature",
        "enabled": True,
        "rollout_percentage": 100.0,
        "description": "API v3 Feature Flag",
        "target_rules": [{"property": "tier", "operator": "eq", "values": ["VIP"]}],
    }
    resp = api_client.post(
        "/v1/feature-flags",
        json=create_payload,
        headers=_auth_headers(Role.CORTEX_ADMIN),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["key"] == "api_v3_feature"
    assert data["enabled"] is True

    # 2. Viewer cannot create (403)
    resp_viewer = api_client.post(
        "/v1/feature-flags",
        json=create_payload,
        headers=_auth_headers(Role.CORTEX_VIEWER),
    )
    assert resp_viewer.status_code == 403

    # 3. List flags
    resp_list = api_client.get("/v1/feature-flags", headers=_auth_headers(Role.CORTEX_VIEWER))
    assert resp_list.status_code == 200
    list_data = resp_list.json()
    assert any(f["key"] == "api_v3_feature" for f in list_data["flags"])

    # 4. Evaluate flag
    eval_resp = api_client.post(
        "/v1/feature-flags/evaluate",
        json={"key": "api_v3_feature", "actor_id": "u_vip", "context": {"tier": "VIP"}},
        headers=_auth_headers(Role.CORTEX_VIEWER),
    )
    assert eval_resp.status_code == 200
    assert eval_resp.json()["enabled"] is True

    # 5. Delete flag
    del_resp = api_client.delete(
        "/v1/feature-flags/api_v3_feature",
        headers=_auth_headers(Role.CORTEX_ADMIN),
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"


def test_audience_segments_api_lifecycle(api_client: TestClient):
    # 1. Create segment
    create_payload = {
        "name": "High Lead Score",
        "rules": [{"field": "score", "operator": "gte", "value": 0.85}],
        "match_policy": "ALL",
        "description": "High intent enterprise leads",
    }
    resp = api_client.post(
        "/v1/intelligence/audiences",
        json=create_payload,
        headers=_auth_headers(Role.CORTEX_OPERATOR),
    )
    assert resp.status_code == 200
    seg = resp.json()
    seg_id = seg["id"]
    assert seg_id.startswith("seg_")

    # 2. Evaluate segment
    profiles = [
        {"id": "p1", "score": 0.90, "primary_email": "top@corp.com", "tenant_id": "tenant_adv_v3"},
        {"id": "p2", "score": 0.50, "primary_email": "low@corp.com", "tenant_id": "tenant_adv_v3"},
    ]
    eval_resp = api_client.post(
        f"/v1/intelligence/audiences/{seg_id}/evaluate",
        json={"profiles": profiles},
        headers=_auth_headers(Role.CORTEX_VIEWER),
    )
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert eval_data["matching_profiles_count"] == 1
    assert eval_data["matching_profile_ids"] == ["p1"]

    # 3. Export segment
    export_resp = api_client.post(
        f"/v1/intelligence/audiences/{seg_id}/export",
        json={"matching_profiles": [profiles[0]], "destination": "hubspot"},
        headers=_auth_headers(Role.CORTEX_OPERATOR),
    )
    assert export_resp.status_code == 200
    export_data = export_resp.json()
    assert export_data["destination"] == "hubspot"
    assert export_data["count"] == 1
    assert export_data["payloads"][0]["email"] == "top@corp.com"


def test_incidents_remediation_api(api_client: TestClient):
    payload = {
        "incident_id": "inc_api_001",
        "incident_type": "EXCESSIVE_5XX",
        "severity": "HIGH",
        "context": {"service": "cortex-core"},
    }
    resp = api_client.post(
        "/v1/incidents/remediate",
        json=payload,
        headers=_auth_headers(Role.CORTEX_OPERATOR),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["incident_id"] == "inc_api_001"
    assert data["status"] == "COMPLETED"
    assert len(data["steps"]) >= 2
    assert len(data["hmac_signature"]) == 64
