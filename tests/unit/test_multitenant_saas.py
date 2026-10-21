import asyncio
import os
import sys

from fastapi.testclient import TestClient
from sqlalchemy import select

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

from cortex_api.api_keys import authenticate_public_key
from cortex_api.db_models import TenantModel
from cortex_api.main import app

from tests.conftest import auth_headers, event_payload


def test_tenant_onboarding_and_credentials_generation(api_client, session_factory):
    headers = auth_headers(role="cortex_platform_admin", tenant_id="system")
    res = api_client.post(
        "/v1/tenants",
        headers=headers,
        json={"tenant_name": "Acme SaaS Corp", "admin_email": "admin@acme-corp.com", "plan": "pro"},
    )

    assert res.status_code == 201, res.text
    data = res.json()
    assert data["status"] == "created"
    assert data["tenant_id"].startswith("ten_")
    assert data["primary_site_id"].startswith("site_")
    assert data["public_sdk_key"].startswith("pk_live_")
    assert "operator_jwt_secret" not in data

    async def _verify_persistence():
        async with session_factory() as session:
            tenant_result = await session.execute(select(TenantModel).where(TenantModel.id == data["tenant_id"]))
            tenant = tenant_result.scalar_one()
            assert tenant.name == "Acme SaaS Corp"
            assert tenant.admin_email == "admin@acme-corp.com"
            assert tenant.plan == "pro"
            assert tenant.primary_site_id == data["primary_site_id"]

            key = await authenticate_public_key(data["public_sdk_key"], session, site_id=data["primary_site_id"])
            assert key.tenant_id == data["tenant_id"]
            assert key.site_id == data["primary_site_id"]

    asyncio.run(_verify_persistence())


def test_tenant_settings_and_branding(api_client):
    client = api_client
    res = client.get("/v1/tenant/settings", headers=auth_headers())
    assert res.status_code == 200
    data = res.json()
    assert data["plan"] == "enterprise"
    assert "branding" in data
    assert "custom_domain" in data["branding"]


def test_tenant_usage_metering_quotas(api_client, provisioned_key):
    """Metering must count what the tenant actually stored.

    This test previously asserted ``events_ingested > 0`` against a hardcoded 184500, so it
    passed with an empty database. The endpoint now meters the events table, and this test
    ingests three events and requires the counter to move by exactly three.
    """
    plaintext, tenant_id, site_id = provisioned_key
    headers = {"X-Cortex-Public-Key": plaintext}
    before = api_client.get("/v1/tenant/usage", headers=auth_headers()).json()["events_ingested"]

    for index in range(3):
        response = api_client.post(
            "/v1/events",
            json=event_payload(event_id=f"evt_meter_{index}"),
            headers=headers,
        )
        assert response.status_code == 200, response.text

    data = api_client.get("/v1/tenant/usage", headers=auth_headers()).json()
    assert data["events_ingested"] == before + 3
    assert data["active_sites"] >= 1
    assert data["monthly_limit"] > 0
    assert data["usage_pct"] == round(data["events_ingested"] / data["monthly_limit"] * 100, 4)
    assert data["plan"] == "enterprise"
    # ai_universe_calls is a real process counter: it must never be a canned 1240.
    assert data["ai_universe_calls"] == 0



def test_tenant_admin_cannot_create_tenants(api_client):
    """Tenant-local administrators must not be able to provision unrelated organizations."""
    response = api_client.post(
        "/v1/tenants",
        headers=auth_headers(role="cortex_admin", tenant_id="tenant_test"),
        json={"tenant_name": "Unauthorized Child", "admin_email": "attacker@example.com", "plan": "pro"},
    )
    assert response.status_code == 403, response.text
