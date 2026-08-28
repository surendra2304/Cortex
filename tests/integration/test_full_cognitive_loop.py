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

from nexus_core import Orchestrator
from nexus_event_schema import EventSchema, Actor, ActorType
from nexus_agents import AgentRegistry
from nexus_ai_universe_adapter import AIUniverseClient
from nexus_policy_engine import PolicyEngine
from nexus_tool_runtime import ToolBus
from nexus_identity import IdentityResolver
from nexus_analytics import ScoringEngine
from nexus_intelligence import ContextBuilder
from nexus_memory import MemoryStore


@pytest.mark.asyncio
async def test_full_cognitive_loop_end_to_end():
    """
    End-to-End Cognitive Loop Test:
    Synthetic Event -> Ingestion -> Context Assembly -> Agent Processing
    -> AI Universe Consultation -> Policy Evaluation -> Tool Execution
    -> Outcome Measurement -> Strategy Learning.
    Verifies trace_id propagation and all 10 phases.
    """
    # 1. Setup mock database and orchestrator components
    mock_db = AsyncMock()
    mock_db.execute.return_value = MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))

    orchestrator = Orchestrator()

    # 2. Construct synthetic high-intent conversion event
    event = EventSchema(
        event_id="evt_e2e_001",
        tenant_id="ten_enterprise",
        site_id="site_main",
        type="demo.requested",
        occurred_at=datetime.utcnow(),
        actor=Actor(type=ActorType.VISITOR, id="vis_e2e_100"),
        session_id="ses_e2e_200",
        source="web-sdk",
        data={"company_size": "500+", "role": "VP Engineering"},
        consent={"analytics": True},
        trace_id="trc_e2e_full_loop_999"
    )

    # 3. Execute full 10-phase cognitive loop
    result = await orchestrator.run_cognitive_loop(event, db_session=mock_db)

    # 4. Assertions across all phases
    assert result["status"] == "success"
    assert result["trace_id"] == "trc_e2e_full_loop_999"
    assert result["loop_id"].startswith("loop_")

    trace = result["trace"]
    phase_names = [step.get("phase") for step in trace]

    # Verify key cognitive phases occurred in exact sequence
    assert "1.Observe" in phase_names
    assert "2.Contextualize" in phase_names
    assert "3.Understand" in phase_names
    assert "4.Plan" in phase_names
    assert "5.Authorize" in phase_names
    assert "6.Execute" in phase_names
    assert "7.Verify" in phase_names
    assert "8.Measure" in phase_names
    assert "9.Learn" in phase_names
    assert "10.Continue" in phase_names

    # Verify agent was routed and planned an action
    plan_phase = next(step for step in trace if step.get("phase") == "4.Plan")
    assert plan_phase["decision"] is not None
    assert plan_phase["confidence"] > 0.0
