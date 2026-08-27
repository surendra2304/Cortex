from fastapi import APIRouter, Request, HTTPException, Header, status
from typing import Optional, Dict, Any
from datetime import datetime
import asyncio
import logging

from nexus_event_schema import EventSchema, IngestEventResponse

logger = logging.getLogger("nexus-event-gateway")
router = APIRouter(prefix="/v1/events", tags=["Event Gateway"])

# In-memory rate limiting and queue storage stubs (Redis/PostgreSQL simulation)
RATE_LIMIT_BUCKET: Dict[str, list] = {}
RATE_LIMIT_MAX_REQUESTS = 120  # per minute
RATE_LIMIT_WINDOW_SECONDS = 60

EVENT_QUEUE: asyncio.Queue = asyncio.Queue(maxsize=10000)
EVENT_STORE: list = []


def check_rate_limit(client_key: str):
    now = datetime.utcnow().timestamp()
    timestamps = RATE_LIMIT_BUCKET.setdefault(client_key, [])
    # Filter out timestamps outside window
    RATE_LIMIT_BUCKET[client_key] = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW_SECONDS]
    if len(RATE_LIMIT_BUCKET[client_key]) >= RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please throttle event transmissions."
        )
    RATE_LIMIT_BUCKET[client_key].append(now)


@router.post("", response_model=IngestEventResponse)
async def ingest_event(
    event: EventSchema,
    request: Request,
    x_nexus_public_key: Optional[str] = Header(None, alias="X-Nexus-Public-Key")
):
    client_ip = request.client.host if request.client else "127.0.0.1"
    rate_key = f"{x_nexus_public_key or client_ip}:{event.site_id}"
    check_rate_limit(rate_key)

    # Server-side context enrichment
    enriched_data = dict(event.data)
    enriched_data["_server"] = {
        "client_ip": client_ip,
        "user_agent": request.headers.get("user-agent"),
        "received_at": datetime.utcnow().isoformat(),
        "public_key_present": bool(x_nexus_public_key)
    }

    enriched_event = event.model_copy(update={"data": enriched_data})

    # Store in persistence store (PostgreSQL event store simulation)
    EVENT_STORE.append(enriched_event.model_dump(mode="json"))

    # Dispatch to internal processing queue (Redis/asyncio queue simulation)
    try:
        EVENT_QUEUE.put_nowait(enriched_event.model_dump(mode="json"))
    except asyncio.QueueFull:
        logger.warning("Event queue full. Event persisted to storage only.")

    return IngestEventResponse(
        status="accepted",
        event_id=event.event_id,
        processed_at=datetime.utcnow()
    )
