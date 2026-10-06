from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Timezone-aware UTC now (never a naive timestamp)."""
    return datetime.now(UTC)


class TenantStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING = "pending"


class Tenant(BaseModel):
    id: str = Field(..., description="Unique tenant identifier")
    name: str = Field(..., description="Tenant name")
    status: TenantStatus = Field(default=TenantStatus.ACTIVE)
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Site(BaseModel):
    id: str = Field(..., description="Unique site identifier")
    tenant_id: str = Field(..., description="Parent tenant ID")
    domain: str = Field(..., description="Primary domain name")
    name: str = Field(..., description="Site friendly name")
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Visitor(BaseModel):
    id: str = Field(..., description="Anonymous visitor identifier")
    tenant_id: str = Field(..., description="Tenant ID")
    site_id: str = Field(..., description="Site ID")
    first_seen_at: datetime = Field(default_factory=_utcnow)
    last_seen_at: datetime = Field(default_factory=_utcnow)
    attributes: dict[str, Any] = Field(default_factory=dict)


class Session(BaseModel):
    id: str = Field(..., description="Session identifier")
    tenant_id: str = Field(..., description="Tenant ID")
    site_id: str = Field(..., description="Site ID")
    visitor_id: str = Field(..., description="Visitor ID")
    user_agent: str | None = None
    ip_address: str | None = None
    started_at: datetime = Field(default_factory=_utcnow)
    ended_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Event(BaseModel):
    id: str = Field(..., description="Event ID")
    tenant_id: str = Field(..., description="Tenant ID")
    site_id: str = Field(..., description="Site ID")
    session_id: str | None = None
    type: str = Field(..., description="Event type name")
    occurred_at: datetime = Field(default_factory=_utcnow)
    actor_type: str = Field(default="visitor")
    actor_id: str = Field(..., description="Actor ID")
    source: str = Field(default="web")
    data: dict[str, Any] = Field(default_factory=dict)
    consent: dict[str, Any] | None = None
    trace_id: str | None = None


class Profile(BaseModel):
    id: str = Field(..., description="Unified profile ID")
    tenant_id: str = Field(..., description="Tenant ID")
    primary_email: str | None = None
    identities: list[dict[str, Any]] = Field(default_factory=list)
    traits: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Account(BaseModel):
    id: str = Field(..., description="B2B Account/Organization ID")
    tenant_id: str = Field(..., description="Tenant ID")
    name: str = Field(..., description="Account company name")
    domain: str | None = None
    tier: str | None = "standard"
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)


class Conversation(BaseModel):
    id: str = Field(..., description="Conversation ID")
    tenant_id: str = Field(..., description="Tenant ID")
    site_id: str = Field(..., description="Site ID")
    session_id: str | None = None
    visitor_id: str | None = None
    channel: str = Field(default="chat")
    status: str = Field(default="open")
    messages: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class Lead(BaseModel):
    id: str = Field(..., description="Lead ID")
    tenant_id: str = Field(..., description="Tenant ID")
    profile_id: str | None = None
    score: float = Field(default=0.0)
    status: str = Field(default="new")
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)


class Opportunity(BaseModel):
    id: str = Field(..., description="Opportunity ID")
    tenant_id: str = Field(..., description="Tenant ID")
    account_id: str | None = None
    lead_id: str | None = None
    value: float = Field(default=0.0)
    stage: str = Field(default="discovery")
    probability: float = Field(default=0.1)
    closed_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class Customer(BaseModel):
    id: str = Field(..., description="Customer ID")
    tenant_id: str = Field(..., description="Tenant ID")
    account_id: str | None = None
    profile_id: str | None = None
    status: str = Field(default="active")
    plan: str = Field(default="free")
    mrr: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=_utcnow)


class Workflow(BaseModel):
    id: str = Field(..., description="Workflow ID")
    tenant_id: str = Field(..., description="Tenant ID")
    name: str = Field(..., description="Workflow Name")
    trigger: dict[str, Any] = Field(..., description="Trigger definition")
    steps: list[dict[str, Any]] = Field(default_factory=list)
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_utcnow)


class Action(BaseModel):
    id: str = Field(..., description="Action ID")
    tenant_id: str = Field(..., description="Tenant ID")
    workflow_id: str | None = None
    action_type: str = Field(..., description="Type of action executed")
    params: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="pending")
    result: dict[str, Any] | None = None
    executed_at: datetime | None = None


class Experiment(BaseModel):
    id: str = Field(..., description="Experiment ID")
    tenant_id: str = Field(..., description="Tenant ID")
    site_id: str = Field(..., description="Site ID")
    name: str = Field(..., description="Experiment name")
    variants: list[dict[str, Any]] = Field(default_factory=list)
    status: str = Field(default="draft")
    traffic_allocation: float = Field(default=1.0)
    started_at: datetime | None = None
    ended_at: datetime | None = None


class Incident(BaseModel):
    id: str = Field(..., description="Incident ID")
    tenant_id: str = Field(..., description="Tenant ID")
    severity: str = Field(default="low")
    title: str = Field(..., description="Incident title")
    description: str | None = None
    status: str = Field(default="open")
    resolved_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class AgentRun(BaseModel):
    id: str = Field(..., description="Agent Run ID")
    tenant_id: str = Field(..., description="Tenant ID")
    agent_name: str = Field(..., description="Agent name/identifier")
    status: str = Field(default="running")
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None


class IntelligenceRequest(BaseModel):
    id: str = Field(..., description="Intelligence Request ID")
    tenant_id: str = Field(..., description="Tenant ID")
    query_type: str = Field(..., description="Reasoning / Analytics / Scoring type")
    payload: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] | None = None
    latency_ms: float | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class Memory(BaseModel):
    id: str = Field(..., description="Memory record ID")
    tenant_id: str = Field(..., description="Tenant ID")
    entity_type: str = Field(..., description="Target entity type: visitor, profile, session, etc.")
    entity_id: str = Field(..., description="Target entity ID")
    key: str = Field(..., description="Memory key")
    value: Any = Field(..., description="Stored memory value")
    embedding: list[float] | None = None
    ttl: int | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class AuditRecord(BaseModel):
    id: str = Field(..., description="Audit record ID")
    tenant_id: str = Field(..., description="Tenant ID")
    actor_id: str = Field(..., description="User or agent that performed the action")
    action: str = Field(..., description="Operation performed")
    target_resource: str = Field(..., description="Target resource type and ID")
    changes: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utcnow)
