from __future__ import annotations
import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any

class IdempotencyConflict(RuntimeError):
    pass

@dataclass(frozen=True)
class IdempotentResponse:
    key: str
    fingerprint: str
    status_code: int
    body: Any

class IdempotencyStore:
    def __init__(self) -> None:
        self._records: dict[str, IdempotentResponse] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def fingerprint(payload: Any) -> str:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        return hashlib.sha256(raw).hexdigest()

    async def begin(self, key: str, payload: Any) -> IdempotentResponse | None:
        if not key:
            raise ValueError("idempotency key required")
        fp = self.fingerprint(payload)
        async with self._lock:
            existing = self._records.get(key)
            if existing and existing.fingerprint != fp:
                raise IdempotencyConflict("same key used with different payload")
            return existing

    async def commit(self, key: str, payload: Any, status_code: int, body: Any) -> IdempotentResponse:
        rec = IdempotentResponse(key, self.fingerprint(payload), status_code, body)
        async with self._lock:
            self._records[key] = rec
        return rec
