"""Security hardening regression locks (2026-10-07 upgrade).

- S5: API-key provisioning is tenant-bound — an admin cannot mint ingestion
  keys for a tenant they do not belong to.
- S6: the development auth bypass is opt-in (CORTEX_DEV_AUTH_BYPASS=true);
  MOCK_MODE no longer implies unauthenticated admin.
- S7: unsigned webhooks are refused unless a signing secret is configured or
  the explicit development bypass is active.
"""

from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.abspath("apps/api/src"))
sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/event_schema/src"))
sys.path.insert(0, os.path.abspath("packages/agents/src"))
sys.path.insert(0, os.path.abspath("packages/ai_universe_adapter/src"))
sys.path.insert(0, os.path.abspath("packages/tool_runtime/src"))
sys.path.insert(0, os.path.abspath("packages/integrations/src"))
sys.path.insert(0, os.path.abspath("packages/policy_engine/src"))
sys.path.insert(0, os.path.abspath("packages/identity/src"))
sys.path.insert(0, os.path.abspath("packages/analytics/src"))
sys.path.insert(0, os.path.abspath("packages/intelligence/src"))
sys.path.insert(0, os.path.abspath("packages/memory/src"))

from tests.conftest import auth_headers

# ── S5: tenant-bound key provisioning ────────────────────────────────────────


def test_api_key_provisioning_is_tenant_bound(api_client):
    own = auth_headers(role="cortex_admin", tenant_id="tenant_test")
    other = auth_headers(role="cortex_admin", tenant_id="tenant_other")

    # Same tenant: allowed.
    res = api_client.post(
        "/v1/api-keys", json={"tenant_id": "tenant_test", "site_id": "site_test", "name": "own"}, headers=own
    )
    assert res.status_code == 201, res.text

    # Cross-tenant: refused — the caller's tenant wins over the body.
    res = api_client.post(
        "/v1/api-keys", json={"tenant_id": "tenant_other", "site_id": "site_test", "name": "cross"}, headers=own
    )
    assert res.status_code == 403
    assert "tenant_other" in res.json()["detail"]

    # The other tenant's admin still cannot use OUR tenant id.
    res = api_client.post(
        "/v1/api-keys", json={"tenant_id": "tenant_test", "site_id": "site_test", "name": "cross2"}, headers=other
    )
    assert res.status_code == 403


# ── S6: dev auth bypass is opt-in ────────────────────────────────────────────


def _bypass_value(env: dict) -> str:
    """Evaluate the bypass decision in a clean subprocess (import-time logic)."""
    code = "from cortex_api.auth import DEV_AUTH_BYPASS; print(DEV_AUTH_BYPASS)"
    full_env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": os.pathsep.join(
            [
                os.path.abspath("apps/api/src"),
                os.path.abspath("packages/core/src"),
                os.path.abspath("packages/event_schema/src"),
                os.path.abspath("packages/agents/src"),
                os.path.abspath("packages/ai_universe_adapter/src"),
                os.path.abspath("packages/tool_runtime/src"),
                os.path.abspath("packages/integrations/src"),
                os.path.abspath("packages/policy_engine/src"),
                os.path.abspath("packages/identity/src"),
                os.path.abspath("packages/analytics/src"),
                os.path.abspath("packages/intelligence/src"),
                os.path.abspath("packages/memory/src"),
                os.path.abspath("packages/workflow_engine/src"),
                os.path.abspath("cortex_upgrade"),
            ]
        ),
        "APP_ENV": "development",
    }
    full_env.update(env)
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=full_env, cwd=os.getcwd(), timeout=60
    )
    assert out.returncode == 0, out.stderr[-500:]
    return out.stdout.strip()


def test_dev_bypass_defaults_to_off_without_the_flag():
    # MOCK_MODE=true (the historical default) must NOT enable the bypass.
    assert _bypass_value({"MOCK_MODE": "true"}) == "False"
    assert _bypass_value({}) == "False"


def test_dev_bypass_opt_in_flag_enables_it():
    assert _bypass_value({"CORTEX_DEV_AUTH_BYPASS": "true"}) == "True"


def test_dev_bypass_never_active_in_production():
    assert _bypass_value({"CORTEX_DEV_AUTH_BYPASS": "true", "APP_ENV": "production"}) == "False"


# ── S7: unsigned webhooks fail closed outside an explicit dev box ────────────


def test_unsigned_webhook_refused_without_secret_or_bypass(api_client, provisioned_key, monkeypatch):
    import cortex_api.webhooks_router as wh

    plaintext, tenant_id, site_id = provisioned_key
    monkeypatch.setattr(wh, "provider_secret", lambda provider: None)
    monkeypatch.setattr(wh, "DEV_AUTH_BYPASS", False)

    res = api_client.post(
        "/v1/webhooks/shopify",
        json={"event": "order.created", "customer_id": "cust_1"},
        headers={"X-Cortex-Public-Key": plaintext, "X-Site-ID": site_id},
    )
    assert res.status_code == 503
    assert "refusing unsigned webhooks" in res.json()["detail"]


def test_unsigned_webhook_accepted_only_with_explicit_dev_bypass(api_client, provisioned_key, monkeypatch):
    import cortex_api.webhooks_router as wh

    plaintext, tenant_id, site_id = provisioned_key
    monkeypatch.setattr(wh, "provider_secret", lambda provider: None)
    monkeypatch.setattr(wh, "DEV_AUTH_BYPASS", True)

    res = api_client.post(
        "/v1/webhooks/shopify",
        json={"event": "order.created", "customer_id": "cust_1"},
        headers={"X-Cortex-Public-Key": plaintext, "X-Site-ID": site_id},
    )
    assert res.status_code in (200, 202), res.text
    assert res.json()["signature_verified"] is False  # honest: never pretends
