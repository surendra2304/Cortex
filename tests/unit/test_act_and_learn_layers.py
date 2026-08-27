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
    "packages/identity/src",
    "packages/analytics/src",
    "packages/intelligence/src",
    "packages/memory/src",
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(p))

from nexus_workflow_engine import WorkflowStateMachine, WorkflowState, WorkflowContext
from nexus_analytics import OutcomeTracker, OutcomeVerdict, StrategyStatus
from nexus_ai_universe_adapter import RequestClassifier, RequestClassification, AIMode


@pytest.mark.asyncio
async def test_workflow_state_machine_high_intent_lifecycle():
    sm = WorkflowStateMachine(db=None)

    ctx = await sm.start_workflow(
        workflow_name="HIGH_INTENT_FOLLOWUP",
        trigger_event={"type": "high_intent.detected", "score": 0.92},
        context_data={"email": "lead@enterprise.com", "consent": True}
    )
    assert ctx.current_state == WorkflowState.TRIGGERED
    assert len(ctx.steps) == 1

    # Execute workflow lifecycle steps
    completed_ctx = await sm.execute_high_intent_followup(ctx, None)
    assert completed_ctx.current_state == WorkflowState.COMPLETED
    assert any(s["step"] == "SEND_EMAIL" for s in completed_ctx.steps)
    assert any(s["step"] == "VERIFY_DELIVERY" for s in completed_ctx.steps)


@pytest.mark.asyncio
async def test_workflow_consent_revocation_cancellation():
    sm = WorkflowStateMachine(db=None)

    ctx = await sm.start_workflow(
        workflow_name="HIGH_INTENT_FOLLOWUP",
        trigger_event={"type": "high_intent.detected"},
        context_data={"email": "lead@enterprise.com", "consent": False}
    )
    # When consent is false, workflow cancels at consent check step
    cancelled_ctx = await sm.execute_high_intent_followup(ctx, None)
    assert cancelled_ctx.current_state == WorkflowState.CANCELLED
    assert cancelled_ctx.steps[-1]["result"]["reason"] == "Consent not granted"


def test_outcome_tracker_verdict_evaluation():
    tracker = OutcomeTracker()

    # Case A: Email sent -> Replied -> SUCCESS
    verdict_email = tracker.evaluate_verdict("email_dispatch", [{"type": "email.replied"}])
    assert verdict_email == OutcomeVerdict.SUCCESS

    # Case B: Banner injected -> Checkout -> SUCCESS
    verdict_banner = tracker.evaluate_verdict("banner_injection", [{"type": "checkout.completed"}])
    assert verdict_banner == OutcomeVerdict.SUCCESS

    # Case C: Banner injected -> No downstream events -> NO_EFFECT
    verdict_none = tracker.evaluate_verdict("banner_injection", [])
    assert verdict_none == OutcomeVerdict.NO_EFFECT


@pytest.mark.asyncio
async def test_strategy_auto_promotion_and_demotion():
    tracker = OutcomeTracker()
    mock_db = AsyncMock()

    # Mock empty strategy record
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    status = await tracker.record_and_update_strategy(
        db=mock_db,
        strategy_key="agent_growth:banner_injection",
        action_type="banner_injection",
        action_id="act_test_1",
        downstream_events=[{"type": "checkout.completed"}]
    )
    assert status in (StrategyStatus.PROBATION, StrategyStatus.PROVEN)


def test_ai_universe_modes_and_classification_constraints():
    classifier = RequestClassifier()

    # Strategic conversion drop -> DEBATE mode
    s_class, s_mode = classifier.classify("conversion.drop_detected", {})
    assert s_class == RequestClassification.STRATEGIC
    assert s_mode == AIMode.DEBATE

    # Ambiguous lead qualification -> FAST or REVIEW
    a_class, a_mode = classifier.classify("lead.qualify", {})
    assert a_class == RequestClassification.AMBIGUOUS
    assert a_mode in (AIMode.FAST, AIMode.REVIEW)
