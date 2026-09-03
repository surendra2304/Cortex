from __future__ import annotations
import asyncio
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

class EventRejected(ValueError):
    pass

@dataclass(frozen=True)
class CanonicalEvent:
    event_id: str
    tenant_id: str
    site_id: str
    event_type: str
    occurred_at: datetime
    received_at: datetime
    actor_id: str | None
    consent: dict[str, bool]
    data: dict[str, Any]
    trace_id: str

class EventNormalizer:
    def normalize(self, raw: dict[str, Any], received_at: datetime | None = None) -> CanonicalEvent:
        received_at = received_at or datetime.now(UTC)
        required = ("event_id", "tenant_id", "site_id", "type", "occurred_at", "consent")
        missing = [key for key in required if not raw.get(key)]
        if missing:
            raise EventRejected(f"missing fields: {missing}")
        occurred = raw["occurred_at"]
        if isinstance(occurred, str):
            occurred = datetime.fromisoformat(occurred.replace("Z", "+00:00"))
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=UTC)
        else:
            occurred = occurred.astimezone(UTC)
        if occurred > received_at:
            raise EventRejected("future event timestamp")
        if not isinstance(raw["consent"], dict):
            raise EventRejected("consent must be an object")
        actor = raw.get("actor")
        trace = str(raw.get("trace_id") or hashlib.sha256(str(raw["event_id"]).encode()).hexdigest()[:16])
        return CanonicalEvent(
            event_id=str(raw["event_id"]),
            tenant_id=str(raw["tenant_id"]),
            site_id=str(raw["site_id"]),
            event_type=str(raw["type"]),
            occurred_at=occurred,
            received_at=received_at,
            actor_id=str(actor["id"]) if isinstance(actor, dict) and actor.get("id") else None,
            consent={str(k): bool(v) for k, v in raw["consent"].items()},
            data=dict(raw.get("data") or {}),
            trace_id=trace,
        )

class EventDedupeStore:
    def __init__(self) -> None:
        self._seen: set[tuple[str, str]] = set()
        self._lock = asyncio.Lock()

    async def claim(self, tenant_id: str, event_id: str) -> bool:
        key = (tenant_id, event_id)
        async with self._lock:
            if key in self._seen:
                return False
            self._seen.add(key)
            return True
