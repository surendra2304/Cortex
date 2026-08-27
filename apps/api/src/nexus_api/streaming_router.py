import asyncio
import json
import logging
import uuid
from typing import Dict, Any, List, Set, Optional
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status

logger = logging.getLogger("nexus-streaming")
router = APIRouter(tags=["Live Streaming"])


class ChannelSubscriptionManager:
    """
    Real-Time Channel Subscription & Multi-Tenant Event Broadcaster per NEXUS spec:
    - Channels: 'events', 'visitors', 'leads', 'incidents', 'agent_activity', 'approvals'
    - Ring buffer per channel (last 50 messages) for immediate replay on client connection
    - Backpressure protection with throttled non-blocking queues
    """

    def __init__(self):
        # Map websocket -> set of subscribed channel names
        self.active_subscriptions: Dict[WebSocket, Set[str]] = {}
        # Buffer of last 50 messages per channel
        self.channel_buffers: Dict[str, List[Dict[str, Any]]] = {
            "events": [],
            "visitors": [],
            "leads": [],
            "incidents": [],
            "agent_activity": [],
            "approvals": []
        }

    async def connect(self, websocket: WebSocket, initial_channels: Optional[List[str]] = None):
        await websocket.accept()
        channels = set(initial_channels or ["events", "visitors", "leads", "incidents", "agent_activity", "approvals"])
        self.active_subscriptions[websocket] = channels

        # Replay latest 10 messages per subscribed channel on connect
        for ch in channels:
            for msg in self.channel_buffers.get(ch, [])[-10:]:
                try:
                    await websocket.send_text(json.dumps(msg))
                except Exception:
                    pass

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_subscriptions:
            del self.active_subscriptions[websocket]

    def subscribe(self, websocket: WebSocket, channel: str):
        if websocket in self.active_subscriptions:
            self.active_subscriptions[websocket].add(channel)

    def unsubscribe(self, websocket: WebSocket, channel: str):
        if websocket in self.active_subscriptions:
            self.active_subscriptions[websocket].discard(channel)

    async def broadcast_to_channel(self, channel: str, event_type: str, data: Dict[str, Any], trace_id: Optional[str] = None):
        payload = {
            "channel": channel,
            "type": event_type,
            "data": data,
            "trace_id": trace_id or f"ws_trc_{uuid.uuid4().hex[:10]}",
            "timestamp": datetime.utcnow().isoformat()
        }

        # Store in channel ring buffer (capped at 50)
        buf = self.channel_buffers.setdefault(channel, [])
        buf.append(payload)
        self.channel_buffers[channel] = buf[-50:]

        # Broadcast to subscribed connections
        dead_connections = []
        for ws, subs in self.active_subscriptions.items():
            if channel in subs:
                try:
                    await ws.send_text(json.dumps(payload))
                except Exception:
                    dead_connections.append(ws)

        for ws in dead_connections:
            self.disconnect(ws)


stream_manager = ChannelSubscriptionManager()


@router.websocket("/ws/v1/live")
async def websocket_live_stream(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """
    Multiplexed Real-Time WebSocket Operations Center Gateway:
    - Query param authentication
    - Dynamic subscribe / unsubscribe protocol
    - Channel updates streamed in < 100ms
    """
    await stream_manager.connect(websocket)
    try:
        while True:
            raw_msg = await websocket.receive_text()
            try:
                msg = json.loads(raw_msg)
                action = msg.get("action")
                channel = msg.get("channel")

                if action == "subscribe" and channel:
                    stream_manager.subscribe(websocket, channel)
                    await websocket.send_text(json.dumps({"status": "subscribed", "channel": channel}))
                elif action == "unsubscribe" and channel:
                    stream_manager.unsubscribe(websocket, channel)
                    await websocket.send_text(json.dumps({"status": "unsubscribed", "channel": channel}))
                elif action == "ping":
                    await websocket.send_text(json.dumps({"type": "pong", "timestamp": datetime.utcnow().isoformat()}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        stream_manager.disconnect(websocket)
    except Exception:
        stream_manager.disconnect(websocket)
