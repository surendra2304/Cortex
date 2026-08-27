from typing import Any, Dict, List, Optional, Protocol, runtime_checkable, Callable, Awaitable
from enum import Enum
from datetime import datetime
import inspect
import json
import logging
from pydantic import BaseModel, Field
import redis.asyncio as aioredis

logger = logging.getLogger("nexus-tool-runtime")


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
    CRM_SYNC = "crm_sync"
    OUTBOUND_WEBHOOK = "outbound_webhook"
    PAYMENT_INITIATE = "payment_initiate"
    TICKETING_CREATE = "ticketing_create"


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
    actor: Dict[str, Any] = Field(..., description="Actor entity invoking the tool")
    reason: str = Field(..., description="Justification or intent behind tool invocation")
    params: Dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = None
    policy_decision: Optional[PolicyDecision] = None
    approval: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    verification: Optional[Dict[str, Any]] = None
    audit_record: Optional[Dict[str, Any]] = None
    executed_at: Optional[datetime] = None


@runtime_checkable
class BaseToolExecutor(Protocol):
    async def execute(self, params: Dict[str, Any], execution_context: Optional[Execution] = None) -> Dict[str, Any]:
        ...


class ToolBus:
    """Dynamic Tool Registry and Execution Dispatcher with Idempotency & Rate-Limiting."""

    def __init__(self, redis_client: Optional[aioredis.Redis] = None):
        self._tools: Dict[str, Tool] = {}
        self._executors: Dict[str, Any] = {}
        self.redis_client = redis_client
        self.execution_history: List[Dict[str, Any]] = []

    def register_tool(self, tool: Tool, executor: Any) -> None:
        self._tools[tool.name] = tool
        self._executors[tool.name] = executor
        logger.info(f"Registered tool '{tool.name}' (side_effect_level={tool.side_effect_level}).")

    def get_tool(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Tool]:
        return list(self._tools.values())

    async def _check_and_set_idempotency(self, idempotency_key: str, ttl_seconds: int = 86400) -> bool:
        if not self.redis_client:
            return True
        try:
            was_set = await self.redis_client.set(f"idempotency:{idempotency_key}", "locked", nx=True, ex=ttl_seconds)
            return bool(was_set)
        except Exception as exc:
            logger.warning(f"Idempotency check failed in Redis ({exc}). Allowing execution to proceed.")
            return True

    async def execute(self, tool_name: str, params: Dict[str, Any], execution: Optional[Execution] = None) -> Dict[str, Any]:
        tool = self._tools.get(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not registered in ToolBus.")

        idempotency_key = (
            execution.idempotency_key if execution and execution.idempotency_key
            else params.get("idempotency_key")
        )

        if idempotency_key:
            is_first_execution = await self._check_and_set_idempotency(idempotency_key)
            if not is_first_execution:
                logger.info(f"Duplicate execution blocked for tool '{tool_name}' with key '{idempotency_key}'.")
                return {
                    "status": "skipped",
                    "reason": "duplicate_idempotent_request",
                    "idempotency_key": idempotency_key,
                    "tool": tool_name,
                    "executed_at": datetime.utcnow().isoformat()
                }

        executor = self._executors.get(tool_name)
        if not executor:
            raise ValueError(f"No executor registered for tool '{tool_name}'.")

        try:
            start_time = datetime.utcnow()

            # Handle both async and sync executors / methods
            if hasattr(executor, "execute") and callable(executor.execute):
                if inspect.iscoroutinefunction(executor.execute):
                    result = await executor.execute(params, execution)
                else:
                    result = executor.execute(params, execution)
            elif inspect.iscoroutinefunction(executor):
                result = await executor(params, execution)
            elif callable(executor):
                result = executor(params, execution)
            else:
                raise TypeError(f"Executor for tool '{tool_name}' is not callable.")

            executed_at = datetime.utcnow()

            exec_record = {
                "tool": tool_name,
                "status": "success",
                "params": params,
                "result": result,
                "started_at": start_time.isoformat(),
                "executed_at": executed_at.isoformat(),
                "idempotency_key": idempotency_key
            }
            self.execution_history.append(exec_record)

            if execution:
                execution.result = result
                execution.executed_at = executed_at
                execution.verification = {"status": "verified", "timestamp": executed_at.isoformat()}

            return {
                "status": "success",
                "tool": tool_name,
                "executed_at": executed_at.isoformat(),
                "result": result
            }

        except Exception as exc:
            logger.error(f"Execution failed for tool '{tool_name}': {exc}")
            if execution:
                execution.error = str(exc)
                execution.verification = {"status": "failed", "error": str(exc)}
            raise
