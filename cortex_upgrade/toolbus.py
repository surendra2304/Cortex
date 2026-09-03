from __future__ import annotations
import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from .models import FailureKind, Principal, SideEffect, ToolCall, ToolResult
from .policy import PolicyEngine
from .approval import ApprovalQueue

@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    side_effect: SideEffect
    scopes: frozenset[str]
    handler: Callable[[dict[str, Any]], Awaitable[Any]]
    verify: Callable[[dict[str, Any], Any], Awaitable[bool]]
    max_attempts: int = 2

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"duplicate tool {spec.name}")
        self._tools[spec.name] = spec
    def get(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise KeyError(f"unknown tool {name}")
        return self._tools[name]

class ToolBus:
    def __init__(self, registry: ToolRegistry, policy: PolicyEngine, approvals: ApprovalQueue | None = None) -> None:
        self.registry = registry
        self.policy = policy
        self.approvals = approvals or ApprovalQueue()
        self._locks: dict[str, asyncio.Lock] = {}

    async def execute(self, principal: Principal, call: ToolCall, approved: bool = False) -> ToolResult:
        spec = self.registry.get(call.tool_name)
        decision = self.policy.authorize_tool(principal, call, approved)
        if not decision.allowed:
            return ToolResult(call.call_id, call.tool_name, False, failure=FailureKind.POLICY)
        lock_key = self._lock_key(call)
        lock = self._locks.setdefault(lock_key, asyncio.Lock())
        async with lock:
            failure = FailureKind.UNKNOWN
            for attempt in range(max(1, spec.max_attempts)):
                try:
                    output = await spec.handler(call.args)
                    verified = await spec.verify(call.args, output)
                    if not verified:
                        failure = FailureKind.INVALID
                        continue
                    return ToolResult(call.call_id, call.tool_name, True, output, verified=True)
                except asyncio.CancelledError:
                    raise
                except TimeoutError:
                    failure = FailureKind.TIMEOUT
                except PermissionError:
                    return ToolResult(call.call_id, call.tool_name, False, failure=FailureKind.AUTHENTICATION)
                except ValueError:
                    return ToolResult(call.call_id, call.tool_name, False, failure=FailureKind.INVALID)
                except Exception:
                    failure = FailureKind.TRANSIENT
            return ToolResult(
                call.call_id, call.tool_name, False,
                failure=failure,
                retryable=failure in {FailureKind.TIMEOUT, FailureKind.TRANSIENT},
            )

    @staticmethod
    def _lock_key(call: ToolCall) -> str:
        body = json.dumps({"tool": call.tool_name, "args": call.args}, sort_keys=True, default=str)
        return hashlib.sha256(body.encode()).hexdigest()
