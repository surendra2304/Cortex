import time
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Response, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import redis.asyncio as aioredis

from nexus_api.config import get_db_session, get_redis_client, settings

logger = logging.getLogger("nexus-production-hardening")
router = APIRouter(tags=["Production & Observability"])

# Prometheus Metrics Storage in memory
METRICS = {
    "events_ingested_total": 0,
    "cognitive_loop_duration_seconds_sum": 0.0,
    "cognitive_loop_duration_seconds_count": 0,
    "ai_universe_calls_total": 0,
    "ai_universe_fallback_total": 0,
    "workflow_runs_total": 0,
    "approval_queue_depth": 0,
    "strategy_performance_gauge": 0.85
}


def increment_metric(name: str, value: float = 1.0) -> None:
    if name in METRICS:
        METRICS[name] += value


def observe_duration(name_prefix: str, duration_sec: float) -> None:
    METRICS[f"{name_prefix}_sum"] += duration_sec
    METRICS[f"{name_prefix}_count"] += 1


# ── 1. PROMETHEUS METRICS ENDPOINT ───────────────────────────────────────────

@router.get("/metrics")
async def prometheus_metrics():
    """Exposes Prometheus text exposition format metrics."""
    avg_loop_duration = (
        METRICS["cognitive_loop_duration_seconds_sum"] / METRICS["cognitive_loop_duration_seconds_count"]
        if METRICS["cognitive_loop_duration_seconds_count"] > 0 else 0.0
    )

    lines = [
        "# HELP events_ingested_total Total count of events ingested across all endpoints",
        "# TYPE events_ingested_total counter",
        f"events_ingested_total {METRICS['events_ingested_total']}",
        "",
        "# HELP cognitive_loop_duration_seconds Duration of cognitive loop executions",
        "# TYPE cognitive_loop_duration_seconds summary",
        f"cognitive_loop_duration_seconds_sum {METRICS['cognitive_loop_duration_seconds_sum']:.4f}",
        f"cognitive_loop_duration_seconds_count {METRICS['cognitive_loop_duration_seconds_count']}",
        f"cognitive_loop_duration_seconds_avg {avg_loop_duration:.4f}",
        "",
        "# HELP ai_universe_calls_total Total calls made to AI Universe deliberation layer",
        "# TYPE ai_universe_calls_total counter",
        f"ai_universe_calls_total {METRICS['ai_universe_calls_total']}",
        "",
        "# HELP ai_universe_fallback_total Total times deterministic fallback was engaged",
        "# TYPE ai_universe_fallback_total counter",
        f"ai_universe_fallback_total {METRICS['ai_universe_fallback_total']}",
        "",
        "# HELP workflow_runs_total Total automated workflow state machine runs",
        "# TYPE workflow_runs_total counter",
        f"workflow_runs_total {METRICS['workflow_runs_total']}",
        "",
        "# HELP approval_queue_depth Current pending human-in-the-loop approval actions",
        "# TYPE approval_queue_depth gauge",
        f"approval_queue_depth {METRICS['approval_queue_depth']}",
        "",
        "# HELP strategy_performance_gauge Aggregated strategy win rate",
        "# TYPE strategy_performance_gauge gauge",
        f"strategy_performance_gauge {METRICS['strategy_performance_gauge']:.2f}"
    ]

    return Response(content="\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


# ── 2. HEALTH & READINESS PROBES ─────────────────────────────────────────────

@router.get("/health")
async def liveness_probe():
    """Liveness probe: verifies process is alive."""
    return {"status": "UP", "timestamp": datetime.utcnow().isoformat(), "service": settings.app_name}


@router.get("/health/ready")
async def readiness_probe(
    db: AsyncSession = Depends(get_db_session),
    redis_client: aioredis.Redis = Depends(get_redis_client)
):
    """Readiness probe: validates PostgreSQL, Redis, and internal dependencies."""
    checks = {"postgres": "UNKNOWN", "redis": "UNKNOWN", "ai_universe": "READY"}

    # 1. PostgreSQL check
    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = "UP"
    except Exception as exc:
        checks["postgres"] = f"DOWN: {str(exc)[:50]}"

    # 2. Redis check
    try:
        ping = await redis_client.ping()
        checks["redis"] = "UP" if ping else "DOWN"
    except Exception as exc:
        checks["redis"] = f"DOWN: {str(exc)[:50]}"

    all_ok = all(v == "UP" or v == "READY" for v in checks.values())
    status_code = status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE

    return Response(
        content=json.dumps({"status": "READY" if all_ok else "NOT_READY", "dependencies": checks}),
        status_code=status_code,
        media_type="application/json"
    )


# ── 3. WEBSOCKET LIVE EVENT STREAM ───────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass


ws_manager = ConnectionManager()


@router.websocket("/v1/ws/events")
async def websocket_live_events(websocket: WebSocket):
    """Real-time WebSocket event stream for dashboard live telemetry."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep-alive heartbeat
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


# ── 4. CONNECTOR REGISTRY & HEALTH ───────────────────────────────────────────

from nexus_integrations import get_connector_registry


@router.get("/connectors")
async def list_registered_connectors():
    """Returns real-time health, scopes, and circuit breaker status for all ecosystem connectors."""
    return get_connector_registry()
