"""Regression tests for webhook authentication.

Audit defect C2: the catch-all ``/v1/webhooks/{provider}`` gateway shadowed the
dedicated ``/v1/webhooks/stripe`` route, accepted requests with no signature
whatsoever, reported ``200 OK``, and trusted a client-supplied ``X-Tenant-ID``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

from cortex_upgrade.webhook import canonical_json


def _sign(secret: str, body: bytes, timestamp: str | None = None) -> str:
    ts = timestamp or str(int(time.time()))
    payload = f"{ts}.".encode() + body if ts else body
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


def test_stripe_path_is_not_shadowed_by_the_generic_gateway(api_client, monkeypatch):
    """The generic gateway must refuse to be the handler for 'stripe'.

    A 404 here is the gateway's explicit rejection; a 503 means the dedicated
    Stripe router handled the request and correctly refused to verify it
    without a signing secret. What must NOT happen is a 200.
    """
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("CORTEX_ALLOW_UNSIGNED_WEBHOOKS", raising=False)
    response = api_client.post("/v1/webhooks/stripe", content=b"{}", headers={"X-Cortex-Public-Key": "pk_x"})
    assert response.status_code in (404, 503)
    assert response.status_code != 200


def test_unsigned_stripe_webhook_is_rejected_by_default(api_client, monkeypatch):
    """C2: a default checkout must not accept anonymous payment webhooks."""
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("CORTEX_ALLOW_UNSIGNED_WEBHOOKS", raising=False)
    response = api_client.post("/v1/webhooks/stripe", content=b'{"type": "checkout.session.completed"}')
    assert response.status_code == 503
    assert "STRIPE_WEBHOOK_SECRET" in response.json()["detail"]


def test_unsigned_generic_webhook_is_rejected(api_client):
    payload = json.dumps({"event": "ping"})
    response = api_client.post("/v1/webhooks/github", content=payload)
    assert response.status_code == 401
    assert "X-Cortex-Public-Key" in response.json()["detail"]


def test_webhook_with_key_but_no_signature_is_rejected(api_client, provisioned_key, monkeypatch):
    plaintext, _, _ = provisioned_key
    monkeypatch.setenv("WEBHOOK_SECRET_GITHUB", "test-webhook-secret")

    payload = json.dumps({"event": "ping"})
    response = api_client.post(
        "/v1/webhooks/github",
        content=payload,
        headers={"X-Cortex-Public-Key": plaintext},
    )
    assert response.status_code == 401
    assert "signature" in response.json()["detail"].lower()


def test_forged_signature_is_rejected(api_client, provisioned_key, monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET_GITHUB", "real-secret")
    plaintext, _, _ = provisioned_key
    body = canonical_json({"event": "ping"})
    response = api_client.post(
        "/v1/webhooks/github",
        content=body,
        headers={
            "X-Cortex-Public-Key": plaintext,
            "X-Cortex-Signature": _sign("attacker-secret", body),
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 401


def test_valid_signature_is_accepted_and_reports_verification(api_client, provisioned_key, monkeypatch):
    secret = "real-secret"
    monkeypatch.setenv("WEBHOOK_SECRET_GITHUB", secret)
    monkeypatch.setenv("WEBHOOK_SIGNING_SECRET", secret)
    monkeypatch.setenv("CORTEX_WEBHOOK_SECRET", secret)
    plaintext, tenant_id, _ = provisioned_key
    body = canonical_json({"event": "ping", "tenant_id": "victim"})
    response = api_client.post(
        "/v1/webhooks/github",
        content=body,
        headers={"X-Cortex-Public-Key": plaintext, "X-Cortex-Signature": _sign(secret, body)},
    )
    assert response.status_code == 200
    assert response.json()["signature_verified"] is True
    assert response.json()["tenant_id"] == tenant_id
