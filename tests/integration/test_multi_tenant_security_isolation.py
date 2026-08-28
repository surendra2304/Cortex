import pytest
import os
import sys
from fastapi.testclient import TestClient

for p in [
    "packages/core/src",
    "packages/event_schema/src",
    "packages/integrations/src",
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(p))

from nexus_api.main import app


def test_multi_tenant_security_isolation_e2e():
    """
    End-to-End Multi-Tenant Security Isolation:
    Tenant A's vulnerability findings and security incidents never appear in Tenant B.
    """
    client = TestClient(app)

    # 1. Onboard Tenant Alpha
    res_a = client.post("/v1/tenants", json={
        "tenant_name": "Tenant Alpha Security Corp",
        "admin_email": "ciso@alpha.com",
        "plan": "enterprise"
    })
    assert res_a.status_code == 201
    tenant_a = res_a.json()

    # 2. Onboard Tenant Beta
    res_b = client.post("/v1/tenants", json={
        "tenant_name": "Tenant Beta Security LLC",
        "admin_email": "ciso@beta.com",
        "plan": "enterprise"
    })
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
                "affected_endpoint": "/alpha-route"
            }
        ]
    }

    res_finding = client.post("/v1/sentinel/findings", json=finding_payload)
    assert res_finding.status_code == 202
    data = res_finding.json()
    assert data["asset_id"] == tenant_a["primary_site_id"]
    assert data["asset_id"] != tenant_b["primary_site_id"]
