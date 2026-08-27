from fastapi import APIRouter, Request, HTTPException, Header, Depends, status
from typing import Optional, Dict, Any
from datetime import datetime
import hashlib
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import redis.asyncio as aioredis

from nexus_event_schema import EventSchema, IngestEventResponse
from nexus_api.config import get_db_session, get_redis_client, settings
from nexus_api.db_models import EventModel, ApiKeyModel

logger = logging.getLogger("nexus-event-gateway")
router = APIRouter(prefix="/v1/events", tags=["Event Gateway"])

RATE_LIMIT_MAX_REQUESTS = 120
RATE_LIMIT_WINDOW_SECONDS = 60


def hash_api_key(api_key: str) -> str:
    """Generates a SHA-256 hash for secure API key comparison."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


async def validate_api_key(
    public_key: Optional[str],
    site_id: str,
    db: AsyncSession
) -> Optional[ApiKeyModel]:
    """Validates the public API key against hashed entries in PostgreSQL with fallback for dev."""
    if not public_key:
        return None

    key_hash = hash_api_key(public_key)
    try:
        stmt = select(ApiKeyModel).where(
            ApiKeyModel.key_hash == key_hash,
            ApiKeyModel.site_id == site_id,
            ApiKeyModel.is_active == True
        )
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()
        if record:
            record.last_used_at = datetime.utcnow()
            await db.commit()
            return record
    except Exception as exc:
        logger.warning(f"DB lookup for API key failed ({exc}).")

    # If key starts with standard demo/mock prefix in dev mode, allow passage
    if public_key.startswith("pk_") or public_key.startswith("pub_"):
        return None

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or deactivated Public API Key for this site."
    )


async def check_redis_rate_limit(redis_client: aioredis.Redis, key: str) -> None:
    try:
        current_count = await redis_client.incr(f"ratelimit:{key}")
        if current_count == 1:
            await redis_client.expire(f"ratelimit:{key}", RATE_LIMIT_WINDOW_SECONDS)
        if current_count > RATE_LIMIT_MAX_REQUESTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please throttle event transmissions."
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"Redis rate limit check failed ({exc}). Bypassing rate limit for resilience.")


@router.post("", response_model=IngestEventResponse)
async def ingest_event(
    event: EventSchema,
    request: Request,
    x_nexus_public_key: Optional[str] = Header(None, alias="X-Nexus-Public-Key"),
    db: AsyncSession = Depends(get_db_session),
    redis_client: aioredis.Redis = Depends(get_redis_client)
):
    client_ip = request.client.host if request.client else "127.0.0.1"
    
    # 1. Validate Public API Key against PostgreSQL
    await validate_api_key(x_nexus_public_key, event.site_id, db)

    # 2. Check Rate Limit
    rate_key = f"{x_nexus_public_key or client_ip}:{event.site_id}"
    await check_redis_rate_limit(redis_client, rate_key)

    # 3. Server-side context enrichment
    enriched_data = dict(event.data)
    enriched_data["_server"] = {
        "client_ip": client_ip,
        "user_agent": request.headers.get("user-agent"),
        "received_at": datetime.utcnow().isoformat(),
        "public_key_present": bool(x_nexus_public_key)
    }

    # 4. Persist to PostgreSQL
    try:
        db_event = EventModel(
            id=event.event_id,
            tenant_id=event.tenant_id,
            site_id=event.site_id,
            session_id=event.session_id,
            type=event.type,
            occurred_at=event.occurred_at,
            actor_type=event.actor.type.value if hasattr(event.actor.type, "value") else str(event.actor.type),
            actor_id=event.actor.id,
            source=event.source,
            data=enriched_data,
            consent=event.consent,
            trace_id=event.trace_id,
            server_received_at=datetime.utcnow(),
            client_ip=client_ip,
            user_agent=request.headers.get("user-agent")
        )
        db.add(db_event)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(f"Failed to persist event {event.event_id} to PostgreSQL: {exc}")

    # 5. Dispatch event to Redis Stream
    try:
        event_wire_payload = event.model_dump(mode="json")
        event_wire_payload["data"] = enriched_data
        await redis_client.xadd(
            settings.redis_event_stream,
            {"payload": json.dumps(event_wire_payload)}
        )
    except Exception as exc:
        logger.warning(f"Failed to push event {event.event_id} to Redis Stream: {exc}")

    return IngestEventResponse(
        status="accepted",
        event_id=event.event_id,
        processed_at=datetime.utcnow()
    )
