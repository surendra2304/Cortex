"""Dead Letter Queue (DLQ) & Quarantine Triage Engine for CORTEX.

Isolates poisoned, permanently unparseable, or persistently failing stream events:
- Retains full delivery and error telemetry (attempts, stack trace, original stream ID)
- Provides safe inspection and diagnostic queries strictly isolated by tenant_id
- Enables controlled operator replay through custom async handlers
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from .models import FailureKind

logger = logging.getLogger("cortex-upgrade.dlq")


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class PoisonMessage:
    message_id: str
    stream_id: str
    tenant_id: str
    payload: dict[str, Any]
    failure_kind: str
    error_details: str
    delivery_attempts: int
    quarantined_at: datetime = field(default_factory=_utcnow)
    reprocessed: bool = False
    reprocessed_at: datetime | None = None
    reprocess_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["quarantined_at"] = self.quarantined_at.isoformat()
        if self.reprocessed_at:
            d["reprocessed_at"] = self.reprocessed_at.isoformat()
        return d


class DeadLetterQueue:
    """In-memory tenant-isolated dead letter queue for stream triage and safe recovery."""

    def __init__(self, max_messages_per_tenant: int = 1000) -> None:
        self.max_messages_per_tenant = max_messages_per_tenant
        self._messages: dict[str, dict[str, PoisonMessage]] = {}  # tenant_id -> {msg_id: msg}
        self._lock = asyncio.Lock()

    async def quarantine(
        self,
        stream_id: str,
        tenant_id: str,
        payload: dict[str, Any],
        failure_kind: str | FailureKind,
        error_details: str,
        delivery_attempts: int = 5,
    ) -> PoisonMessage:
        """Quarantine a poisoned message for operator inspection."""
        msg_id = f"dlq_{uuid.uuid4().hex[:12]}"
        kind_str = failure_kind.value if isinstance(failure_kind, FailureKind) else str(failure_kind)

        msg = PoisonMessage(
            message_id=msg_id,
            stream_id=stream_id,
            tenant_id=tenant_id,
            payload=payload,
            failure_kind=kind_str,
            error_details=error_details,
            delivery_attempts=delivery_attempts,
        )

        async with self._lock:
            tenant_store = self._messages.setdefault(tenant_id, {})
            tenant_store[msg_id] = msg

            # Enforce bounded size
            if len(tenant_store) > self.max_messages_per_tenant:
                # Remove oldest
                oldest_key = next(iter(tenant_store))
                del tenant_store[oldest_key]

        logger.warning(
            f"Quarantined poison message '{msg_id}' for tenant '{tenant_id}' "
            f"(stream_id='{stream_id}', attempts={delivery_attempts}): {error_details[:100]}"
        )
        return msg

    async def get_message(self, message_id: str, tenant_id: str) -> PoisonMessage | None:
        """Retrieve a quarantined message enforcing strict tenant scoping."""
        async with self._lock:
            tenant_store = self._messages.get(tenant_id, {})
            return tenant_store.get(message_id)

    async def list_messages(
        self,
        tenant_id: str,
        include_reprocessed: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PoisonMessage]:
        """List quarantined messages for a specific tenant."""
        async with self._lock:
            tenant_store = self._messages.get(tenant_id, {})
            items = list(tenant_store.values())

        if not include_reprocessed:
            items = [m for m in items if not m.reprocessed]

        # Sort newest first
        items.sort(key=lambda m: m.quarantined_at, reverse=True)
        return items[offset : offset + limit]

    async def reprocess(
        self,
        message_id: str,
        tenant_id: str,
        processor: Callable[[dict[str, Any]], Awaitable[bool]],
    ) -> tuple[bool, str]:
        """Attempt safe replay of a quarantined message through a supplied processor."""
        async with self._lock:
            tenant_store = self._messages.get(tenant_id, {})
            msg = tenant_store.get(message_id)
            if not msg:
                return False, "message not found"

        try:
            success = await processor(msg.payload)
            now = _utcnow()
            async with self._lock:
                if success:
                    msg.reprocessed = True
                    msg.reprocessed_at = now
                    msg.reprocess_error = None
                    return True, "successfully reprocessed"
                else:
                    msg.reprocess_error = "processor returned False"
                    return False, "processor returned False"
        except Exception as exc:
            err_msg = f"{type(exc).__name__}: {exc}"
            logger.exception(f"Failed to reprocess message '{message_id}': {err_msg}")
            async with self._lock:
                msg.reprocess_error = err_msg
            return False, err_msg

    async def purge(self, message_id: str, tenant_id: str) -> bool:
        """Permanently delete a message from quarantine."""
        async with self._lock:
            tenant_store = self._messages.get(tenant_id, {})
            if message_id in tenant_store:
                del tenant_store[message_id]
                return True
            return False

    async def metrics(self, tenant_id: str | None = None) -> dict[str, Any]:
        """Summary metrics across quarantined messages."""
        async with self._lock:
            if tenant_id:
                store = self._messages.get(tenant_id, {})
                total = len(store)
                reprocessed = sum(1 for m in store.values() if m.reprocessed)
                pending = total - reprocessed
                return {
                    "tenant_id": tenant_id,
                    "total_quarantined": total,
                    "pending_triage": pending,
                    "reprocessed": reprocessed,
                }

            all_msgs = [m for t in self._messages.values() for m in t.values()]
            total = len(all_msgs)
            reprocessed = sum(1 for m in all_msgs if m.reprocessed)
            return {
                "total_quarantined": total,
                "pending_triage": total - reprocessed,
                "reprocessed": reprocessed,
                "tenants_with_poison_events": len(self._messages),
            }

    async def clear(self) -> None:
        async with self._lock:
            self._messages.clear()


# Global singleton instance
global_dlq = DeadLetterQueue()
