"""Resilient Event Stream Ingestion, Deduplication, and Priority Routing for CORTEX.

Provides:
- EventDeduplicator: Rolling sliding-window deduplication by event_id and payload hash
- PriorityEventRouter: Multi-tier prioritization classifying telemetry into P0-P3 priority queues
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger("cortex-upgrade.event-stream")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PriorityLevel(int, Enum):
    P0_CRITICAL = 0
    P1_HIGH = 1
    P2_STANDARD = 2
    P3_BACKGROUND = 3


class EventDeduplicator:
    """Sliding-window deduplication preventing duplicate event ingestion.

    Guarantees idempotency across transient network retries and duplicate stream deliveries.
    Maintains bounded memory by purging records older than window_seconds.
    """

    def __init__(self, window_seconds: float = 300.0, max_entries: int = 50000) -> None:
        self.window_seconds = max(0.01, window_seconds)
        self.max_entries = max_entries
        self._seen_ids: OrderedDict[str, datetime] = OrderedDict()
        self._seen_hashes: OrderedDict[str, datetime] = OrderedDict()
        self._lock = asyncio.Lock()

    @staticmethod
    def compute_payload_hash(payload: dict[str, Any] | str) -> str:
        """Deterministic sha256 of canonical JSON payload."""
        if isinstance(payload, str):
            raw = payload.strip()
        else:
            raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def is_duplicate(
        self, event_id: str | None, payload_hash: str | None = None
    ) -> bool:
        """Check if event_id or payload_hash has been processed within the sliding window."""
        now = _utcnow()
        cutoff = now - timedelta(seconds=self.window_seconds)

        async with self._lock:
            if event_id and event_id in self._seen_ids:
                if self._seen_ids[event_id] > cutoff:
                    return True
                del self._seen_ids[event_id]

            if payload_hash and payload_hash in self._seen_hashes:
                if self._seen_hashes[payload_hash] > cutoff:
                    return True
                del self._seen_hashes[payload_hash]

            return False

    async def record(
        self, event_id: str | None, payload_hash: str | None = None
    ) -> None:
        """Record event arrival timestamp to suppress subsequent duplicates."""
        now = _utcnow()
        async with self._lock:
            if event_id:
                self._seen_ids[event_id] = now
                if len(self._seen_ids) > self.max_entries:
                    self._seen_ids.popitem(last=False)

            if payload_hash:
                self._seen_hashes[payload_hash] = now
                if len(self._seen_hashes) > self.max_entries:
                    self._seen_hashes.popitem(last=False)

    async def check_and_record(
        self, event_id: str | None, payload_hash: str | None = None
    ) -> bool:
        """Atomically test and record. Returns True if duplicate, False if newly recorded."""
        now = _utcnow()
        cutoff = now - timedelta(seconds=self.window_seconds)

        async with self._lock:
            if event_id and event_id in self._seen_ids:
                if self._seen_ids[event_id] > cutoff:
                    return True
                del self._seen_ids[event_id]

            if payload_hash and payload_hash in self._seen_hashes:
                if self._seen_hashes[payload_hash] > cutoff:
                    return True
                del self._seen_hashes[payload_hash]

            # Record
            if event_id:
                self._seen_ids[event_id] = now
                if len(self._seen_ids) > self.max_entries:
                    self._seen_ids.popitem(last=False)
            if payload_hash:
                self._seen_hashes[payload_hash] = now
                if len(self._seen_hashes) > self.max_entries:
                    self._seen_hashes.popitem(last=False)

            return False

    async def cleanup_expired(self) -> int:
        """Purge entries older than window_seconds."""
        cutoff = _utcnow() - timedelta(seconds=self.window_seconds)
        purged = 0

        async with self._lock:
            for k in list(self._seen_ids.keys()):
                if self._seen_ids[k] <= cutoff:
                    del self._seen_ids[k]
                    purged += 1
                else:
                    break

            for h in list(self._seen_hashes.keys()):
                if self._seen_hashes[h] <= cutoff:
                    del self._seen_hashes[h]
                    purged += 1
                else:
                    break

        return purged

    async def size(self) -> tuple[int, int]:
        async with self._lock:
            return len(self._seen_ids), len(self._seen_hashes)


class PriorityEventRouter:
    """Classifies telemetry and command events into prioritized tiers."""

    CRITICAL_KEYWORDS = frozenset([
        "incident",
        "slo_breach",
        "payment_failed",
        "charge.failed",
        "security_alert",
        "pii_quarantine",
        "isolation_breach",
        "ddos",
        "brute_force",
    ])

    HIGH_INTENT_KEYWORDS = frozenset([
        "checkout",
        "demo_request",
        "pricing_cta",
        "quote_requested",
        "contract_sign",
        "qualified_lead",
        "enterprise_inquiry",
    ])

    BACKGROUND_KEYWORDS = frozenset([
        "heartbeat",
        "health_check",
        "ping",
        "worker_keepalive",
    ])

    @classmethod
    def classify(cls, event_type: str, data: dict[str, Any] | None = None) -> PriorityLevel:
        e = event_type.lower()
        payload_str = str(data or {}).lower()

        if any(kw in e or kw in payload_str for kw in cls.CRITICAL_KEYWORDS):
            return PriorityLevel.P0_CRITICAL

        if any(kw in e or kw in payload_str for kw in cls.HIGH_INTENT_KEYWORDS):
            return PriorityLevel.P1_HIGH

        if any(kw in e for kw in cls.BACKGROUND_KEYWORDS):
            return PriorityLevel.P3_BACKGROUND

        return PriorityLevel.P2_STANDARD
