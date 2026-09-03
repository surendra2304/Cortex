from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TenantStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING = "pending"


class Tenant(BaseModel):
    id: str = Field(..., description="Unique tenant identifier")
    name: str = Field(..., description="Tenant name")
    status: TenantStatus = Field(default=TenantStatus.ACTIVE)
    config: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Site(BaseModel):
    id: str = Field(..., description="Unique site identifier")
    tenant_id: str = Field(..., description="Parent tenant ID")
    domain: str = Field(..., description="Primary domain name")
    name: str = Field(..., description="Site friendly name")
    settings: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Visitor(BaseModel):
    id: str = Field(..., description="Anonymous visitor identifier")
    tenant_id: str = Field(..., description="Tenant ID")
    site_id: str = Field(..., description="Site ID")
    first_seen_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen_at: datetime = Field(default_factory=datetime.utcnow)
    attributes: Dict[str, Any] = Field(default_factory=dict)


class Session(BaseModel):
    id: str = Field(..., description="Session identifier")
    tenant_id: str = Field(..., description="Tenant ID")
    site_id: str = Field(..., description="Site ID")
    visitor_id: str = Field(..., description="Visitor ID")
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Event(BaseModel):
    id: str = Field(..., description="Event ID")
    tenant_id: str = Field(..., description="Tenant ID")
    site_id: str = Field(..., description="Site ID")
    session_id: Optional[str] = None
    type: str = Field(..., description="Event type name")
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    actor_type: str = Field(default="visitor")
    actor_id: str = Field(..., description="Actor ID")
    source: str = Field(default="web")
    data: Dict[str, Any] = Field(default_factory=dict)
    consent: Optional[Dict[str, Any]] = None
    trace_id: Optional[str] = None


class Profile(BaseModel):
    id: str = Field(..., description="Unified profile ID")
    tenant_id: str = Field(..., description="Tenant ID")
    primary_email: Optional[str] = None
    identities: List[Dict[str, Any]] = Field(default_factory=list)
    traits: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Account(BaseModel):
    id: str = Field(..., description="B2B Account/Organization ID")
    tenant_id: str = Field(..., description="Tenant ID")
    name: str = Field(..., description="Account company name")
    domain: Optional[str] = None
    tier: Optional[str] = "standard"
    custom_fields: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Conversation(BaseModel):
    id: str = Field(..., description="Conversation ID")
    tenant_id: str = Field(..., description="Tenant ID")
    site_id: str = Field(..., description="Site ID")
    session_id: Optional[str] = None
    visitor_id: Optional[str] = None
    channel: str = Field(default="chat")
    status: str = Field(default="open")
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Lead(BaseModel):
    id: str = Field(..., description="Lead ID")
    tenant_id: str = Field(..., description="Tenant ID")
    profile_id: Optional[str] = None
    score: float = Field(default=0.0)
    status: str = Field(default="new")
    source: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Opportunity(BaseModel):
    id: str = Field(..., description="Opportunity ID")
    tenant_id: str = Field(..., description="Tenant ID")
    account_id: Optional[str] = None
    lead_id: Optional[str] = None
    value: float = Field(default=0.0)
    stage: str = Field(default="discovery")
    probability: float = Field(default=0.1)
    closed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Customer(BaseModel):
    id: str = Field(..., description="Customer ID")
    tenant_id: str = Field(..., description="Tenant ID")
    account_id: Optional[str] = None
    profile_id: Optional[str] = None
    status: str = Field(default="active")
    plan: str = Field(default="free")
    mrr: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Workflow(BaseModel):
    id: str = Field(..., description="Workflow ID")
    tenant_id: str = Field(..., description="Tenant ID")
    name: str = Field(..., description="Workflow Name")
    trigger: Dict[str, Any] = Field(..., description="Trigger definition")
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Action(BaseModel):
    id: str = Field(..., description="Action ID")
    tenant_id: str = Field(..., description="Tenant ID")
    workflow_id: Optional[str] = None
    action_type: str = Field(..., description="Type of action executed")
    params: Dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="pending")
    result: Optional[Dict[str, Any]] = None
    executed_at: Optional[datetime] = None


class Experiment(BaseModel):
    id: str = Field(..., description="Experiment ID")
    tenant_id: str = Field(..., description="Tenant ID")
    site_id: str = Field(..., description="Site ID")
    name: str = Field(..., description="Experiment name")
    variants: List[Dict[str, Any]] = Field(default_factory=list)
    status: str = Field(default="draft")
    traffic_allocation: float = Field(default=1.0)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class Incident(BaseModel):
    id: str = Field(..., description="Incident ID")
    tenant_id: str = Field(..., description="Tenant ID")
    severity: str = Field(default="low")
    title: str = Field(..., description="Incident title")
    description: Optional[str] = None
    status: str = Field(default="open")
    resolved_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AgentRun(BaseModel):
    id: str = Field(..., description="Agent Run ID")
    tenant_id: str = Field(..., description="Tenant ID")
    agent_name: str = Field(..., description="Agent name/identifier")
    status: str = Field(default="running")
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


class IntelligenceRequest(BaseModel):
    id: str = Field(..., description="Intelligence Request ID")
    tenant_id: str = Field(..., description="Tenant ID")
    query_type: str = Field(..., description="Reasoning / Analytics / Scoring type")
    payload: Dict[str, Any] = Field(default_factory=dict)
    response: Optional[Dict[str, Any]] = None
    latency_ms: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Memory(BaseModel):
    id: str = Field(..., description="Memory record ID")
    tenant_id: str = Field(..., description="Tenant ID")
    entity_type: str = Field(..., description="Target entity type: visitor, profile, session, etc.")
    entity_id: str = Field(..., description="Target entity ID")
    key: str = Field(..., description="Memory key")
    value: Any = Field(..., description="Stored memory value")
    embedding: Optional[List[float]] = None
    ttl: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AuditRecord(BaseModel):
    id: str = Field(..., description="Audit record ID")
    tenant_id: str = Field(..., description="Tenant ID")
    actor_id: str = Field(..., description="User or agent that performed the action")
    action: str = Field(..., description="Operation performed")
    target_resource: str = Field(..., description="Target resource type and ID")
    changes: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
