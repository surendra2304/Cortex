from __future__ import annotations
import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

@dataclass(frozen=True)
class Memory:
    memory_id: str
    tenant_id: str
    user_id: str | None
    agent_id: str | None
    run_id: str | None
    text: str
    category: str
    importance: float
    expires_at: datetime | None = None
    metadata: dict = field(default_factory=dict)

class ScopedMemory:
    """Small reference memory boundary designed to sit in front of Memora."""
    def __init__(self) -> None:
        self._rows: dict[str, Memory] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _id(tenant_id: str, text: str) -> str:
        return hashlib.sha256(f"{tenant_id}:{text}".encode()).hexdigest()

    async def add(self, tenant_id: str, text: str, *, user_id: str | None = None,
                  agent_id: str | None = None, run_id: str | None = None,
                  category: str = "general", importance: float = .5,
                  expires_in_days: int | None = None, metadata: dict | None = None) -> Memory:
        if not any([user_id, agent_id, run_id]):
            raise ValueError("memory must have an explicit user/agent/run scope")
        if not 0 <= importance <= 1:
            raise ValueError("importance out of range")
        expiry = None if expires_in_days is None else datetime.now(UTC) + timedelta(days=expires_in_days)
        record = Memory(self._id(tenant_id, text), tenant_id, user_id, agent_id, run_id, text, category, importance, expiry, metadata or {})
        async with self._lock:
            self._rows[record.memory_id] = record
        return record

    async def search(self, tenant_id: str, query: str, *, user_id: str | None = None,
                     agent_id: str | None = None, run_id: str | None = None, limit: int = 20) -> list[Memory]:
        if not 1 <= limit <= 100:
            raise ValueError("invalid limit")
        now = datetime.now(UTC)
        needle = query.lower().strip()
        async with self._lock:
            scored: list[tuple[float, Memory]] = []
            for row in self._rows.values():
                if row.tenant_id != tenant_id or (row.expires_at and row.expires_at <= now):
                    continue
                if user_id is not None and row.user_id != user_id:
                    continue
                if agent_id is not None and row.agent_id != agent_id:
                    continue
                if run_id is not None and row.run_id != run_id:
                    continue
                lexical = 1.0 if needle and needle in row.text.lower() else .1
                scored.append((lexical * (.5 + row.importance), row))
            scored.sort(key=lambda item: item[0], reverse=True)
            return [row for _, row in scored[:limit]]
