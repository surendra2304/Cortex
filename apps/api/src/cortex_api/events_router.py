from fastapi import APIRouter, Request, HTTPException, Header, Depends, status
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Request, HTTPException, Header, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
import redis.asyncio as aioredis

from cortex_event_schema import EventSchema, IngestEventResponse
from cortex_api.config import get_db_session, get_redis_client, settings
from cortex_api.db_models import EventModel, ApiKeyModel
from cortex_api.auth import require_role, Role
from cortex_upgrade.rate_limit import AtomicSlidingWindow
from cortex_upgrade.event_ingestion import EventDedupeStore, EventNormalizer, EventRejected

logger = logging.getLogger("cortex-event-gateway")
router = APIRouter(prefix="/v1/events", tags=["Event Gateway"])

RATE_LIMIT_MAX_REQUESTS = 1000
RATE_LIMIT_WINDOW_SECONDS = 60

local_rate_limiter = AtomicSlidingWindow()
dedupe_store = EventDedupeStore()
event_normalizer = EventNormalizer()


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
        if hasattr(res, "scalar_one_or_none"):
            record = res.scalar_one_or_none()
            if record:
                record.last_used_at = datetime.now(timezone.utc)
                await db.commit()
                return record
    except Exception as exc:
        logger.warning(f"DB lookup for API key failed ({exc}).")

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
        # Fail-closed atomic sliding window local fallback — do not silently bypass!
        logger.warning(f"Redis rate limit check failed ({exc}). Using atomic sliding window fallback.")
        result = await local_rate_limiter.consume(key, RATE_LIMIT_MAX_REQUESTS, float(RATE_LIMIT_WINDOW_SECONDS))
        if not result.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Retry after {result.retry_after:.1f}s."
            )


@router.post("", response_model=IngestEventResponse)
async def ingest_event(
    event: EventSchema,
    request: Request,
    x_cortex_public_key: Optional[str] = Header(None, alias="X-Cortex-Public-Key"),
    db: AsyncSession = Depends(get_db_session),
    redis_client: aioredis.Redis = Depends(get_redis_client)
):
    client_ip = request.client.host if request.client else "127.0.0.1"
    now_utc = datetime.now(timezone.utc)
    
    # 1. Validate Public API Key against PostgreSQL
    api_key_record = await validate_api_key(x_cortex_public_key, event.site_id, db)

    # 2. Derive authoritative tenant and enforce tenant isolation
    auth_tenant = api_key_record.tenant_id if api_key_record else event.tenant_id
    if api_key_record and event.tenant_id and event.tenant_id != api_key_record.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tenant mismatch: supplied '{event.tenant_id}' does not match credential tenant '{api_key_record.tenant_id}'."
        )

    # 3. Check Rate Limit (1000/min)
    rate_key = f"{x_cortex_public_key or client_ip}:{event.site_id}"
    await check_redis_rate_limit(redis_client, rate_key)

    # 4. Deduplicate event IDs within tenant
    await dedupe_store.claim(auth_tenant, event.event_id)

    # 5. Server-side context enrichment
    enriched_data = dict(event.data)
    enriched_data["_server"] = {
        "client_ip": client_ip,
        "user_agent": request.headers.get("user-agent"),
        "received_at": now_utc.isoformat(),
        "public_key_present": bool(x_cortex_public_key)
    }

    # 6. Persist to PostgreSQL (FAIL-CLOSED: if DB fails, request fails)
    try:
        db_event = EventModel(
            id=event.event_id,
            tenant_id=auth_tenant,
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
            server_received_at=now_utc,
            client_ip=client_ip,
            user_agent=request.headers.get("user-agent")
        )
        db.add(db_event)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        if settings.app_env == "production":
            logger.error(f"Failed to persist event {event.event_id} to PostgreSQL in production: {exc}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to durably commit event {event.event_id} to store: {exc}"
            )
        else:
            logger.warning(f"Failed to persist event {event.event_id} to PostgreSQL (dev/test offline mode): {exc}")

    # 7. Dispatch event to Redis Stream (with outbox / logging fail-safe)
    try:
        event_wire_payload = event.model_dump(mode="json")
        event_wire_payload["tenant_id"] = auth_tenant
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
        processed_at=now_utc
    )


@router.post("/batch", response_model=List[IngestEventResponse])
async def ingest_event_batch(
    events: List[EventSchema],
    request: Request,
    x_cortex_public_key: Optional[str] = Header(None, alias="X-Cortex-Public-Key"),
    db: AsyncSession = Depends(get_db_session),
    redis_client: aioredis.Redis = Depends(get_redis_client)
):
    """Batch event ingestion — accepts up to 50 events in a single request."""
    if len(events) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch size exceeds maximum of 50 events."
        )
    if not events:
        return []

    client_ip = request.client.host if request.client else "127.0.0.1"
    now_utc = datetime.now(timezone.utc)
    site_id = events[0].site_id
    api_key_record = await validate_api_key(x_cortex_public_key, site_id, db)

    rate_key = f"{x_cortex_public_key or client_ip}:{site_id}"
    await check_redis_rate_limit(redis_client, rate_key)

    responses: List[IngestEventResponse] = []
    for event in events:
        auth_tenant = api_key_record.tenant_id if api_key_record else event.tenant_id
        if api_key_record and event.tenant_id and event.tenant_id != api_key_record.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Batch tenant mismatch for event {event.event_id}."
            )

        await dedupe_store.claim(auth_tenant, event.event_id)

        enriched_data = dict(event.data)
        enriched_data["_server"] = {
            "client_ip": client_ip,
            "user_agent": request.headers.get("user-agent"),
            "received_at": now_utc.isoformat(),
            "public_key_present": bool(x_cortex_public_key),
            "batch": True,
        }

        try:
            db_event = EventModel(
                id=event.event_id,
                tenant_id=auth_tenant,
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
                server_received_at=now_utc,
                client_ip=client_ip,
                user_agent=request.headers.get("user-agent")
            )
            db.add(db_event)
        except Exception as exc:
            logger.error(f"Failed to prepare batch event {event.event_id}: {exc}")

        try:
            event_wire_payload = event.model_dump(mode="json")
            event_wire_payload["tenant_id"] = auth_tenant
            event_wire_payload["data"] = enriched_data
            await redis_client.xadd(
                settings.redis_event_stream,
                {"payload": json.dumps(event_wire_payload)}
            )
        except Exception as exc:
            logger.warning(f"Failed to push batch event {event.event_id} to Redis Stream: {exc}")

        responses.append(IngestEventResponse(
            status="accepted",
            event_id=event.event_id,
            processed_at=now_utc
        ))

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(f"Failed to commit batch of {len(events)} events: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to durably commit batch to store: {exc}"
        )

    return responses


@router.get("", response_model=List[Dict[str, Any]])
async def query_events(
    site_id: Optional[str] = None,
    type: Optional[str] = None,
    actor_id: Optional[str] = None,
    session_id: Optional[str] = None,
    limit: int = 50,
    auth: Dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
    db: AsyncSession = Depends(get_db_session)
):
    """Query recent events from the event store scoped strictly to the authenticated tenant."""
    limit = min(limit, 200)
    tenant_id = auth.get("tenant_id", "tenant_default")
    stmt = select(EventModel).where(EventModel.tenant_id == tenant_id)
    conditions = []

    if site_id:
        conditions.append(EventModel.site_id == site_id)
    if type:
        conditions.append(EventModel.type == type)
    if actor_id:
        conditions.append(EventModel.actor_id == actor_id)
    if session_id:
        conditions.append(EventModel.session_id == session_id)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    stmt = stmt.order_by(desc(EventModel.occurred_at)).limit(limit)

    try:
        res = await db.execute(stmt)
        records = res.scalars().all()
        return [
            {
                "event_id": r.id,
                "tenant_id": r.tenant_id,
                "site_id": r.site_id,
                "type": r.type,
                "actor_id": r.actor_id,
                "actor_type": r.actor_type,
                "session_id": r.session_id,
                "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
                "data": r.data,
                "source": r.source,
                "trace_id": r.trace_id,
            }
            for r in records
        ]
    except Exception as exc:
        logger.error(f"Event query failed: {exc}")
        return []
