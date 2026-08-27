import os
import sys
import pytest
from datetime import datetime

sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/event_schema/src"))
sys.path.insert(0, os.path.abspath("packages/agents/src"))
sys.path.insert(0, os.path.abspath("packages/ai_universe_adapter/src"))
sys.path.insert(0, os.path.abspath("packages/tool_runtime/src"))
sys.path.insert(0, os.path.abspath("packages/policy_engine/src"))
sys.path.insert(0, os.path.abspath("packages/workflow_engine/src"))

from nexus_core import Orchestrator
from nexus_event_schema import EventSchema, Actor, ActorType
from nexus_agents import AgentRegistry, GrowthAgent, SalesAgent, SupportAgent, ReliabilityAgent
from nexus_workflow_engine import WorkflowStateMachine, WorkflowContext, WorkflowState


@pytest.mark.asyncio
async def test_agent_registry_routing():
    registry = AgentRegistry()
    assert isinstance(registry.route_for_event("pricing_view"), GrowthAgent)
    assert isinstance(registry.route_for_event("checkout_completed"), SalesAgent)
    assert isinstance(registry.route_for_event("error_spike"), SupportAgent)
    assert isinstance(registry.route_for_event("heartbeat"), ReliabilityAgent)


@pytest.mark.asyncio
async def test_workflow_state_machine():
    sm = WorkflowStateMachine(db=None)
    ctx = await sm.start_workflow(
        workflow_name="HIGH_INTENT_FOLLOWUP",
        trigger_event={"type": "lead_created"}
    )
    await sm.transition(ctx, WorkflowState.PLANNING, "PLAN")
    await sm.transition(ctx, WorkflowState.EXECUTING, "EXECUTE")
    await sm.transition(ctx, WorkflowState.COMPLETED, "COMPLETE")

    assert ctx.current_state == WorkflowState.COMPLETED
    assert len(ctx.steps) == 4


@pytest.mark.asyncio
async def test_cognitive_loop_orchestrator():
    orchestrator = Orchestrator()

    # Create pricing view event
    evt = EventSchema(
        event_id="evt_loop_1",
        tenant_id="tenant_alpha",
        site_id="site_beta",
        type="pricing_view",
        occurred_at=datetime.utcnow(),
        actor=Actor(type=ActorType.VISITOR, id="vis_123"),
        source="web-sdk",
        data={"plan": "enterprise"}
    )

    result = await orchestrator.run_cognitive_loop(evt)
    assert result["status"] == "success"
    assert result["agent_id"] == "agent_growth"
    assert len(result["trace"]) >= 10
    assert len(orchestrator.audit_records) == 1
    assert orchestrator.audit_records[0].tenant_id == "tenant_alpha"
