import pytest
import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

for p in [
    "packages/core/src",
    "packages/event_schema/src",
    "packages/agents/src",
    "packages/ai_universe_adapter/src",
    "packages/tool_runtime/src",
    "packages/integrations/src",
    "packages/policy_engine/src",
    "packages/workflow_engine/src",
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(p))

from cortex_workflow_engine import WorkflowStateMachine, WorkflowState
from cortex_integrations import create_email_tool, EmailToolExecutor


@pytest.mark.asyncio
async def test_high_intent_followup_workflow_e2e():
    """
    End-to-End High-Intent Follow-up Workflow:
    High Intent Event -> Planning -> Consent Verification -> Email Dispatch -> Outcome Measurement.
    """
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock(return_value=None)
    mock_db.execute = AsyncMock(return_value=None)
    sm = WorkflowStateMachine(db=mock_db)

    # 1. Trigger High-Intent Follow-up Workflow
    trigger_event = {
        "type": "high_intent.detected",
        "actor_id": "vis_high_intent_88",
        "intent_score": 0.92
    }
    context_data = {
        "email": "cto@target-enterprise.com",
        "consent": True,
        "first_name": "Jordan"
    }

    ctx = await sm.start_workflow(
        workflow_name="HIGH_INTENT_FOLLOWUP",
        trigger_event=trigger_event,
        context_data=context_data
    )
    assert ctx.current_state == WorkflowState.TRIGGERED

    # 2. Execute High-Intent Workflow Steps
    executed_ctx = await sm.execute_high_intent_followup(ctx, orchestrator=None)

    # 3. Assert full completion
    assert executed_ctx.current_state == WorkflowState.COMPLETED
    assert executed_ctx.completed_at is not None

    step_names = [s["step"] for s in executed_ctx.steps]
    assert "TRIGGER" in step_names
    assert "PLAN_FOLLOWUP" in step_names
    assert "SEND_EMAIL" in step_names
    assert "VERIFY_DELIVERY" in step_names
    assert "COMPLETE" in step_names
