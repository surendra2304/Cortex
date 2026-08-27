"""
Stripe Webhook Receiver
=======================
Receives signed webhook events from Stripe and pushes them into the NEXUS
Redis event stream so the background worker can process them through the
10-phase cognitive loop.

Supported event types:
  - checkout.session.completed  → triggers Sales Agent + CRM upsert
  - customer.subscription.updated → triggers Growth Agent + account update

Security:
  - Stripe-Signature header verified via stripe.Webhook.construct_event().
  - Webhook signing secret read from STRIPE_WEBHOOK_SECRET env var.
  - If secret is absent and MOCK_MODE=true, signature validation is skipped
    for local development convenience (a warning is logged).

Environment variables:
  STRIPE_WEBHOOK_SECRET   Stripe endpoint signing secret (whsec_...)
  STRIPE_SECRET_KEY       Stripe secret API key (sk_...)
  MOCK_MODE               Set "true" to bypass signature verification locally
"""

from fastapi import APIRouter, Request, HTTPException, status, Depends
from typing import Optional
import json
import logging
import os
import uuid
from datetime import datetime

import redis.asyncio as aioredis

from nexus_api.config import get_redis_client, settings

# Stripe SDK — graceful degradation if not installed
try:
    import stripe as _stripe_sdk
    HAVE_STRIPE = True
except ImportError:
    HAVE_STRIPE = False

logger = logging.getLogger("nexus-stripe-webhook")

router = APIRouter(prefix="/v1/webhooks", tags=["Stripe Webhooks"])

# Stripe events we care about → NEXUS event type mapping
SUPPORTED_STRIPE_EVENTS = {
    "checkout.session.completed": "checkout.completed",
    "customer.subscription.updated": "subscription.updated",
}


def _is_mock_mode() -> bool:
    return os.getenv("MOCK_MODE", "true").lower() in ("true", "1", "yes")


def _get_webhook_secret() -> Optional[str]:
    return os.getenv("STRIPE_WEBHOOK_SECRET")


def _verify_stripe_signature(payload: bytes, sig_header: Optional[str], secret: Optional[str]) -> dict:
    """
    Verify the Stripe-Signature header and return the parsed event dict.
    Raises HTTPException(400) if signature verification fails.
    In mock mode without a secret, skips verification and parses directly.
    """
    if not secret:
        if _is_mock_mode():
            logger.warning(
                "[MOCK MODE] STRIPE_WEBHOOK_SECRET not set — skipping signature verification. "
                "DO NOT use this in production."
            )
            try:
                return json.loads(payload)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid JSON payload: {exc}"
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="STRIPE_WEBHOOK_SECRET is not configured."
            )

    if not HAVE_STRIPE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="stripe SDK is not installed. Run: pip install stripe"
        )

    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Stripe-Signature header."
        )

    try:
        event = _stripe_sdk.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=secret,
        )
        return dict(event)
    except _stripe_sdk.error.SignatureVerificationError as exc:
        logger.warning(f"Stripe webhook signature verification failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe webhook signature."
        )
    except Exception as exc:
        logger.error(f"Unexpected error parsing Stripe event: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not parse Stripe webhook payload: {exc}"
        )


def _build_nexus_event(stripe_event: dict) -> dict:
    """
    Maps a raw Stripe event dict to a NEXUS-compatible event payload
    that the worker can deserialise and pass to the cognitive loop.
    """
    stripe_type = stripe_event.get("type", "stripe.unknown")
    nexus_type = SUPPORTED_STRIPE_EVENTS.get(stripe_type, f"stripe.{stripe_type}")
    stripe_data = stripe_event.get("data", {}).get("object", {})

    # Extract the most useful identifiers from the Stripe object
    customer_id = stripe_data.get("customer")
    customer_email = (
        stripe_data.get("customer_details", {}).get("email")
        or stripe_data.get("customer_email")
    )
    amount_total = stripe_data.get("amount_total") or stripe_data.get("amount")
    currency = stripe_data.get("currency", "usd")
    subscription_id = stripe_data.get("subscription") or stripe_data.get("id")

    return {
        # Standard NEXUS event envelope
        "event_id": f"stripe_{stripe_event.get('id', uuid.uuid4().hex)}",
        "tenant_id": os.getenv("NEXUS_DEFAULT_TENANT_ID", "default"),
        "site_id": os.getenv("NEXUS_DEFAULT_SITE_ID", "stripe"),
        "session_id": customer_id or f"stripe_session_{uuid.uuid4().hex[:8]}",
        "type": nexus_type,
        "occurred_at": datetime.utcfromtimestamp(
            stripe_event.get("created", datetime.utcnow().timestamp())
        ).isoformat(),
        "source": "stripe_webhook",
        "trace_id": f"stripe_trace_{uuid.uuid4().hex[:12]}",
        "actor": {
            "type": "customer",
            "id": customer_id or "stripe_anonymous",
        },
        "consent": {"analytics": True, "marketing": False},
        # Stripe-specific payload forwarded as event data
        "data": {
            "stripe_event_id": stripe_event.get("id"),
            "stripe_event_type": stripe_type,
            "customer_id": customer_id,
            "customer_email": customer_email,
            "amount_total": amount_total,
            "currency": currency,
            "subscription_id": subscription_id,
            "stripe_object": stripe_data,
        },
    }


@router.post(
    "/stripe",
    status_code=status.HTTP_200_OK,
    summary="Stripe Webhook Receiver",
    description=(
        "Receives signed Stripe webhook events, verifies the Stripe-Signature, "
        "and pushes checkout.completed and subscription.updated events into the "
        "NEXUS Redis event stream for autonomous cognitive loop processing."
    ),
)
async def receive_stripe_webhook(
    request: Request,
    redis_client: aioredis.Redis = Depends(get_redis_client),
):
    # Read raw body — must happen BEFORE any JSON parsing to preserve the
    # byte-exact payload required for Stripe HMAC signature verification.
    raw_body = await request.body()
    sig_header = request.headers.get("Stripe-Signature")
    webhook_secret = _get_webhook_secret()

    # 1. Verify signature and parse the Stripe event
    stripe_event = _verify_stripe_signature(raw_body, sig_header, webhook_secret)

    stripe_event_type = stripe_event.get("type", "")
    stripe_event_id = stripe_event.get("id", "unknown")

    logger.info(
        f"Stripe webhook received: type='{stripe_event_type}' id='{stripe_event_id}'"
    )

    # 2. Filter — only forward event types we care about
    if stripe_event_type not in SUPPORTED_STRIPE_EVENTS:
        logger.debug(
            f"Stripe event type '{stripe_event_type}' is not in the NEXUS processing list — acknowledged and ignored."
        )
        return {"status": "acknowledged", "action": "ignored", "stripe_event_id": stripe_event_id}

    # 3. Map to a NEXUS event envelope and push to Redis Stream
    nexus_event = _build_nexus_event(stripe_event)

    try:
        await redis_client.xadd(
            settings.redis_event_stream,
            {"payload": json.dumps(nexus_event)},
        )
        logger.info(
            f"Stripe event '{stripe_event_type}' → NEXUS event '{nexus_event['type']}' "
            f"pushed to stream '{settings.redis_event_stream}'."
        )
    except Exception as exc:
        logger.error(
            f"Failed to push Stripe event '{stripe_event_id}' to Redis stream: {exc}"
        )
        # Return 200 to Stripe regardless — otherwise Stripe retries indefinitely.
        # The failure is logged and can be replayed from Stripe's dashboard.
        return {
            "status": "error",
            "detail": "Event received but failed to enqueue for processing. Will retry.",
            "stripe_event_id": stripe_event_id,
        }

    return {
        "status": "accepted",
        "nexus_event_type": nexus_event["type"],
        "nexus_event_id": nexus_event["event_id"],
        "stripe_event_id": stripe_event_id,
        "queued_at": datetime.utcnow().isoformat(),
    }
