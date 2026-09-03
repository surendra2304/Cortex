from __future__ import annotations
import asyncio
from datetime import UTC, datetime
from uuid import uuid4
from .models import AuditEvent

SECRET_WORDS = {"authorization", "api_key", "token", "secret", "password", "cookie", "credential"}

def redact(value):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if k.lower() in SECRET_WORDS else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value

class AuditLog:
    def __init__(self) -> None:
        self._rows: list[AuditEvent] = []
        self._lock = asyncio.Lock()

    async def append(self, tenant_id, principal_id, request_id, action, resource, outcome, reason="", metadata=None):
        record = AuditEvent(uuid4(), tenant_id, principal_id, action, resource, outcome, request_id,
                            reason, redact(metadata or {}), datetime.now(UTC))
        async with self._lock:
            self._rows.append(record)
        return record

    async def query(self, tenant_id, limit=100):
        async with self._lock:
            rows = [r for r in self._rows if r.tenant_id == tenant_id]
            return list(reversed(rows[-limit:]))
