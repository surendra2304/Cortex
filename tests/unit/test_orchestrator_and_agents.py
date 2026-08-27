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
    ctx = WorkflowContext(
        workflow_id="wf_101",
        tenant_id="tenant_alpha",
        site_id="site_beta",
        trigger_data={"event": "lead_created"}
    )
    sm = WorkflowStateMachine(ctx)
    sm.transition(WorkflowState.CONTEXT_ASSEMBLY)
    sm.transition(WorkflowState.AGENT_RUN)
    sm.transition(WorkflowState.COMPLETED)

    assert ctx.current_state == WorkflowState.COMPLETED
    assert len(ctx.history) == 3


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
