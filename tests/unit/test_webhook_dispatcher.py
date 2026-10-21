"""
Unit tests for Cryptographic Webhook Dispatcher and Resilient Delivery Queue.
"""

from datetime import UTC, datetime, timedelta
import httpx
import pytest
import respx
from cortex_integrations.webhook_dispatcher import (
    CryptographicWebhookDispatcher,
    WebhookDeliveryReceipt,
    WebhookDeliveryStatus,
)


def test_signature_computation_and_verification():
    dispatcher = CryptographicWebhookDispatcher()
    secret = "whsec_super_secret_test_key_12345678"
    payload = b'{"event":"test","value":42}'
    now = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)
    t_str = str(int(now.timestamp()))

    sig_header = dispatcher.compute_signature(secret, payload, t_str)
    assert sig_header.startswith(f"t={t_str},v1=")

    # Valid verification
    is_valid = dispatcher.verify_signature(secret, payload, sig_header, tolerance_seconds=300.0, now=now)
    assert is_valid is True

    # Tampered payload rejected
    tampered_payload = b'{"event":"test","value":99}'
    assert dispatcher.verify_signature(secret, tampered_payload, sig_header, now=now) is False

    # Expired timestamp rejected (> 300s clock skew)
    future_now = now + timedelta(seconds=350)
    assert dispatcher.verify_signature(secret, payload, sig_header, tolerance_seconds=300.0, now=future_now) is False


@pytest.mark.asyncio
async def test_dispatch_successful_delivery():
    dispatcher = CryptographicWebhookDispatcher()
    target_url = "https://crm.partner.io/cortex/webhooks"
    secret = "whsec_live_test_secret_key_8888"

    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://crm.partner.io") as respx_mock:
            respx_mock.post("/cortex/webhooks").respond(status_code=200, text='{"received":true}')

            receipt = await dispatcher.dispatch(
                endpoint_url=target_url,
                event_type="lead.qualified",
                payload_data={"lead_id": "ld_999", "score": 0.95},
                secret=secret,
                tenant_id="tenant_acme",
                client=client,
            )

            assert isinstance(receipt, WebhookDeliveryReceipt)
            assert receipt.status == WebhookDeliveryStatus.DELIVERED
            assert receipt.http_status == 200
            assert receipt.attempt_count == 1
            assert receipt.tenant_id == "tenant_acme"
            assert "v1=" in str(receipt.signature_header)


@pytest.mark.asyncio
async def test_dispatch_retry_and_dead_letter():
    dispatcher = CryptographicWebhookDispatcher()
    target_url = "https://unstable.service.io/hook"
    secret = "whsec_test_retry_secret"

    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://unstable.service.io") as respx_mock:
            # Simulate continuous 503 Service Unavailable
            respx_mock.post("/hook").respond(status_code=503, text="Service Unavailable")

            receipt = await dispatcher.dispatch(
                endpoint_url=target_url,
                event_type="incident.triggered",
                payload_data={"incident_id": "inc_001"},
                secret=secret,
                tenant_id="tenant_acme",
                max_retries=2,
                backoff_base_seconds=0.01,  # fast test
                client=client,
            )

            assert receipt.status == WebhookDeliveryStatus.DEAD_LETTERED
            assert receipt.attempt_count == 2
            assert receipt.http_status == 503
            assert "HTTP 503" in (receipt.error_message or "")


@pytest.mark.asyncio
async def test_dispatch_cross_tenant_mismatch():
    dispatcher = CryptographicWebhookDispatcher()
    with pytest.raises(PermissionError, match="Tenant isolation mismatch"):
        await dispatcher.dispatch(
            endpoint_url="https://any.io",
            event_type="test",
            payload_data={"tenant_id": "tenant_wrong"},
            secret="whsec_123",
            tenant_id="tenant_correct",
        )
