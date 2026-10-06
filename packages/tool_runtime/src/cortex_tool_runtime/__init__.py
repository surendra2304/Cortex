import inspect
import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timezone
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable

import redis.asyncio as aioredis
from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Timezone-aware UTC now (never a naive timestamp)."""
    return datetime.now(UTC)


logger = logging.getLogger("cortex-tool-runtime")


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
    CALENDAR_BOOK = "calendar_book"


class Tool(BaseModel):
    name: str = Field(..., description="Unique tool identifier")
    version: str = Field(default="1.0.0", description="Semantic version of the tool contract")
    description: str = Field(default="", description="Tool documentation for agent planning")
    capabilities: list[ToolCapability] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict, description="JSON Schema for invocation parameters")
    side_effect_level: SideEffectLevel = Field(default=SideEffectLevel.READ)
    auth_scope: str = Field(default="system:internal", description="Required OAuth/IAM authorization scope")
    rate_limit: int = Field(default=60, description="Max invocations permitted per minute")
    idempotency_strategy: IdempotencyStrategy = Field(default=IdempotencyStrategy.IDEMPOTENCY_KEY)


class PolicyDecision(BaseModel):
    approved: bool
    requires_human_approval: bool = False
    reason: str
    risk_score: float = 0.0
    evaluated_at: datetime = Field(default_factory=_utcnow)


class Execution(BaseModel):
    request_id: str = Field(..., description="Unique correlation ID for tool execution")
    tool_name: str = Field(..., description="Target tool name")
    actor: dict[str, Any] = Field(..., description="Actor entity invoking the tool")
    reason: str = Field(..., description="Justification or intent behind tool invocation")
    params: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None
    policy_decision: PolicyDecision | None = None
    approval: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    verification: dict[str, Any] | None = None
    audit_record: dict[str, Any] | None = None
    executed_at: datetime | None = None


@runtime_checkable
class BaseToolExecutor(Protocol):
    async def execute(self, params: dict[str, Any], execution_context: Execution | None = None) -> dict[str, Any]: ...


class ToolBus:
    """Dynamic Tool Registry and Execution Dispatcher with Idempotency & Rate-Limiting."""

    def __init__(self, redis_client: aioredis.Redis | None = None):
        self._tools: dict[str, Tool] = {}
        self._executors: dict[str, Any] = {}
        self.redis_client = redis_client
        self.execution_history: list[dict[str, Any]] = []
        # Single-process fallback used only when no Redis client is configured.
        # It is honest about its scope: keys expire per TTL and are not shared
        # across replicas, which the audit record surfaces as "local".
        self._local_idempotency: dict[str, float] = {}

    def register_tool(self, tool: Tool, executor: Any) -> None:
        self._tools[tool.name] = tool
        self._executors[tool.name] = executor
        logger.info(f"Registered tool '{tool.name}' (side_effect_level={tool.side_effect_level}).")

    def get_tool(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    async def _check_and_set_idempotency(self, idempotency_key: str, ttl_seconds: int = 86400) -> str:
        """Reserve an idempotency key.

        Returns ``"first"``, ``"duplicate"``, or ``"unavailable"``.

        Audit defect H7: a Redis error used to return ``True`` ("allowing
        execution to proceed"), which is exactly the wrong default for a
        guard whose purpose is to prevent duplicate side effects. The caller now
        decides based on the tool's side-effect level, and HIGH_IMPACT /
        DANGEROUS tools fail closed.
        """
        if not self.redis_client:
            now = time.time()
            self._local_idempotency = {k: v for k, v in self._local_idempotency.items() if v > now}
            if idempotency_key in self._local_idempotency:
                return "duplicate"
            self._local_idempotency[idempotency_key] = now + ttl_seconds
            logger.warning(
                "No Redis client configured: idempotency for key '%s' is enforced in-process only "
                "(single-replica guarantee).",
                idempotency_key,
            )
            return "local"
        try:
            was_set = await self.redis_client.set(f"idempotency:{idempotency_key}", "locked", nx=True, ex=ttl_seconds)
            return "first" if was_set else "duplicate"
        except Exception as exc:
            logger.warning(f"Idempotency store unavailable ({exc}).")
            return "unavailable"

    async def execute(
        self, tool_name: str, params: dict[str, Any], execution: Execution | None = None
    ) -> dict[str, Any]:
        tool = self._tools.get(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not registered in ToolBus.")

        idempotency_key = (
            execution.idempotency_key if execution and execution.idempotency_key else params.get("idempotency_key")
        )

        idempotency_status: str | None = None
        if idempotency_key and tool.idempotency_strategy != IdempotencyStrategy.NONE:
            idempotency_status = await self._check_and_set_idempotency(idempotency_key)
            if idempotency_status == "duplicate":
                logger.info(f"Duplicate execution blocked for tool '{tool_name}' with key '{idempotency_key}'.")
                return {
                    "status": "skipped",
                    "reason": "duplicate_idempotent_request",
                    "idempotency_key": idempotency_key,
                    "tool": tool_name,
                    "executed_at": datetime.now(UTC).isoformat(),
                }
            if idempotency_status in {"unavailable", "local"} and tool.side_effect_level in {
                SideEffectLevel.HIGH_IMPACT,
                SideEffectLevel.DANGEROUS,
            }:
                logger.error(
                    "Refusing to execute %s tool '%s': idempotency guard status is '%s'.",
                    tool.side_effect_level.value,
                    tool_name,
                    idempotency_status,
                )
                if execution:
                    execution.error = "idempotency_guard_unavailable"
                    execution.verification = {
                        "status": "blocked",
                        "reason": "idempotency_guard_unavailable",
                        "side_effect_level": tool.side_effect_level.value,
                    }
                return {
                    "status": "blocked",
                    "reason": "idempotency_guard_unavailable",
                    "side_effect_level": tool.side_effect_level.value,
                    "tool": tool_name,
                    "idempotency_key": idempotency_key,
                    "executed_at": datetime.now(UTC).isoformat(),
                }

        executor = self._executors.get(tool_name)
        if not executor:
            raise ValueError(f"No executor registered for tool '{tool_name}'.")

        try:
            start_time = datetime.now(UTC)

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

            executed_at = datetime.now(UTC)

            # Verification honesty (audit defect H7): reaching this line means the
            # executor returned without raising — that is "executed", not
            # "verified". A provider-confirmed verification is only recorded when
            # the executor itself reports one.
            provider_verified = None
            if isinstance(result, dict):
                provider_verified = result.get("verified")
            if provider_verified is True:
                verification = {"status": "verified", "source": "executor", "timestamp": executed_at.isoformat()}
            elif provider_verified is False:
                verification = {"status": "unverified", "source": "executor", "timestamp": executed_at.isoformat()}
            else:
                verification = {
                    "status": "executed",
                    "source": "tool_bus",
                    "detail": "executor returned without error; no provider-side verification reported",
                    "timestamp": executed_at.isoformat(),
                }
            if idempotency_status in {"unavailable", "local"}:
                verification["idempotency"] = f"{idempotency_status}_degraded"

            exec_record = {
                "tool": tool_name,
                "status": "success",
                "params": params,
                "result": result,
                "started_at": start_time.isoformat(),
                "executed_at": executed_at.isoformat(),
                "idempotency_key": idempotency_key,
            }
            self.execution_history.append(exec_record)

            if execution:
                execution.result = result
                execution.executed_at = executed_at
                execution.verification = verification

            return {
                "status": "success",
                "tool": tool_name,
                "executed_at": executed_at.isoformat(),
                "verification": verification,
                "result": result,
            }

        except Exception as exc:
            logger.error(f"Execution failed for tool '{tool_name}': {exc}")
            if execution:
                execution.error = str(exc)
                execution.verification = {"status": "failed", "error": str(exc)}
            raise
