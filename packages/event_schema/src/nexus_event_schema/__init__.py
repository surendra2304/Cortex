from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ActorType(str, Enum):
    VISITOR = "visitor"
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class Actor(BaseModel):
    type: ActorType = Field(default=ActorType.VISITOR, description="Type of actor generating or associated with the event")
    id: str = Field(..., description="Unique identifier for the actor")


class EventSchema(BaseModel):
    event_id: str = Field(..., description="Globally unique identifier for the event")
    tenant_id: str = Field(..., description="Tenant identifier to enforce strict multi-tenant isolation")
    site_id: str = Field(..., description="Target site/application identifier")
    type: str = Field(..., description="Categorical event type name (e.g. page_view, click, form_submit, agent_action)")
    occurred_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp when event occurred in ISO 8601")
    actor: Actor = Field(..., description="Actor entity generating the event")
    session_id: Optional[str] = Field(default=None, description="Optional associated session ID")
    source: str = Field(default="web", description="Event ingestion source (e.g. web, mobile, api, webhook, worker)")
    data: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary payload and contextual attributes")
    consent: Optional[Dict[str, Any]] = Field(default=None, description="GDPR/CCPA/privacy consent parameters and flags")
    trace_id: Optional[str] = Field(default=None, description="Distributed tracing identifier for cross-service observability")


class IngestEventResponse(BaseModel):
    status: str = "accepted"
    event_id: str
    processed_at: datetime = Field(default_factory=datetime.utcnow)
