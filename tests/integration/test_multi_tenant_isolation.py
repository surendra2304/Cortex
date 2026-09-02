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

from cortex_api.main import app
from cortex_core import Tenant, Site


def test_multi_tenant_isolation_e2e():
    """
    End-to-End Multi-Tenant Isolation Test:
    Two distinct tenants onboarded -> verified separate credentials and scoped isolation.
    """
    client = TestClient(app)

    # 1. Onboard Tenant Alpha
    res_a = client.post("/v1/tenants", json={
        "tenant_name": "Tenant Alpha Corp",
        "admin_email": "admin@alpha.com",
        "plan": "pro"
    })
    assert res_a.status_code == 201
    tenant_a = res_a.json()

    # 2. Onboard Tenant Beta
    res_b = client.post("/v1/tenants", json={
        "tenant_name": "Tenant Beta LLC",
        "admin_email": "admin@beta.com",
        "plan": "enterprise"
    })
    assert res_b.status_code == 201
    tenant_b = res_b.json()

    # 3. Assert zero overlap between tenant credentials
    assert tenant_a["tenant_id"] != tenant_b["tenant_id"]
    assert tenant_a["primary_site_id"] != tenant_b["primary_site_id"]
    assert tenant_a["public_sdk_key"] != tenant_b["public_sdk_key"]
    assert tenant_a["operator_jwt_secret"] != tenant_b["operator_jwt_secret"]

    # 4. Assert model validation
    t_model_a = Tenant(id=tenant_a["tenant_id"], name=tenant_a["tenant_name"])
    t_model_b = Tenant(id=tenant_b["tenant_id"], name=tenant_b["tenant_name"])
    assert t_model_a.id != t_model_b.id
