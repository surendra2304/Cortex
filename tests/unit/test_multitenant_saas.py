import pytest
import os
import sys
from fastapi.testclient import TestClient

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

from nexus_api.main import app


def test_tenant_onboarding_and_credentials_generation():
    client = TestClient(app)
    res = client.post("/v1/tenants", json={
        "tenant_name": "Acme SaaS Corp",
        "admin_email": "admin@acme-corp.com",
        "plan": "pro"
    })

    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "created"
    assert "ten_" in data["tenant_id"]
    assert "site_" in data["primary_site_id"]
    assert "pk_live_" in data["public_sdk_key"]
    assert "sec_jwt_" in data["operator_jwt_secret"]


def test_tenant_settings_and_branding():
    client = TestClient(app)
    res = client.get("/v1/tenant/settings")
    assert res.status_code == 200
    data = res.json()
    assert data["plan"] == "enterprise"
    assert "branding" in data
    assert "custom_domain" in data["branding"]


def test_tenant_usage_metering_quotas():
    client = TestClient(app)
    res = client.get("/v1/tenant/usage")
    assert res.status_code == 200
    data = res.json()
    assert data["events_ingested"] > 0
    assert data["monthly_limit"] > 0
    assert data["usage_pct"] < 100.0
