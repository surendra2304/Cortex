from __future__ import annotations
import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from .models import Approval, ToolCall

@dataclass
class PendingApproval:
    approval: Approval
    expires_at: datetime

class ApprovalQueue:
    def __init__(self) -> None:
        self._items: dict[UUID, PendingApproval] = {}
        self._lock = asyncio.Lock()

    async def request(self, tenant_id: str, principal_id: str, call: ToolCall, ttl_minutes: int = 60) -> Approval:
        if ttl_minutes <= 0:
            raise ValueError("invalid approval TTL")
        approval = Approval(
            approval_id=uuid4(), tenant_id=tenant_id, principal_id=principal_id,
            tool_name=call.tool_name, call_id=call.call_id, approved=False, decided_by=""
        )
        async with self._lock:
            self._items[approval.approval_id] = PendingApproval(
                approval, datetime.now(UTC) + timedelta(minutes=ttl_minutes)
            )
        return approval

    async def decide(self, approval_id: UUID, approver: str, approved: bool, reason: str = "") -> Approval:
        async with self._lock:
            item = self._items.get(approval_id)
            if not item:
                raise KeyError("approval not found")
            if item.expires_at <= datetime.now(UTC):
                del self._items[approval_id]
                raise TimeoutError("approval expired")
            approved_record = Approval(
                approval_id=item.approval.approval_id,
                tenant_id=item.approval.tenant_id,
                principal_id=item.approval.principal_id,
                tool_name=item.approval.tool_name,
                call_id=item.approval.call_id,
                approved=approved,
                decided_by=approver,
                reason=reason,
            )
            self._items[approval_id] = PendingApproval(approved_record, item.expires_at)
            return approved_record

    async def get(self, approval_id: UUID) -> Approval | None:
        async with self._lock:
            item = self._items.get(approval_id)
            if not item:
                return None
            if item.expires_at <= datetime.now(UTC):
                del self._items[approval_id]
                return None
            return item.approval

    async def depth(self) -> int:
        async with self._lock:
            return len(self._items)
