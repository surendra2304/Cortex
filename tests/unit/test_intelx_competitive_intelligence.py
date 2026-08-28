import pytest
import os
import sys
from fastapi.testclient import TestClient

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

from nexus_api.main import app
from nexus_integrations import IntelXClient
from nexus_intelligence import MarketSignalDetector
from nexus_agents import CompetitiveIntelligenceAgent, AgentInput, AgentRegistry


@pytest.mark.asyncio
async def test_intelx_client_competitive_and_market_intelligence():
    client = IntelXClient()

    # 1. Fetch competitor profile
    profile = await client.fetch_competitor_intelligence("Datadog")
    assert profile.competitor_name == "Datadog"
    assert len(profile.feature_gaps) > 0
    assert "Nexus" in profile.battlecard_summary

    # 2. Fetch market signals
    signals = await client.fetch_market_signals("saas_devops")
    assert len(signals) >= 2
    assert "Autonomous" in signals[0].trend_title


@pytest.mark.asyncio
async def test_competitive_intelligence_agent_processing():
    agent = CompetitiveIntelligenceAgent()

    # Process input mentioning competitor in telemetry
    inp = AgentInput(
        goal="Synthesize competitive positioning battlecard",
        events=[
            {"type": "page_view", "data": {"url": "https://example.com/compare-datadog-vs-nexus"}},
            {"type": "search.performed", "data": {"query": "datadog pricing alternatives"}}
        ],
        context={"competitor_name": "Datadog"}
    )

    output = await agent.process(inp)
    assert output.decision == "SYNTHESIZE_COMPETITIVE_BATTLECARD"
    assert output.confidence > 0.85
    assert len(output.proposed_actions) == 2
    assert any(a.action_type == "account_update" for a in output.proposed_actions)
    assert any(a.action_type == "banner_injection" for a in output.proposed_actions)


def test_market_signal_detector_trending_content():
    detector = MarketSignalDetector()
    # Trigger detection
    import asyncio
    asyncio.run(detector.detect_market_signals("saas_devops"))

    recs = detector.get_trending_content_recommendations(["agentic", "workflows"])
    assert len(recs) > 0
    assert any("Agentic" in r for r in recs)


def test_agent_registry_routes_competitor_event():
    registry = AgentRegistry()
    routed = registry.route_for_event("competitor.datadog_comparison")
    assert routed.agent_id == "agent_competitive"


def test_friday_competitive_summary_and_market_trends_endpoints():
    client = TestClient(app)

    # 1. Voice query: What's my competitive position?
    comp_res = client.get("/v1/friday/competitive_summary?competitor=Datadog")
    assert comp_res.status_code == 200
    assert "voice_summary" in comp_res.json()
    assert "battlecard" in comp_res.json()

    # 2. Voice query: Any market trends affecting my site?
    mkt_res = client.get("/v1/friday/market_trends?industry=saas_devops")
    assert mkt_res.status_code == 200
    assert "voice_summary" in mkt_res.json()
    assert len(mkt_res.json()["active_signals"]) > 0
