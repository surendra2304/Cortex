"""Regression tests for webhook authentication (audit defect C2).

Phase 2 demonstrated that the catch-all ``/v1/webhooks/{provider}`` route was
registered before the dedicated Stripe router, so it swallowed Stripe traffic:
a POST with a bogus ``Stripe-Signature`` returned ``200 OK``, and the tenant was
taken from the client-supplied ``X-Tenant-ID`` header.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from cortex_api.api_keys import generate_api_key, hash_api_key
from cortex_api.db_models import ApiKeyModel

from tests.conftest import auth_headers


async def _provision_key(session_factory, tenant_id: str = "tenant_hook", site_id: str = "site_hook") -> str:
    plaintext = generate_api_key()
    async with session_factory() as session:
        session.add(
            ApiKeyModel(
                id=f"key_{tenant_id}",
                tenant_id=tenant_id,
                site_id=site_id,
                key_hash=hash_api_key(plaintext),
                key_prefix=plaintext[:12],
                name="webhook-test",
                is_active=True,
            )
        )
        await session.commit()
    return plaintext


def _stripe_signature(payload: bytes, secret: str) -> str:
    timestamp = str(int(time.time()))
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


@pytest.fixture
def stripe_secret(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
    monkeypatch.setenv("CORTEX_ALLOW_UNSIGNED_WEBHOOKS", "false")
    return "whsec_test_secret"


def test_stripe_route_is_not_shadowed_by_the_catch_all(api_client, stripe_secret):
    """The dedicated Stripe handler must own /v1/webhooks/stripe."""
    body = json.dumps({"id": "evt_x", "type": "checkout.session.completed", "created": int(time.time())}).encode()
    forged = _stripe_signature(body, "wrong-secret")
    response = api_client.post(
        "/v1/webhooks/stripe",
        content=body,
        headers={"Stripe-Signature": forged, "X-Tenant-ID": "victim_corp"},
    )
    # The generic gateway would answer 200 with {"status": "received"}; the Stripe
    # handler rejects the bad signature instead.
    assert response.status_code == 400
    assert "signature" in response.json()["detail"].lower()


def test_stripe_webhook_rejects_unsigned_request_when_secret_configured(api_client, stripe_secret):
    body = json.dumps({"id": "evt_y", "type": "checkout.session.completed"}).encode()
    response = api_client.post("/v1/webhooks/stripe", content=body)
    assert response.status_code == 400
    assert "Stripe-Signature" in response.json()["detail"]


def test_generic_webhook_requires_public_key(api_client):
    response = api_client.post("/v1/webhooks/github", json={"action": "opened"})
    assert response.status_code == 401
    assert "X-Cortex-Public-Key" in response.json()["detail"]


def test_generic_webhook_requires_signature_once_key_is_present(api_client, session_factory, monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET_GITHUB", "gh-secret")
    key = _provision_public_key(api_client, session_factory)
    response = api_client.post(
        "/v1/webhooks/github",
        json={"action": "opened"},
        headers={"X-Cortex-Public-Key": key},
    )
    assert response.status_code == 401
    assert "signature" in response.json()["detail"].lower()


def test_generic_webhook_accepts_valid_signature_and_ignores_tenant_header(api_client, session_factory, monkeypatch):
    secret = "gh-secret"
    monkeypatch.setenv("WEBHOOK_SECRET_GITHUB", secret)
    key = _provision_public_key(api_client, session_factory)

    body = json.dumps({"action": "opened"}).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    response = api_client.post(
        "/v1/webhooks/github",
        content=body,
        headers={
            "X-Cortex-Public-Key": key,
            "X-Cortex-Signature": signature,
            "X-Tenant-ID": "victim_corp",  # must be ignored
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 200
    body_json = response.json()
    assert body_json.get("tenant_id") == "tenant_test"
    assert body_json.get("signature_verified") is True


def _provision_public_key(api_client, session_factory) -> str:
    """Provision a key through the admin API (exercises the real provisioning path)."""
    response = api_client.post(
        "/v1/api-keys",
        json={"site_id": "site_hook", "name": "webhook-test"},
        headers=auth_headers(role="cortex_admin", tenant_id="tenant_test"),
    )
    assert response.status_code == 201, response.text
    return response.json()["api_key"]
