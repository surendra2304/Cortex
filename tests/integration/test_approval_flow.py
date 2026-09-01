import pytest
import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

for p in [
    "packages/core/src",
    "packages/event_schema/src",
    "packages/agents/src",
    "packages/tool_runtime/src",
    "packages/policy_engine/src",
    "packages/workflow_engine/src",
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(p))

from nexus_workflow_engine import WorkflowStateMachine, WorkflowState
from nexus_policy_engine import PolicyEngine
from nexus_tool_runtime import Tool, ToolCapability, SideEffectLevel, Execution


@pytest.mark.asyncio
async def test_human_in_the_loop_approval_flow_e2e():
    """
    End-to-End Approval Flow:
    HIGH_IMPACT Action -> Policy Gate -> AWAITING_APPROVAL -> Operator Approval -> Workflow Resumes.
    """
    policy_engine = PolicyEngine(human_in_the_loop_enabled=True)
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock(return_value=None)
    mock_db.execute = AsyncMock(return_value=None)
    sm = WorkflowStateMachine(db=mock_db)

    # 1. Define High Impact Tool
    high_impact_tool = Tool(
        name="banner_injection",
        capabilities=[ToolCapability.BANNER_INJECTION],
        side_effect_level=SideEffectLevel.HIGH_IMPACT
    )

    execution = Execution(
        request_id="req_hitl_001",
        tool_name="banner_injection",
        actor={"type": "agent", "id": "agent_growth"},
        reason="High bounce rate detected on pricing page",
        params={"variant": "aggressive_pricing_cta"}
    )

    # 2. Policy Engine blocks execution and requires human approval
    decision = policy_engine.evaluate(execution, high_impact_tool)
    assert decision.approved is False
    assert decision.requires_human_approval is True

    # 3. Workflow transitions to AWAITING_APPROVAL
    ctx = await sm.start_workflow(
        workflow_name="OPTIMIZE_PRICING_CONVERSION",
        trigger_event={"type": "pricing.drop_off"},
        context_data={"proposed_tool": "banner_injection"}
    )

    await sm.transition(ctx, WorkflowState.AWAITING_APPROVAL, "GATE_HUMAN_APPROVAL", {"requires_human": True})
    assert ctx.current_state == WorkflowState.AWAITING_APPROVAL

    # 4. Operator grants approval -> Workflow transitions to EXECUTING and COMPLETED
    await sm.transition(ctx, WorkflowState.EXECUTING, "OPERATOR_APPROVED", {"approved_by": "operator_admin"})
    assert ctx.current_state == WorkflowState.EXECUTING

    await sm.transition(ctx, WorkflowState.COMPLETED, "EXECUTION_FINISHED", {"status": "success"})
    assert ctx.current_state == WorkflowState.COMPLETED
