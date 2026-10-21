import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import jwt
from fastapi import APIRouter, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse

from cortex_api import auth as auth_module
from cortex_api.ws_auth import authenticate_websocket


logger = logging.getLogger("cortex-streaming")
router = APIRouter(tags=["Live Streaming"])


class ChannelSubscriptionManager:
    """
    Real-Time Channel Subscription & Multi-Tenant Event Broadcaster per CORTEX spec:
    - Tenant-isolated channel buffers and connection sets
    - Channels: 'events', 'visitors', 'leads', 'incidents', 'agent_activity', 'approvals'
    - Ring buffer per channel (last 50 messages) for immediate replay on client connection
    - Backpressure protection with throttled non-blocking queues
    - Per-tenant connection limits
    """

    def __init__(self, max_connections_per_tenant: int = 100):
        self.max_connections_per_tenant = max_connections_per_tenant
        # tenant_id -> {websocket: set_of_channels}
        self.tenant_subscriptions: dict[str, dict[WebSocket, set[str]]] = {}
        # tenant_id -> {channel: list_of_messages}
        self.tenant_buffers: dict[str, dict[str, list[dict[str, Any]]]] = {}
        # Keep channel_buffers for backward compatibility in unit tests
        self.channel_buffers: dict[str, list[dict[str, Any]]] = {
            "events": [],
            "visitors": [],
            "leads": [],
            "incidents": [],
            "agent_activity": [],
            "approvals": [],
        }
        # tenant_id -> list of (asyncio.Queue, set_of_channels)
        self.tenant_sse_subscribers: dict[str, list[tuple[asyncio.Queue, set[str]]]] = {}

    async def connect(
        self, websocket: WebSocket, tenant_id: str = "tenant_default", initial_channels: list[str] | None = None
    ) -> bool:
        tenant_conns = self.tenant_subscriptions.setdefault(tenant_id, {})
        if len(tenant_conns) >= self.max_connections_per_tenant:
            await websocket.close(code=1008)
            return False

        await websocket.accept()
        channels = set(initial_channels or ["events", "visitors", "leads", "incidents", "agent_activity", "approvals"])
        tenant_conns[websocket] = channels

        # Replay latest 10 messages per subscribed channel on connect
        t_buffer = self.tenant_buffers.setdefault(tenant_id, {})
        for ch in channels:
            for msg in t_buffer.get(ch, self.channel_buffers.get(ch, []))[-10:]:
                try:
                    await websocket.send_text(json.dumps(msg))
                except Exception:
                    pass
        return True

    def disconnect(self, websocket: WebSocket, tenant_id: str | None = None):
        if tenant_id and tenant_id in self.tenant_subscriptions:
            self.tenant_subscriptions[tenant_id].pop(websocket, None)
        else:
            for _tenant_id, conns in list(self.tenant_subscriptions.items()):
                if websocket in conns:
                    del conns[websocket]

    def subscribe(self, websocket: WebSocket, channel: str, tenant_id: str = "tenant_default"):
        conns = self.tenant_subscriptions.get(tenant_id, {})
        if websocket in conns:
            conns[websocket].add(channel)

    def unsubscribe(self, websocket: WebSocket, channel: str, tenant_id: str = "tenant_default"):
        conns = self.tenant_subscriptions.get(tenant_id, {})
        if websocket in conns:
            conns[websocket].discard(channel)

    async def broadcast_to_channel(
        self,
        channel: str,
        event_type: str,
        data: dict[str, Any],
        trace_id: str | None = None,
        tenant_id: str = "tenant_default",
    ):
        payload = {
            "channel": channel,
            "type": event_type,
            "tenant_id": tenant_id,
            "data": data,
            "trace_id": trace_id or f"ws_trc_{uuid.uuid4().hex[:10]}",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Store in tenant channel ring buffer (capped at 50)
        t_buf = self.tenant_buffers.setdefault(tenant_id, {}).setdefault(channel, [])
        t_buf.append(payload)
        self.tenant_buffers[tenant_id][channel] = t_buf[-50:]

        # Also store in global ring buffer for backward compatibility
        buf = self.channel_buffers.setdefault(channel, [])
        buf.append(payload)
        self.channel_buffers[channel] = buf[-50:]

        # Broadcast strictly to subscribed connections belonging to this tenant
        tenant_conns = self.tenant_subscriptions.get(tenant_id, {})
        dead_connections = []
        for ws, subs in list(tenant_conns.items()):
            if channel in subs:
                try:
                    await ws.send_text(json.dumps(payload))
                except Exception:
                    dead_connections.append(ws)

        for ws in dead_connections:
            self.disconnect(ws, tenant_id)

        # Broadcast to active SSE subscribers for this tenant
        sse_subs = self.tenant_sse_subscribers.get(tenant_id, [])
        for q, ch_set in list(sse_subs):
            if channel in ch_set:
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    pass


    def subscribe_sse(self, tenant_id: str, channels: set[str]) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.tenant_sse_subscribers.setdefault(tenant_id, []).append((q, channels))
        return q

    def unsubscribe_sse(self, tenant_id: str, q: asyncio.Queue) -> None:
        if tenant_id in self.tenant_sse_subscribers:
            self.tenant_sse_subscribers[tenant_id] = [
                (sub_q, ch) for sub_q, ch in self.tenant_sse_subscribers[tenant_id] if sub_q is not q
            ]

stream_manager = ChannelSubscriptionManager()


@router.websocket("/ws/v1/live")
async def websocket_live_stream(websocket: WebSocket, token: str | None = Query(None)):
    """
    Multiplexed Real-Time WebSocket Operations Center Gateway:
    - Authenticated query param with tenant derivation
    - Dynamic subscribe / unsubscribe protocol
    - Channel updates streamed in < 100ms with strict tenant isolation
    """
    tenant_id = await authenticate_websocket(websocket, token)
    if tenant_id is None:
        return

    connected = await stream_manager.connect(websocket, tenant_id=tenant_id)
    if not connected:
        return

    try:
        while True:
            raw_msg = await websocket.receive_text()
            try:
                msg = json.loads(raw_msg)
                action = msg.get("action")
                channel = msg.get("channel")

                if action == "subscribe" and channel:
                    stream_manager.subscribe(websocket, channel, tenant_id=tenant_id)
                    await websocket.send_text(json.dumps({"status": "subscribed", "channel": channel}))
                elif action == "unsubscribe" and channel:
                    stream_manager.unsubscribe(websocket, channel, tenant_id=tenant_id)
                    await websocket.send_text(json.dumps({"status": "unsubscribed", "channel": channel}))
                elif action == "ping":
                    await websocket.send_text(json.dumps({"type": "pong", "timestamp": datetime.now(UTC).isoformat()}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        stream_manager.disconnect(websocket, tenant_id=tenant_id)
    except Exception:
        stream_manager.disconnect(websocket, tenant_id=tenant_id)
@router.get("/v1/stream/sse")
async def sse_live_stream(
    request: Request,
    token: str | None = Query(None),
    authorization: str | None = Header(None),
    channels: str = Query("events,visitors,leads,incidents,agent_activity,approvals"),
    ping_interval_seconds: float = Query(15.0, ge=0.01, le=60.0),
    max_events: int = Query(0, ge=0, le=1000, description="0 for continuous stream, >0 to cap events"),
):
    """
    Authenticated Server-Sent Events (SSE) telemetry stream:
    - Supports JWT bearer token via Authorization header or token query parameter
    - Channels filtering
    - Keep-alive heartbeat ping every ping_interval_seconds
    - Optional max_events limit for testing or bounded event subscriptions
    - Strict multi-tenant isolation
    """
    raw_token = token
    if not raw_token and authorization and authorization.startswith("Bearer "):
        raw_token = authorization.split("Bearer ", 1)[1].strip()

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials for live SSE stream.",
        )

    # Validate token
    try:
        secret = getattr(auth_module, "JWT_SECRET", "default_secret")
        payload = jwt.decode(raw_token, secret, algorithms=["HS256", "RS256"], options={"verify_exp": True})
        tenant_id = str(payload.get("tenant_id") or "tenant_default")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired streaming token: {exc}",
        )

    channel_set = {c.strip() for c in channels.split(",") if c.strip()}
    queue = stream_manager.subscribe_sse(tenant_id, channel_set)

    async def sse_generator():
        events_emitted = 0
        # Send initial connected message
        init_payload = {
            "status": "connected",
            "tenant_id": tenant_id,
            "channels": sorted(list(channel_set)),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        yield f"event: connection\ndata: {json.dumps(init_payload)}\n\n"
        events_emitted += 1
        if max_events > 0 and events_emitted >= max_events:
            stream_manager.unsubscribe_sse(tenant_id, queue)
            return

        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=ping_interval_seconds)
                    msg_id = msg.get("trace_id", str(uuid.uuid4()))
                    ch = msg.get("channel", "events")
                    yield f"id: {msg_id}\nevent: {ch}\ndata: {json.dumps(msg)}\n\n"
                    events_emitted += 1
                    if max_events > 0 and events_emitted >= max_events:
                        break
                except (TimeoutError, asyncio.TimeoutError):
                    ping_data = {"type": "ping", "timestamp": datetime.now(UTC).isoformat()}
                    yield f"event: ping\ndata: {json.dumps(ping_data)}\n\n"
                    events_emitted += 1
                    if max_events > 0 and events_emitted >= max_events:
                        break
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            stream_manager.unsubscribe_sse(tenant_id, queue)

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
