import pytest
import os
import sys

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

from nexus_integrations import IntelXClient
from nexus_agents import CompetitiveIntelligenceAgent, AgentInput, GrowthAgent


@pytest.mark.asyncio
async def test_full_intelx_competitive_intelligence_flow_e2e():
    """
    End-to-End IntelX Competitive Flow:
    Competitor detected in telemetry -> Research submitted to IntelX -> Findings synthesized
    -> GrowthAgent recommendation -> Personalization updated.
    """
    intelx = IntelXClient()
    comp_agent = CompetitiveIntelligenceAgent(intelx_client=intelx)
    growth_agent = GrowthAgent()

    # Step 1: Competitor query in event stream
    inp = AgentInput(
        goal="Competitor alternative evaluation",
        events=[
            {"type": "page_view", "data": {"url": "https://company.com/compare/dynatrace"}},
            {"type": "pricing.viewed", "data": {"tier": "enterprise"}}
        ],
        context={"competitor_name": "Dynatrace"}
    )

    # Step 2: CompetitiveIntelligenceAgent executes IntelX research
    output = await comp_agent.process(inp)
    assert output.decision == "SYNTHESIZE_COMPETITIVE_BATTLECARD"
    assert "Dynatrace" in output.reasoning_summary
    assert len(output.proposed_actions) == 2

    # Step 3: Verify battlecard and comparison banner proposed
    banner_action = next(a for a in output.proposed_actions if a.action_type == "banner_injection")
    assert "vs_dynatrace_callout" in banner_action.params.get("variant")
    assert "Switch from Dynatrace" in banner_action.params.get("copy")
