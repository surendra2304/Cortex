"""
Cryptographic Outbound Webhook Dispatcher & Resilient Sync Queue for Cortex.

Provides production-grade outbound webhook delivery with HMAC-SHA256 signatures,
timestamp replay prevention (RFC 2104 / Stripe-style headers), exponential backoff retries,
jittered delays, and Dead-Letter Queue escalation for exhausted attempts.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import random
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any
import httpx
from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


logger = logging.getLogger("cortex-webhook-dispatcher")


class WebhookDeliveryStatus(str, Enum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    RETRYING = "RETRYING"
    DEAD_LETTERED = "DEAD_LETTERED"
    FAILED = "FAILED"


class WebhookDeliveryReceipt(BaseModel):
    delivery_id: str
    tenant_id: str
    endpoint_url: str
    event_type: str
    status: WebhookDeliveryStatus
    attempt_count: int
    http_status: int | None = None
    signature_header: str
    timestamp_header: str
    response_snippet: str | None = None
    error_message: str | None = None
    dispatched_at: str
    completed_at: str | None = None


class CryptographicWebhookDispatcher:
    """
    Signs and delivers outbound webhooks with cryptographic authenticity and replay defense.
    """

    def __init__(self, default_timeout_seconds: float = 8.0):
        self.default_timeout_seconds = default_timeout_seconds
        self.delivery_history: list[WebhookDeliveryReceipt] = []

    def compute_signature(self, secret: str, payload_bytes: bytes, timestamp_str: str) -> str:
        """
        Signs the timestamped payload using HMAC-SHA256.
        Signed string: f"{timestamp_str}.{payload_bytes.decode('utf-8')}"
        Output header value: f"t={timestamp_str},v1={hex_digest}"
        """
        payload_text = payload_bytes.decode("utf-8")
        signed_payload = f"{timestamp_str}.{payload_text}".encode("utf-8")
        mac = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        return f"t={timestamp_str},v1={mac}"

    def verify_signature(
        self,
        secret: str,
        payload_bytes: bytes,
        signature_header: str,
        tolerance_seconds: float = 300.0,
        now: datetime | None = None,
    ) -> bool:
        """
        Verifies received webhook signature and guards against clock skew / replay attacks.
        """
        now = now or _utcnow()
        try:
            parts = dict(kv.split("=", 1) for kv in signature_header.split(","))
            t_str = parts.get("t")
            v1_sig = parts.get("v1")
            if not t_str or not v1_sig:
                return False

            # Verify timestamp within tolerance
            ts = int(t_str)
            current_ts = int(now.timestamp())
            if abs(current_ts - ts) > tolerance_seconds:
                return False

            expected_sig = self.compute_signature(secret, payload_bytes, t_str)
            expected_v1 = expected_sig.split("v1=")[1]
            return hmac.compare_digest(v1_sig, expected_v1)
        except Exception:
            return False

    async def dispatch(
        self,
        endpoint_url: str,
        event_type: str,
        payload_data: dict[str, Any],
        secret: str,
        tenant_id: str = "default",
        max_retries: int = 3,
        backoff_base_seconds: float = 0.5,
        client: httpx.AsyncClient | None = None,
    ) -> WebhookDeliveryReceipt:
        """
        Asynchronously dispatches a webhook with HMAC-SHA256 authentication and retry loop.
        """
        # Strict tenant isolation check
        data_tenant = payload_data.get("tenant_id")
        if data_tenant and data_tenant != tenant_id:
            raise PermissionError(
                f"Tenant isolation mismatch: payload tenant '{data_tenant}' != target tenant '{tenant_id}'."
            )

        delivery_id = f"wh_{uuid.uuid4().hex[:12]}"
        now = _utcnow()
        timestamp_str = str(int(now.timestamp()))

        canonical_body = {
            "id": delivery_id,
            "event": event_type,
            "tenant_id": tenant_id,
            "data": payload_data,
            "dispatched_at": now.isoformat(),
        }
        body_bytes = json.dumps(canonical_body, sort_keys=True).encode("utf-8")
        signature_header = self.compute_signature(secret, body_bytes, timestamp_str)

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Cortex-Webhook-Dispatcher/2.0",
            "X-Cortex-Delivery-Id": delivery_id,
            "X-Cortex-Timestamp": timestamp_str,
            "X-Cortex-Signature": signature_header,
            "X-Cortex-Tenant-Id": tenant_id,
        }

        attempts = 0
        status = WebhookDeliveryStatus.PENDING
        last_status_code = None
        last_error = None
        response_snippet = None

        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.default_timeout_seconds)
            close_client = True

        try:
            for attempt in range(1, max_retries + 1):
                attempts = attempt
                try:
                    resp = await client.post(endpoint_url, content=body_bytes, headers=headers)
                    last_status_code = resp.status_code
                    response_snippet = resp.text[:200] if resp.text else None

                    if 200 <= resp.status_code < 300:
                        status = WebhookDeliveryStatus.DELIVERED
                        last_error = None
                        break
                    elif resp.status_code in (429, 500, 502, 503, 504):
                        # Transient failures eligible for retry
                        status = WebhookDeliveryStatus.RETRYING
                        last_error = f"HTTP {resp.status_code}: {resp.reason_phrase}"
                    else:
                        # Client error (e.g. 400, 401, 403, 404) - non-retryable
                        status = WebhookDeliveryStatus.FAILED
                        last_error = f"HTTP {resp.status_code}: {resp.reason_phrase}"
                        break
                except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
                    status = WebhookDeliveryStatus.RETRYING
                    last_error = f"{type(exc).__name__}: {str(exc)}"

                # Exponential backoff with jitter if another attempt remains
                if attempt < max_retries and status == WebhookDeliveryStatus.RETRYING:
                    jitter = random.uniform(0.8, 1.2)
                    sleep_time = (backoff_base_seconds * (2 ** (attempt - 1))) * jitter
                    await asyncio.sleep(min(sleep_time, 5.0))

            # If all retries exhausted without success, designate DEAD_LETTERED
            if status == WebhookDeliveryStatus.RETRYING:
                status = WebhookDeliveryStatus.DEAD_LETTERED

        finally:
            if close_client:
                await client.aclose()

        completed_at = _utcnow().isoformat()
        receipt = WebhookDeliveryReceipt(
            delivery_id=delivery_id,
            tenant_id=tenant_id,
            endpoint_url=endpoint_url,
            event_type=event_type,
            status=status,
            attempt_count=attempts,
            http_status=last_status_code,
            signature_header=signature_header,
            timestamp_header=timestamp_str,
            response_snippet=response_snippet,
            error_message=last_error,
            dispatched_at=now.isoformat(),
            completed_at=completed_at,
        )

        self.delivery_history.append(receipt)
        if len(self.delivery_history) > 500:
            self.delivery_history = self.delivery_history[-500:]

        return receipt
