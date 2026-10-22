from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from .models import Approval, ToolCall


class ApprovalSigner:
    """HMAC-SHA256 signature generator and verifier for closed-loop tool approvals."""

    DEFAULT_SECRET = os.getenv("CORTEX_APPROVAL_SECRET", "cortex-closed-loop-approval-secret-key-32b")

    @classmethod
    def generate_signature(cls, approval: Approval, secret: str | None = None) -> str:
        sec = secret or cls.DEFAULT_SECRET
        payload = f"{approval.approval_id}:{approval.tenant_id}:{approval.call_id}:{approval.approved}:{approval.decided_by}"
        return hmac.new(sec.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

    @classmethod
    def verify_signature(cls, approval: Approval, signature: str | None = None, secret: str | None = None) -> bool:
        sig = signature or approval.signature
        if not sig:
            return False
        expected = cls.generate_signature(approval, secret)
        return hmac.compare_digest(expected, sig)



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
            approval_id=uuid4(),
            tenant_id=tenant_id,
            principal_id=principal_id,
            tool_name=call.tool_name,
            call_id=call.call_id,
            approved=False,
            decided_by="",
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
            # A decision is terminal: replaying the same decision is idempotent, but a
            # conflicting one must be refused. Without this, an approved high-impact tool
            # call could be flipped to rejected (or back) after the fact.
            if item.approval.decided_by:
                if item.approval.approved != approved:
                    raise ValueError(
                        f"approval already {item.approval.decided_by and ('approved' if item.approval.approved else 'rejected')}"
                    )
                return item.approval
            temp_record = Approval(
                approval_id=item.approval.approval_id,
                tenant_id=item.approval.tenant_id,
                principal_id=item.approval.principal_id,
                tool_name=item.approval.tool_name,
                call_id=item.approval.call_id,
                approved=approved,
                decided_by=approver,
                reason=reason,
            )
            sig = ApprovalSigner.generate_signature(temp_record)
            approved_record = Approval(
                approval_id=item.approval.approval_id,
                tenant_id=item.approval.tenant_id,
                principal_id=item.approval.principal_id,
                tool_name=item.approval.tool_name,
                call_id=item.approval.call_id,
                approved=approved,
                decided_by=approver,
                reason=reason,
                signature=sig,
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
