from fastapi import APIRouter, Request, Header, HTTPException, Depends, status
from typing import Dict, Any, Optional
from datetime import datetime
import uuid
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from nexus_event_schema import EventSchema, Actor, ActorType
from nexus_api.config import get_db_session, get_redis_client, settings
from nexus_api.db_models import EventModel

logger = logging.getLogger("nexus-webhooks")
router = APIRouter(prefix="/v1/webhooks", tags=["Webhooks"])


@router.post("/{provider}")
async def receive_webhook(
    provider: str,
    payload: Dict[str, Any],
    request: Request,
    x_nexus_signature: Optional[str] = Header(None, alias="X-Nexus-Signature"),
    x_tenant_id: Optional[str] = Header("default", alias="X-Tenant-ID"),
    x_site_id: Optional[str] = Header("backend", alias="X-Site-ID"),
    db: AsyncSession = Depends(get_db_session),
    redis_client: aioredis.Redis = Depends(get_redis_client)
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
            type=ActorType.USER if ("user" in str(actor_id) or "@" in str(actor_id)) else ActorType.SYSTEM,
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

    # Persist to PostgreSQL
    try:
        db_event = EventModel(
            id=server_event.event_id,
            tenant_id=server_event.tenant_id,
            site_id=server_event.site_id,
            type=server_event.type,
            occurred_at=server_event.occurred_at,
            actor_type=server_event.actor.type.value if hasattr(server_event.actor.type, "value") else str(server_event.actor.type),
            actor_id=server_event.actor.id,
            source=server_event.source,
            data=server_event.data,
            trace_id=server_event.trace_id,
            server_received_at=datetime.utcnow(),
            client_ip=request.client.host if request.client else "127.0.0.1"
        )
        db.add(db_event)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(f"Failed to persist webhook event {event_id} to DB: {exc}")

    # Push to Redis Stream
    try:
        await redis_client.xadd(
            settings.redis_event_stream,
            {"payload": json.dumps(server_event.model_dump(mode="json"))}
        )
    except Exception as exc:
        logger.warning(f"Failed to push webhook event {event_id} to Redis Stream: {exc}")

    return {
        "status": "received",
        "provider": provider,
        "event_id": event_id,
        "event_type": event_type,
        "timestamp": datetime.utcnow().isoformat()
    }
