from fastapi import APIRouter, Request, Header, HTTPException, status
from typing import Dict, Any, Optional
from datetime import datetime
import uuid
import logging

from nexus_event_schema import EventSchema, Actor, ActorType
from nexus_api.events_router import EVENT_QUEUE, EVENT_STORE

logger = logging.getLogger("nexus-webhooks")
router = APIRouter(prefix="/v1/webhooks", tags=["Webhooks"])


@router.post("/{provider}")
async def receive_webhook(
    provider: str,
    payload: Dict[str, Any],
    request: Request,
    x_nexus_signature: Optional[str] = Header(None, alias="X-Nexus-Signature"),
    x_tenant_id: Optional[str] = Header("default", alias="X-Tenant-ID"),
    x_site_id: Optional[str] = Header("backend", alias="X-Site-ID")
):
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty webhook payload received")

    event_type = payload.get("event") or payload.get("type") or f"{provider}.webhook_received"
    actor_id = payload.get("customer_id") or payload.get("user_id") or payload.get("email") or f"{provider}_system"

    event_id = f"evt_wh_{uuid.uuid4().hex[:12]}"
    server_event = EventSchema(
        event_id=event_id,
        tenant_id=x_tenant_id or "default",
        site_id=x_site_id or "backend",
        type=event_type,
        occurred_at=datetime.utcnow(),
        actor=Actor(
            type=ActorType.USER if "user" in actor_id or "@" in actor_id else ActorType.SYSTEM,
            id=str(actor_id)
        ),
        source=f"webhook:{provider}",
        data={
            "payload": payload,
            "_provider": provider,
            "_signature_present": bool(x_nexus_signature),
            "_client_ip": request.client.host if request.client else "127.0.0.1"
        },
        trace_id=f"trc_{uuid.uuid4().hex[:8]}"
    )

    EVENT_STORE.append(server_event.model_dump(mode="json"))
    try:
        EVENT_QUEUE.put_nowait(server_event.model_dump(mode="json"))
    except Exception as e:
        logger.warning(f"Failed to queue webhook event: {e}")

    return {
        "status": "received",
        "provider": provider,
        "event_id": event_id,
        "event_type": event_type,
        "timestamp": datetime.utcnow().isoformat()
    }
