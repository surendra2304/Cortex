import pytest
import os
import sys
from unittest.mock import AsyncMock, MagicMock

for p in [
    "packages/core/src",
    "packages/event_schema/src",
    "packages/agents/src",
    "packages/ai_universe_adapter/src",
    "packages/workflow_engine/src",
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(p))

from nexus_workflow_engine import WorkflowStateMachine, WorkflowState
from nexus_ai_universe_adapter import RequestClassifier, RequestClassification, AIMode


@pytest.mark.asyncio
async def test_conversion_drop_diagnosis_workflow_e2e():
    """
    End-to-End Conversion Drop Diagnosis:
    Funnel Anomaly Detected -> Trigger Diagnosis -> Form Hypotheses -> AI Universe DEBATE -> Resolve.
    """
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock(return_value=None)
    mock_db.execute = AsyncMock(return_value=None)
    sm = WorkflowStateMachine(db=mock_db)
    classifier = RequestClassifier()

    # 1. Classify trigger as STRATEGIC -> DEBATE mode
    event_type = "conversion.drop_anomaly"
    classification, mode = classifier.classify(event_type, {})
    assert classification == RequestClassification.STRATEGIC
    assert mode == AIMode.DEBATE

    # 2. Start Diagnosis Workflow
    ctx = await sm.start_workflow(
        workflow_name="CONVERSION_DROP_DIAGNOSIS",
        trigger_event={"type": event_type, "drop_pct": 34.5, "step": "checkout"},
        context_data={"funnel_id": "main_checkout_funnel"}
    )

    # 3. Execute multi-agent diagnosis workflow
    completed_ctx = await sm.execute_conversion_drop_diagnosis(ctx, ai_client=None)

    assert completed_ctx.current_state == WorkflowState.COMPLETED
    step_names = [s["step"] for s in completed_ctx.steps]
    assert "DIAGNOSE_DROP" in step_names
    assert "FORM_HYPOTHESIS" in step_names
    assert "VERIFY_TOP_HYPOTHESIS" in step_names
    assert "RESOLVE_INCIDENT" in step_names
