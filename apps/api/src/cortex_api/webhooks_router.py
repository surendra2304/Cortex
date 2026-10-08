"""Inbound webhook gateway (CRM, email, ticketing, custom providers).

Security contract (audit defects C2/H1):

* Every webhook must present a valid ``X-Cortex-Public-Key``; the tenant is
  taken from that credential and never from client-supplied headers.
* The raw body must carry a valid HMAC-SHA256 ``X-Cortex-Signature`` computed
  with the provider secret (``WEBHOOK_SECRET_<PROVIDER>`` or
  ``CORTEX_WEBHOOK_SECRET``).  When no secret is configured the gateway fails
  closed in production and, in development, accepts the payload but reports
  ``signature_verified: false`` — it never pretends verification happened.
* ``/v1/webhooks/stripe`` is owned by ``stripe_webhook_router``; this catch-all
  refuses to shadow it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
from cortex_event_schema import Actor, ActorType, EventSchema
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from cortex_api.api_keys import authenticate_public_key
from cortex_api.auth import DEV_AUTH_BYPASS
from cortex_api.config import get_db_session, get_redis_client, settings
from cortex_api.db_models import EventModel
from cortex_upgrade.webhook import canonical_json, verify_timestamp

logger = logging.getLogger("cortex-webhooks")
router = APIRouter(prefix="/v1/webhooks", tags=["Webhooks"])


def provider_secret(provider: str) -> str | None:
    """Resolve the signing secret for a provider, most specific first."""
    env_name = f"WEBHOOK_SECRET_{provider.upper().replace('-', '_')}"
    return os.getenv(env_name) or settings.webhook_signing_secret


def is_production() -> bool:
    return settings.app_env == "production" or os.getenv("RENDER", "").lower() in {"1", "true", "yes"}


def _verify_signature(raw_body: bytes, signature: str | None, secret: str) -> bool:
    """Verify a provider signature in any of the formats CORTEX accepts.

    Supported shapes:

    * ``<hex-digest>``          — plain HMAC-SHA256 of the raw body
    * ``sha256=<hex-digest>``   — GitHub style
    * ``t=<unix>,v1=<hex>``     — Stripe style, HMAC over ``"<t>.<body>"`` with a
      replay window enforced by :func:`verify_timestamp`

    Returns ``False`` for anything malformed; callers must treat that as
    unauthenticated. (Audit defect C2: the previous implementation split on the
    first ``=``, so a Stripe-style header was compared against its own
    timestamp and could never verify.)
    """
    if not signature:
        return False

    candidate = signature.strip()

    # Stripe / timestamped scheme: t=<unix>,v1=<hex>[,v1=<hex>...]
    if candidate.startswith("t=") or ",v1=" in candidate or candidate.startswith("v1="):
        parts: dict[str, str] = {}
        for component in candidate.split(","):
            key, _, value = component.partition("=")
            parts[key.strip()] = value.strip()
        timestamp = parts.get("t")
        digest = parts.get("v1")
        if not digest:
            return False
        if timestamp:
            try:
                skew = verify_timestamp(int(timestamp), int(time.time()))
            except ValueError:
                return False
            if not skew.ok:
                return False
            signed_payload = f"{timestamp}.".encode() + raw_body
        else:
            signed_payload = raw_body
        supplied = digest.removeprefix("sha256=")
    elif "=" in candidate:  # e.g. "sha256=<hex>"
        supplied = candidate.split("=", 1)[1]
        signed_payload = raw_body
    else:
        supplied = candidate
        signed_payload = raw_body

    return hmac.compare_digest(supplied, hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest())


@router.post("/{provider}")
async def receive_webhook(
    provider: str,
    request: Request,
    x_cortex_public_key: str | None = Header(None, alias="X-Cortex-Public-Key"),
    x_cortex_signature: str | None = Header(None, alias="X-Cortex-Signature"),
    x_site_id: str | None = Header(None, alias="X-Site-ID"),
    db: AsyncSession = Depends(get_db_session),
    redis_client: aioredis.Redis = Depends(get_redis_client),
):
    if provider.lower() == "stripe":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stripe webhooks are handled by the dedicated signed endpoint at /v1/webhooks/stripe.",
        )

    raw_body = await request.body()
    try:
        payload: dict[str, Any] = json.loads(raw_body or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid JSON payload: {exc}") from exc
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty webhook payload received")

    # 1. Credential-bound tenant identity.
    api_key_record = await authenticate_public_key(x_cortex_public_key, db, site_id=x_site_id)
    tenant_id = api_key_record.tenant_id
    site_id = x_site_id or api_key_record.site_id

    # 2. Authenticity of the body.
    secret = provider_secret(provider)
    signature_verified = False
    if secret:
        if not _verify_signature(raw_body, x_cortex_signature, secret):
            logger.warning("Rejected webhook from provider '%s': invalid signature.", provider)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature.")
        signature_verified = True
    elif is_production() or not DEV_AUTH_BYPASS:
        # Fail closed anywhere except an explicitly-flagged development box
        # (audit S7, fixed 2026-10-07): a staging deployment with APP_ENV unset is
        # not a dev box and must not accept unsigned webhooks.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"No signing secret configured for provider '{provider}'; refusing unsigned webhooks "
                f"({'production' if is_production() else 'development auth bypass not enabled'})."
            ),
        )
    else:
        logger.warning(
            "Webhook provider '%s' has no signing secret configured; accepted WITHOUT signature verification "
            "(explicit development bypass active).",
            provider,
        )

    event_type = payload.get("event") or payload.get("type") or f"{provider}.webhook_received"
    actor_id = payload.get("customer_id") or payload.get("user_id") or payload.get("email") or f"{provider}_system"
    event_id = f"evt_wh_{uuid.uuid4().hex[:12]}"
    occurred_at = datetime.now(UTC)

    server_event = EventSchema(
        event_id=event_id,
        tenant_id=tenant_id,
        site_id=site_id,
        type=event_type,
        occurred_at=occurred_at,
        actor=Actor(
            type=ActorType.USER if ("user" in str(actor_id) or "@" in str(actor_id)) else ActorType.SYSTEM,
            id=str(actor_id),
        ),
        source=f"webhook:{provider}",
        data={
            "payload": payload,
            "_provider": provider,
            "_signature_verified": signature_verified,
            "_client_ip": request.client.host if request.client else "127.0.0.1",
        },
        consent=None,
        trace_id=f"trc_{uuid.uuid4().hex[:8]}",
    )

    persisted = True
    try:
        db.add(
            EventModel(
                id=server_event.event_id,
                tenant_id=server_event.tenant_id,
                site_id=server_event.site_id,
                type=server_event.type,
                occurred_at=server_event.occurred_at,
                actor_type=server_event.actor.type.value,
                actor_id=server_event.actor.id,
                source=server_event.source,
                data=server_event.data,
                trace_id=server_event.trace_id,
                server_received_at=occurred_at,
                client_ip=request.client.host if request.client else "127.0.0.1",
            )
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        persisted = False
        logger.error("Failed to persist webhook event %s: %s", event_id, exc)
        if is_production():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to durably persist webhook event.",
            ) from exc

    dispatched = False
    if persisted:
        try:
            await redis_client.xadd(
                settings.redis_event_stream,
                {"payload": json.dumps(server_event.model_dump(mode="json"))},
            )
            dispatched = True
        except Exception as exc:
            logger.warning("Failed to push webhook event %s to Redis stream: %s", event_id, exc)

    return {
        "status": "received" if persisted else "not_persisted",
        "provider": provider,
        "event_id": event_id,
        "event_type": event_type,
        "tenant_id": tenant_id,
        "signature_verified": signature_verified,
        "dispatched": dispatched,
        "received_at": occurred_at.isoformat(),
    }


__all__ = ["canonical_json", "provider_secret", "router"]
