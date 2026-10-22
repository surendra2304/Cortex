import os
import sys


for p in [
    "packages/core/src",
    "packages/event_schema/src",
    "packages/integrations/src",
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(p))

from cortex_api.main import app

from tests.conftest import auth_headers, friday_headers


def test_multi_tenant_security_isolation_e2e(monkeypatch, api_client):
    """
    End-to-End Multi-Tenant Security Isolation:
    Tenant A's vulnerability findings and security incidents never appear in Tenant B.
    """
    client = api_client

    # 1. Onboard Tenant Alpha
    res_a = client.post(
        "/v1/tenants",
        headers=auth_headers(role="cortex_platform_admin", tenant_id="system"),
        json={"tenant_name": "Tenant Alpha Security Corp", "admin_email": "ciso@alpha.com", "plan": "enterprise"},
    )
    assert res_a.status_code == 201
    tenant_a = res_a.json()

    # 2. Onboard Tenant Beta
    res_b = client.post(
        "/v1/tenants",
        headers=auth_headers(role="cortex_platform_admin", tenant_id="system"),
        json={"tenant_name": "Tenant Beta Security LLC", "admin_email": "ciso@beta.com", "plan": "enterprise"},
    )
    assert res_b.status_code == 201
    tenant_b = res_b.json()

    # 3. Ingest finding scoped to Tenant Alpha's asset
    finding_payload = {
        "sentinel_task_id": "task_tenant_iso_01",
        "asset_id": tenant_a["primary_site_id"],
        "posture_score": 85.0,
        "findings": [
            {
                "finding_id": "find_alpha_01",
                "severity": "high",
                "title": "Alpha Specific Finding",
                "description": "Finding belonging strictly to Tenant Alpha.",
                "attack_vector": "api",
                "affected_endpoint": "/alpha-route",
            }
        ],
    }

    res_finding = client.post("/v1/sentinel/findings", headers=friday_headers(monkeypatch), json=finding_payload)
    assert res_finding.status_code == 202
    data = res_finding.json()
    assert data["asset_id"] == tenant_a["primary_site_id"]
    assert data["asset_id"] != tenant_b["primary_site_id"]

    read_a = client.get(
        "/v1/sentinel/findings",
        headers=auth_headers(role="cortex_viewer", tenant_id=tenant_a["tenant_id"]),
    )
    read_b = client.get(
        "/v1/sentinel/findings",
        headers=auth_headers(role="cortex_viewer", tenant_id=tenant_b["tenant_id"]),
    )
    assert read_a.status_code == 200, read_a.text
    assert any(item["finding_id"] == "find_alpha_01" for item in read_a.json()["findings"])
    assert read_b.status_code == 200, read_b.text
    assert all(item["finding_id"] != "find_alpha_01" for item in read_b.json()["findings"])

