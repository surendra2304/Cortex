"""Regression tests for ToolBus execution honesty (audit defect H7).

Two behaviours used to be dishonest:

1. A Redis failure during the idempotency check returned "proceed", so a
   HIGH_IMPACT tool (email dispatch, payment, account update) could run twice.
2. ``execution.verification`` was hardcoded to ``{"status": "verified"}`` whenever
   the executor did not raise, making the loop's "Verify" phase a tautology.
"""

from __future__ import annotations

import pytest
from cortex_tool_runtime import (
    Execution,
    IdempotencyStrategy,
    SideEffectLevel,
    Tool,
    ToolBus,
)


class BrokenRedis:
    async def set(self, *args, **kwargs):
        raise ConnectionError("redis down")


def _execution(key: str = "idem-1") -> Execution:
    return Execution(
        request_id="req-1",
        tool_name="send_email",
        actor={"id": "agent_sales"},
        reason="follow up with a high-intent lead",
        idempotency_key=key,
    )


def _register(bus: ToolBus, level: SideEffectLevel, calls: list):
    async def executor(params, execution=None):
        calls.append(params)
        return {"sent": True}

    bus.register_tool(
        Tool(
            name="send_email",
            side_effect_level=level,
            idempotency_strategy=IdempotencyStrategy.IDEMPOTENCY_KEY,
        ),
        executor,
    )


@pytest.mark.asyncio
async def test_high_impact_tool_is_blocked_when_idempotency_store_fails():
    calls: list = []
    bus = ToolBus(redis_client=BrokenRedis())
    _register(bus, SideEffectLevel.HIGH_IMPACT, calls)

    execution = _execution()
    result = await bus.execute("send_email", {"to": "lead@example.com"}, execution)

    assert result["status"] == "blocked"
    assert result["reason"] == "idempotency_guard_unavailable"
    assert calls == [], "a duplicate-risk side effect must not run without its guard"
    assert execution.verification["status"] == "blocked"


@pytest.mark.asyncio
async def test_read_tool_degrades_but_still_runs_when_store_fails():
    calls: list = []
    bus = ToolBus(redis_client=BrokenRedis())
    _register(bus, SideEffectLevel.READ, calls)

    execution = _execution("idem-read")
    result = await bus.execute("send_email", {"q": "x"}, execution)

    assert result["status"] == "success"
    assert calls == [{"q": "x"}]
    assert execution.verification["idempotency"] == "unavailable_degraded"


@pytest.mark.asyncio
async def test_verification_is_executed_not_verified_without_provider_confirmation():
    calls: list = []
    bus = ToolBus(redis_client=None)
    _register(bus, SideEffectLevel.READ, calls)

    execution = _execution("idem-2")
    await bus.execute("send_email", {"to": "a@b.c"}, execution)

    assert execution.verification["status"] == "executed"
    assert execution.verification["source"] == "tool_bus"
    # In-process fallback must be visible, not silently presented as a hard guarantee.
    assert execution.verification["idempotency"] == "local_degraded"


@pytest.mark.asyncio
async def test_verification_records_provider_confirmation_when_executor_reports_it():
    bus = ToolBus(redis_client=None)

    async def executor(params, execution=None):
        return {"delivered": True, "verified": True}

    bus.register_tool(
        Tool(name="send_email", side_effect_level=SideEffectLevel.READ),
        executor,
    )
    execution = _execution("idem-3")
    await bus.execute("send_email", {}, execution)

    assert execution.verification["status"] == "verified"
    assert execution.verification["source"] == "executor"
    assert execution.verification["idempotency"] == "local_degraded"


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_skips_execution():
    calls: list = []
    bus = ToolBus(redis_client=None)
    _register(bus, SideEffectLevel.READ, calls)

    await bus.execute("send_email", {"to": "a@b.c"}, _execution("idem-dup"))
    second = await bus.execute("send_email", {"to": "a@b.c"}, _execution("idem-dup"))

    assert second["status"] == "skipped"
    assert second["reason"] == "duplicate_idempotent_request"
    assert len(calls) == 1
