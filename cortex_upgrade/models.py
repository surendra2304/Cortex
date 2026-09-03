from __future__ import annotations
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

def utc_now() -> datetime:
    return datetime.now(UTC)

class SideEffect(str, Enum):
    READ = "read"
    SENSITIVE = "sensitive"
    HIGH_IMPACT = "high_impact"
    FORBIDDEN = "forbidden"

class JobState(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

class FailureKind(str, Enum):
    TRANSIENT = "transient"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    AUTHENTICATION = "authentication"
    INVALID = "invalid"
    POLICY = "policy"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PERSISTENCE = "persistence"
    UNKNOWN = "unknown"

@dataclass(frozen=True)
class Principal:
    principal_id: str
    tenant_id: str
    roles: frozenset[str] = frozenset()
    scopes: frozenset[str] = frozenset()
    credential_id: str | None = None

@dataclass(frozen=True)
class RequestContext:
    request_id: str
    principal: Principal
    idempotency_key: str | None = None

@dataclass(frozen=True)
class ToolCall:
    call_id: UUID
    tool_name: str
    args: dict[str, Any]
    side_effect: SideEffect
    scopes: frozenset[str] = frozenset()
    approval_required: bool = True

@dataclass(frozen=True)
class ToolResult:
    call_id: UUID
    tool_name: str
    ok: bool
    output: Any = None
    failure: FailureKind | None = None
    retryable: bool = False
    verified: bool = False

@dataclass(frozen=True)
class Approval:
    approval_id: UUID
    tenant_id: str
    principal_id: str
    tool_name: str
    call_id: UUID
    approved: bool
    decided_by: str
    decided_at: datetime = field(default_factory=utc_now)
    reason: str = ""

@dataclass(frozen=True)
class AuditEvent:
    event_id: UUID
    tenant_id: str
    principal_id: str
    action: str
    resource: str
    outcome: str
    request_id: str
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
