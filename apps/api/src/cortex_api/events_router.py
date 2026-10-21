"""Event ingestion gateway.

Security contract
-----------------
* ``POST /v1/events`` and ``POST /v1/events/batch`` require a provisioned
  ``X-Cortex-Public-Key``.  The tenant is taken **only** from that credential; a
  payload naming a different tenant is rejected with ``403``, while neutral
  placeholders (``default``/``tenant_default``) are treated as "unspecified".
* Duplicate ``event_id`` values are idempotent: the request succeeds but the
  event is neither persisted twice nor re-dispatched to the stream.
* Persistence failures fail closed in production.  In non-production the
  failure is surfaced as ``status: "not_persisted"`` instead of the previous
  silent ``accepted`` response (audit defects C1/C5/H3).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
from cortex_event_schema import EventSchema, IngestEventResponse
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import and_, desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cortex_api.api_keys import (  # noqa: F401  (hash re-exported for compatibility)
    authenticate_public_key,
    hash_api_key,
)
from cortex_api.auth import Role, require_role
from cortex_api.config import get_db_session, get_redis_client, settings
from cortex_api.db_models import ApiKeyModel, EventModel, SessionModel
from cortex_upgrade.event_ingestion import EventDedupeStore, EventNormalizer
from cortex_upgrade.rate_limit import AtomicSlidingWindow

logger = logging.getLogger("cortex-event-gateway")
router = APIRouter(prefix="/v1/events", tags=["Event Gateway"])

# Payload tenant values that carry no authority claim. The browser SDK sends
# "default" because a public key already determines the tenant server-side, so
# these are treated as "derive from credential" rather than a mismatch.
NEUTRAL_TENANT_VALUES = {"", "default", "tenant_default", "unknown", "self"}

# Deployment-tunable limits. Previously module constants, which meant a
# high-volume site could only be supported by editing code (found while building
# the load harness).
RATE_LIMIT_MAX_REQUESTS = settings.rate_limit_max_requests
RATE_LIMIT_WINDOW_SECONDS = settings.rate_limit_window_seconds
MAX_BATCH_SIZE = settings.max_batch_size
MAX_EVENT_BYTES = settings.max_event_bytes

local_rate_limiter = AtomicSlidingWindow()
dedupe_store = EventDedupeStore()
event_normalizer = EventNormalizer()


def client_ip_for(request: Request) -> str:
    """Resolve the caller IP, honouring the proxy header only when configured."""
    if getattr(settings, "trust_proxy_headers", False):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def _ingestion_circuit():
    """Health observations for the ingestion path (fed by real traffic).

    The self-model reads these samples: without them the ingestion subsystem would be
    "unverified" no matter how many events flowed through it.
    """
    from cortex_core.resilience import global_health_registry

    return global_health_registry.circuit("ingestion")


async def _observe_ingestion(ok: bool, reason: str = "") -> None:
    circuit = _ingestion_circuit()
    if ok:
        await circuit.record_success()
    else:
        await circuit.record_failure(reason or "ingestion failure")


async def _release_event_claims(tenant_id: str, events: list[EventSchema]) -> None:
    for event in events:
        await dedupe_store.release(tenant_id, event.event_id)


async def check_redis_rate_limit(redis_client: aioredis.Redis, key: str) -> None:
    """Sliding-window limiter with a fail-closed local fallback."""
    try:
        current_count = await redis_client.incr(f"ratelimit:{key}")
        if current_count == 1:
            await redis_client.expire(f"ratelimit:{key}", RATE_LIMIT_WINDOW_SECONDS)
        if current_count > RATE_LIMIT_MAX_REQUESTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please throttle event transmissions.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Redis rate limit check failed (%s). Using atomic sliding window fallback.", exc)
        result = await local_rate_limiter.consume(key, RATE_LIMIT_MAX_REQUESTS, float(RATE_LIMIT_WINDOW_SECONDS))
        if not result.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Retry after {result.retry_after:.1f}s.",
            ) from exc


def _enriched_data(event: EventSchema, request: Request, now_utc: datetime, *, batch: bool = False) -> dict[str, Any]:
    enriched = dict(event.data)
    enriched["_server"] = {
        "client_ip": client_ip_for(request),
        "user_agent": request.headers.get("user-agent"),
        "received_at": now_utc.isoformat(),
        "batch": batch,
    }
    return enriched


def _normalize_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


async def _ensure_session(
    db: AsyncSession,
    session_id: str | None,
    tenant_id: str,
    site_id: str,
    visitor_id: str,
    request: Request,
    occurred_at: datetime,
) -> None:
    """Ensure SessionModel exists in database before EventModel is inserted.

    Prevents PostgreSQL Foreign Key constraint violations (events.session_id -> sessions.id).
    Strictly verifies tenant isolation: cross-tenant session hijacking returns 403.
    """
    if not session_id:
        return

    res = await db.execute(select(SessionModel).where(SessionModel.id == session_id))
    existing = res.scalar_one_or_none()

    if existing:
        if existing.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cross-tenant session access forbidden: session belongs to '{existing.tenant_id}', not '{tenant_id}'.",
            )
        norm_occ = _normalize_dt(occurred_at)
        norm_end = _normalize_dt(existing.ended_at)
        if norm_occ and (norm_end is None or norm_occ > norm_end):
            existing.ended_at = norm_occ
    else:
        now = datetime.now(UTC)
        new_session = SessionModel(
            id=session_id,
            tenant_id=tenant_id,
            site_id=site_id,
            visitor_id=visitor_id,
            user_agent=request.headers.get("user-agent"),
            ip_address=client_ip_for(request),
            started_at=occurred_at or now,
            ended_at=occurred_at or now,
            session_metadata={},
            created_at=now,
        )
        db.add(new_session)


async def _ensure_batch_sessions(
    db: AsyncSession,
    events: list[EventSchema],
    tenant_id: str,
    request: Request,
    now_utc: datetime,
) -> None:
    """Ensure all sessions in a batch exist and belong to the authenticated tenant."""
    session_ids = {event.session_id for event in events if event.session_id}
    if not session_ids:
        return

    res = await db.execute(select(SessionModel).where(SessionModel.id.in_(session_ids)))
    existing_sessions = {s.id: s for s in res.scalars().all()}

    # Strict tenant verification: any cross-tenant session raises 403
    for s_id, s in existing_sessions.items():
        if s.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cross-tenant session access forbidden: session '{s_id}' belongs to another tenant.",
            )

    client_ip = client_ip_for(request)
    user_agent = request.headers.get("user-agent")

    for event in events:
        s_id = event.session_id
        if not s_id:
            continue
        occurred_at = event.occurred_at or now_utc
        if s_id in existing_sessions:
            s = existing_sessions[s_id]
            norm_occ = _normalize_dt(occurred_at)
            norm_end = _normalize_dt(s.ended_at)
            if norm_occ and (norm_end is None or norm_occ > norm_end):
                s.ended_at = norm_occ
        else:
            new_session = SessionModel(
                id=s_id,
                tenant_id=tenant_id,
                site_id=event.site_id,
                visitor_id=event.actor.id,
                user_agent=user_agent,
                ip_address=client_ip,
                started_at=occurred_at,
                ended_at=occurred_at,
                session_metadata={},
                created_at=now_utc,
            )
            existing_sessions[s_id] = new_session
            db.add(new_session)


def _to_model(
    event: EventSchema, tenant_id: str, request: Request, now_utc: datetime, enriched: dict[str, Any]
) -> EventModel:
    return EventModel(
        id=event.event_id,
        tenant_id=tenant_id,
        site_id=event.site_id,
        session_id=event.session_id,
        type=event.type,
        occurred_at=event.occurred_at,
        actor_type=event.actor.type.value if hasattr(event.actor.type, "value") else str(event.actor.type),
        actor_id=event.actor.id,
        source=event.source,
        data=enriched,
        consent=event.consent,
        trace_id=event.trace_id,
        server_received_at=now_utc,
        client_ip=client_ip_for(request),
        user_agent=request.headers.get("user-agent"),
    )


async def _publish(redis_client: aioredis.Redis, event: EventSchema, tenant_id: str, enriched: dict[str, Any]) -> bool:
    wire_payload = event.model_dump(mode="json")
    wire_payload["tenant_id"] = tenant_id
    wire_payload["data"] = enriched
    try:
        await redis_client.xadd(settings.redis_event_stream, {"payload": json.dumps(wire_payload)})
        return True
    except Exception as exc:
        logger.warning("Failed to push event %s to Redis stream: %s", event.event_id, exc)
        return False


def _assert_payload_size(event: EventSchema) -> None:
    """Reject oversized payloads before they are persisted or streamed."""
    encoded = len(json.dumps(event.data, default=str).encode())
    if encoded > MAX_EVENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Event data is {encoded} bytes; the maximum is {MAX_EVENT_BYTES}.",
        )


def _assert_tenant_authority(event: EventSchema, credential_tenant: str) -> None:
    """Reject payloads that claim a tenant other than the credential's.

    Neutral placeholders (see ``NEUTRAL_TENANT_VALUES``) are not claims: the
    tenant is always taken from the credential, which keeps the browser SDK —
    configured with a public key and no tenant id — working on a hardened
    gateway.
    """
    supplied = (event.tenant_id or "").strip()
    if supplied and supplied.lower() not in NEUTRAL_TENANT_VALUES and supplied != credential_tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Tenant mismatch: supplied '{event.tenant_id}' does not match the "
                f"credential tenant '{credential_tenant}'."
            ),
        )


@router.post("", response_model=IngestEventResponse)
async def ingest_event(
    event: EventSchema,
    request: Request,
    x_cortex_public_key: str | None = Header(None, alias="X-Cortex-Public-Key"),
    db: AsyncSession = Depends(get_db_session),
    redis_client: aioredis.Redis = Depends(get_redis_client),
):
    now_utc = datetime.now(UTC)

    # 1. Authenticate the credential and derive the authoritative tenant.
    api_key_record = await authenticate_public_key(x_cortex_public_key, db, site_id=event.site_id)

    # 1b. Bound the body size so a single event cannot exhaust memory.
    _assert_payload_size(event)
    auth_tenant = api_key_record.tenant_id
    _assert_tenant_authority(event, auth_tenant)

    # 2. Rate limit per credential + site.
    await check_redis_rate_limit(redis_client, f"{api_key_record.id}:{event.site_id}")

    # 3. Idempotency: a repeated event_id is acknowledged but not re-processed.
    if not await dedupe_store.claim(auth_tenant, event.event_id):
        logger.info("Duplicate event %s for tenant %s acknowledged idempotently.", event.event_id, auth_tenant)
        return IngestEventResponse(status="duplicate", event_id=event.event_id, processed_at=now_utc)

    try:
        await _ensure_session(
            db,
            session_id=event.session_id,
            tenant_id=auth_tenant,
            site_id=event.site_id,
            visitor_id=event.actor.id,
            request=request,
            occurred_at=event.occurred_at or now_utc,
        )
    except Exception:
        await dedupe_store.release(auth_tenant, event.event_id)
        raise

    enriched_data = _enriched_data(event, request, now_utc)
    persisted = True
    try:
        db.add(_to_model(event, auth_tenant, request, now_utc, enriched_data))
        await db.commit()
        await _observe_ingestion(True)
    except IntegrityError as exc:
        await db.rollback()
        # IntegrityError may mean a duplicate ID, but can also signal a different
        # constraint violation. Only acknowledge duplicates that exist for this tenant.
        try:
            existing = await db.execute(
                select(EventModel.id).where(
                    EventModel.id == event.event_id,
                    EventModel.tenant_id == auth_tenant,
                )
            )
            is_duplicate = existing.scalar_one_or_none() is not None
        except Exception as verify_exc:
            logger.error("Unable to verify conflicting event %s: %s", event.event_id, verify_exc)
            is_duplicate = False

        if is_duplicate:
            await _observe_ingestion(True, "duplicate")
            return IngestEventResponse(status="duplicate", event_id=event.event_id, processed_at=now_utc)

        await dedupe_store.release(auth_tenant, event.event_id)
        await _observe_ingestion(False, "IntegrityError")
        if settings.app_env == "production":
            logger.error("Integrity error while persisting event %s: %s", event.event_id, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to durably commit event {event.event_id} to store.",
            ) from exc
        logger.error("Event %s was NOT persisted (integrity error): %s", event.event_id, exc)
        persisted = False
    except Exception as exc:
        await db.rollback()
        await dedupe_store.release(auth_tenant, event.event_id)
        persisted = False
        await _observe_ingestion(False, type(exc).__name__)
        if settings.app_env == "production":
            logger.error("Failed to persist event %s in production: %s", event.event_id, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to durably commit event {event.event_id} to store.",
            ) from exc
        logger.error("Event %s was NOT persisted (non-production): %s", event.event_id, exc)

    dispatched = await _publish(redis_client, event, auth_tenant, enriched_data) if persisted else False

    return IngestEventResponse(
        status="accepted" if persisted else "not_persisted",
        event_id=event.event_id,
        processed_at=now_utc,
        dispatched=dispatched,
    )


@router.post("/batch", response_model=list[IngestEventResponse])
async def ingest_event_batch(
    events: list[EventSchema],
    request: Request,
    x_cortex_public_key: str | None = Header(None, alias="X-Cortex-Public-Key"),
    db: AsyncSession = Depends(get_db_session),
    redis_client: aioredis.Redis = Depends(get_redis_client),
):
    """Batch event ingestion — accepts up to 50 events in a single request."""
    if len(events) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Batch size exceeds maximum of {MAX_BATCH_SIZE} events.",
        )
    if not events:
        return []

    now_utc = datetime.now(UTC)
    for event in events:
        _assert_payload_size(event)
    site_ids = {event.site_id for event in events}
    if len(site_ids) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="All events in a batch must target the same site_id.",
        )
    site_id = site_ids.pop()

    api_key_record = await authenticate_public_key(x_cortex_public_key, db, site_id=site_id)
    auth_tenant = api_key_record.tenant_id

    await check_redis_rate_limit(redis_client, f"{api_key_record.id}:{site_id}")

    responses: list[IngestEventResponse] = []
    pending: list[tuple] = []

    for event in events:
        _assert_tenant_authority(event, auth_tenant)

    for event in events:
        if not await dedupe_store.claim(auth_tenant, event.event_id):
            responses.append(IngestEventResponse(status="duplicate", event_id=event.event_id, processed_at=now_utc))
            continue

        enriched_data = _enriched_data(event, request, now_utc, batch=True)
        pending.append((event, enriched_data))

    try:
        await _ensure_batch_sessions(
            db,
            [e for e, _ in pending],
            auth_tenant,
            request,
            now_utc,
        )
    except Exception:
        await _release_event_claims(auth_tenant, [event for event, _ in pending])
        raise

    for event, enriched_data in pending:
        try:
            db.add(_to_model(event, auth_tenant, request, now_utc, enriched_data))
        except Exception as exc:
            logger.error("Failed to prepare batch event %s: %s", event.event_id, exc)
            responses.append(IngestEventResponse(status="rejected", event_id=event.event_id, processed_at=now_utc))
            await dedupe_store.release(auth_tenant, event.event_id)
            pending = [item for item in pending if item[0].event_id != event.event_id]

    individual_statuses: dict[str, str] | None = None
    try:
        await db.commit()
        committed = True
        await _observe_ingestion(True)
    except IntegrityError as exc:
        await db.rollback()
        logger.warning("Batch contained already-persisted event ids; retrying writes individually: %s", exc)
        individual_statuses = await _commit_individually(db, pending, auth_tenant, request, now_utc)
        await _release_event_claims(
            auth_tenant,
            [event for event, _ in pending if individual_statuses[event.event_id] == "not_persisted"],
        )
        await _observe_ingestion(
            all(result != "not_persisted" for result in individual_statuses.values()),
            "batch individual commit failed",
        )
    except Exception as exc:
        await db.rollback()
        await _release_event_claims(auth_tenant, [event for event, _ in pending])
        await _observe_ingestion(False, type(exc).__name__)
        logger.error("Failed to commit batch of %d events: %s", len(events), exc)
        if settings.app_env == "production":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to durably commit batch to store.",
            ) from exc
        committed = False

    for event, enriched_data in pending:
        if individual_statuses is not None:
            event_status = individual_statuses[event.event_id]
        else:
            event_status = "accepted" if committed else "not_persisted"
        dispatched = (
            await _publish(redis_client, event, auth_tenant, enriched_data) if event_status == "accepted" else False
        )
        responses.append(
            IngestEventResponse(
                status=event_status,
                event_id=event.event_id,
                processed_at=now_utc,
                dispatched=dispatched,
            )
        )

    order = {event.event_id: index for index, event in enumerate(events)}
    responses.sort(key=lambda response: order.get(response.event_id, 0))
    return responses


async def _commit_individually(
    db: AsyncSession,
    pending: list[tuple],
    tenant_id: str,
    request: Request,
    now_utc: datetime,
) -> dict[str, str]:
    """Retry each event separately after a batch conflict and preserve its outcome."""
    outcomes: dict[str, str] = {}
    for event, enriched in pending:
        try:
            await _ensure_session(
                db,
                session_id=event.session_id,
                tenant_id=tenant_id,
                site_id=event.site_id,
                visitor_id=event.actor.id,
                request=request,
                occurred_at=event.occurred_at or now_utc,
            )
            db.add(_to_model(event, tenant_id, request, now_utc, enriched))
            await db.commit()
            outcomes[event.event_id] = "accepted"
        except IntegrityError:
            await db.rollback()
            try:
                existing = await db.execute(
                    select(EventModel.id).where(
                        EventModel.id == event.event_id,
                        EventModel.tenant_id == tenant_id,
                    )
                )
                outcomes[event.event_id] = "duplicate" if existing.scalar_one_or_none() else "not_persisted"
            except Exception as exc:
                logger.error("Unable to verify conflicting batch event %s: %s", event.event_id, exc)
                outcomes[event.event_id] = "not_persisted"
            if outcomes[event.event_id] == "duplicate":
                logger.info("Batch event %s already existed; treated idempotently.", event.event_id)
        except Exception as exc:
            await db.rollback()
            logger.error("Batch event %s failed to commit: %s", event.event_id, exc)
            outcomes[event.event_id] = "not_persisted"
    return outcomes


@router.get("", response_model=list[dict[str, Any]])
async def query_events(
    site_id: str | None = None,
    type: str | None = None,
    actor_id: str | None = None,
    session_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
    db: AsyncSession = Depends(get_db_session),
):
    """Query recent events from the event store scoped strictly to the authenticated tenant.

    ``offset`` exists so callers can page through a tenant's history: without it every
    response was clamped to the newest 200 events and older events were unreadable.
    """
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
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

    # ``id`` is the pagination tiebreaker: events can share ``occurred_at`` (bulk ingestion),
    # and without a total order the same row can appear twice or be skipped while paging.
    stmt = stmt.order_by(desc(EventModel.occurred_at), desc(EventModel.id)).limit(limit).offset(offset)

    try:
        res = await db.execute(stmt)
        records = res.scalars().all()
    except Exception as exc:
        # Returning an empty list here reported a database failure as "tenant has no events"
        # with HTTP 200. Surface the failure instead of silently lying to the caller.
        logger.error("Event query failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="event query failed",
        ) from exc

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


__all__ = [
    "ApiKeyModel",
    "EventNormalizer",
    "check_redis_rate_limit",
    "dedupe_store",
    "router",
]
