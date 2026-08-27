from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field


class SideEffectLevel(str, Enum):
    READ = "READ"
    SENSITIVE = "SENSITIVE"
    HIGH_IMPACT = "HIGH_IMPACT"
    DANGEROUS = "DANGEROUS"


class IdempotencyStrategy(str, Enum):
    NONE = "none"
    IDEMPOTENCY_KEY = "idempotency_key"
    EXACT_PAYLOAD_HASH = "exact_payload_hash"


class ToolCapability(str, Enum):
    ANALYTICS_QUERY = "analytics_query"
    SESSION_INSPECT = "session_inspect"
    EMAIL_DISPATCH = "email_dispatch"
    BANNER_INJECTION = "banner_injection"
    EXPERIMENT_MUTATE = "experiment_mutate"
    ACCOUNT_UPDATE = "account_update"
    WORKFLOW_TRIGGER = "workflow_trigger"


class Tool(BaseModel):
    name: str = Field(..., description="Unique tool identifier")
    version: str = Field(default="1.0.0", description="Semantic version of the tool contract")
    description: str = Field(default="", description="Tool documentation for agent planning")
    capabilities: List[ToolCapability] = Field(default_factory=list)
    input_schema: Dict[str, Any] = Field(default_factory=dict, description="JSON Schema for invocation parameters")
    side_effect_level: SideEffectLevel = Field(default=SideEffectLevel.READ)
    auth_scope: str = Field(default="system:internal", description="Required OAuth/IAM authorization scope")
    rate_limit: int = Field(default=60, description="Max invocations permitted per minute")
    idempotency_strategy: IdempotencyStrategy = Field(default=IdempotencyStrategy.IDEMPOTENCY_KEY)


class PolicyDecision(BaseModel):
    approved: bool
    requires_human_approval: bool = False
    reason: str
    risk_score: float = 0.0
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)


class Execution(BaseModel):
    request_id: str = Field(..., description="Unique correlation ID for tool execution")
    tool_name: str = Field(..., description="Target tool name")
    actor: Dict[str, Any] = Field(..., description="Actor entity invoking the tool e.g. {'type': 'agent', 'id': 'lead_agent'}")
    reason: str = Field(..., description="Justification or intent behind tool invocation")
    params: Dict[str, Any] = Field(default_factory=dict)
    policy_decision: Optional[PolicyDecision] = None
    approval: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    verification: Optional[Dict[str, Any]] = None
    audit_record: Optional[Dict[str, Any]] = None
    executed_at: Optional[datetime] = None


@runtime_checkable
class BaseToolExecutor(Protocol):
    async def execute(self, execution: Execution, tool: Tool) -> Dict[str, Any]:
        ...
