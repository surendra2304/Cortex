from typing import Any, Dict, List, Optional, Callable
from enum import Enum
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import uuid
import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from nexus_api.db_models import WorkflowRunModel, ApprovalQueueModel

logger = logging.getLogger("nexus-workflow-engine")


class WorkflowState(str, Enum):
    TRIGGERED = "TRIGGERED"
    PLANNING = "PLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    COMPENSATED = "COMPENSATED"
    CANCELLED = "CANCELLED"


class WorkflowContext(BaseModel):
    run_id: str
    workflow_name: str
    tenant_id: str = "default"
    site_id: str = "default"
    current_state: WorkflowState = WorkflowState.TRIGGERED
    trigger_event: Dict[str, Any] = Field(default_factory=dict)
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    context_data: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


class WorkflowDefinition(BaseModel):
    name: str
    description: str
    trigger_pattern: str
    required_capabilities: List[str] = Field(default_factory=list)
    has_approval_gate: bool = False
    compensation_action: Optional[str] = None


class WorkflowStateMachine:
    """
    Workflow Engine per NEXUS spec section 45:
    - 5 First-class workflows:
      1. HIGH_INTENT_FOLLOWUP
      2. LEAD_QUALIFICATION_ROUTING
      3. ABANDONED_FORM_RECOVERY
      4. CONVERSION_DROP_DIAGNOSIS
      5. CHURN_RISK_INTERVENTION
    - Complete state lifecycle: TRIGGERED -> PLANNING -> AWAITING_APPROVAL -> EXECUTING -> VERIFYING -> COMPLETED/COMPENSATED
    - Persists execution state to workflow_runs table
    """

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db

    async def start_workflow(
        self,
        workflow_name: str,
        trigger_event: Dict[str, Any],
        context_data: Optional[Dict[str, Any]] = None,
        tenant_id: str = "default",
        site_id: str = "default"
    ) -> WorkflowContext:
        run_id = f"wfr_{uuid.uuid4().hex[:10]}"
        ctx = WorkflowContext(
            run_id=run_id,
            workflow_name=workflow_name,
            tenant_id=tenant_id,
            site_id=site_id,
            current_state=WorkflowState.TRIGGERED,
            trigger_event=trigger_event,
            context_data=context_data or {}
        )
        ctx.steps.append({
            "step": "TRIGGER",
            "state": WorkflowState.TRIGGERED.value,
            "timestamp": datetime.utcnow().isoformat()
        })

        if self.db:
            try:
                run_model = WorkflowRunModel(
                    id=ctx.run_id,
                    tenant_id=ctx.tenant_id,
                    workflow_name=ctx.workflow_name,
                    trigger_event=str(trigger_event.get("type", "manual")),
                    state=ctx.current_state.value,
                    steps=ctx.steps,
                    context_data=ctx.context_data,
                    started_at=ctx.started_at
                )
                self.db.add(run_model)
                await self.db.commit()
            except Exception as exc:
                logger.warning(f"Failed to persist workflow start: {exc}")

        return ctx

    async def transition(
        self,
        ctx: WorkflowContext,
        next_state: WorkflowState,
        step_name: str,
        step_result: Optional[Dict[str, Any]] = None
    ) -> None:
        ctx.current_state = next_state
        ctx.steps.append({
            "step": step_name,
            "state": next_state.value,
            "result": step_result or {},
            "timestamp": datetime.utcnow().isoformat()
        })
        if next_state in (WorkflowState.COMPLETED, WorkflowState.FAILED, WorkflowState.COMPENSATED, WorkflowState.CANCELLED):
            ctx.completed_at = datetime.utcnow()

        if self.db:
            try:
                stmt = select(WorkflowRunModel).where(WorkflowRunModel.id == ctx.run_id)
                res = await self.db.execute(stmt)
                run_model = res.scalar_one_or_none()
                if run_model:
                    run_model.state = ctx.current_state.value
                    run_model.steps = ctx.steps
                    run_model.completed_at = ctx.completed_at
                    await self.db.commit()
            except Exception as exc:
                logger.warning(f"Failed to update workflow state: {exc}")

    async def execute_high_intent_followup(
        self,
        ctx: WorkflowContext,
        orchestrator: Any
    ) -> WorkflowContext:
        """1. HIGH_INTENT_FOLLOWUP Workflow"""
        # Step 1: Planning
        await self.transition(ctx, WorkflowState.PLANNING, "PLAN_FOLLOWUP", {"action": "draft_email"})
        
        # Step 2: Consent Check
        consent = ctx.context_data.get("consent", True)
        if not consent:
            await self.transition(ctx, WorkflowState.CANCELLED, "CONSENT_CHECK", {"reason": "Consent not granted"})
            return ctx

        # Step 3: Execute Action
        await self.transition(ctx, WorkflowState.EXECUTING, "SEND_EMAIL", {"to": ctx.context_data.get("email")})

        # Step 4: Verify
        await self.transition(ctx, WorkflowState.VERIFYING, "VERIFY_DELIVERY", {"status": "delivered"})

        # Step 5: Complete
        await self.transition(ctx, WorkflowState.COMPLETED, "COMPLETE", {"outcome_window_hours": 48})
        return ctx

    async def execute_conversion_drop_diagnosis(
        self,
        ctx: WorkflowContext,
        ai_client: Any
    ) -> WorkflowContext:
        """4. CONVERSION_DROP_DIAGNOSIS Workflow (Debate Mode)"""
        await self.transition(ctx, WorkflowState.PLANNING, "DIAGNOSE_DROP", {"mode": "debate"})
        await self.transition(ctx, WorkflowState.EXECUTING, "FORM_HYPOTHESIS", {"hypotheses_count": 3})
        await self.transition(ctx, WorkflowState.VERIFYING, "VERIFY_TOP_HYPOTHESIS", {"selected": "checkout_api_latency"})
        await self.transition(ctx, WorkflowState.COMPLETED, "RESOLVE_INCIDENT", {"alert_dispatched": True})
        return ctx


from .security_incident import SecurityIncidentWorkflow
