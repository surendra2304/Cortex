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

from nexus_integrations import (
    SentinelEventListener,
    SentinelPayload,
    SentinelFinding,
    DeploymentSecurityGate,
    GateVerdict,
    IntelXClient,
    FuturisClient
)
from nexus_agents import CompetitiveIntelligenceAgent, GrowthAgent, AgentInput
from nexus_intelligence import AssetExposureMonitor, MarketSignalDetector, PredictionInformedPersonalization
from nexus_workflow_engine import SecurityIncidentWorkflow, CapacityPlanningWorkflow


@pytest.mark.asyncio
async def test_full_eight_system_ecosystem_orchestration_e2e():
    """
    Complete Eight-System Ecosystem Integration Test:
    1. Sentinel (Vulnerability intake & exposure mapping)
    2. Forge (Deployment security gate verification)
    3. IntelX (Competitive intelligence & market signals)
    4. Futuris (Traffic capacity & predictive personalization)
    5. AI Universe (Deliberation & decision making)
    6. Specialist Agents (Growth, Sales, Competitive, Reliability)
    7. Closed-Loop Learning (MemoryStore & OutcomeTracker)
    8. FRIDAY Bridge (Executive voice queries & incident delegation)
    """

    # ── 1. Sentinel Security Flow ──
    exposure_mon = AssetExposureMonitor()
    sentinel_listener = SentinelEventListener(exposure_monitor=exposure_mon)
    payload = SentinelPayload(
        sentinel_task_id="task_e2e_8sys_01",
        asset_id="site_main",
        posture_score=80.0,
        findings=[
            SentinelFinding(
                finding_id="find_sec_001",
                severity="high",
                title="Potential XSS on search route",
                description="Search query parameter not escaped in server template.",
                attack_vector="web_query",
                affected_endpoint="/search"
            )
        ]
    )
    ingest_res = await sentinel_listener.handle_findings(payload)
    assert ingest_res["status"] == "ingested"

    # ── 2. Forge Deployment Security Gate ──
    gate = DeploymentSecurityGate()
    gate_res = await gate.evaluate_deployment(
        deployment_id="dep_forge_release_v2",
        asset_id="site_main",
        endpoints=["/search"],
        simulated_findings=[payload.findings[0].model_dump()]
    )
    assert gate_res.verdict == GateVerdict.NEEDS_APPROVAL
    assert gate_res.requires_human_override is True

    # ── 3. IntelX Competitive & Market Intelligence ──
    intelx = IntelXClient()
    comp_profile = await intelx.fetch_competitor_intelligence("Datadog")
    assert len(comp_profile.feature_gaps) > 0

    market_detector = MarketSignalDetector(intelx_client=intelx)
    mkt_signals = await market_detector.detect_market_signals("saas_devops")
    assert len(mkt_signals) >= 2

    # ── 4. Futuris Predictive Operations & Capacity ──
    futuris = FuturisClient()
    cap_wf = CapacityPlanningWorkflow(futuris_client=futuris)
    cap_res = await cap_wf.evaluate_capacity("site_main")
    assert cap_res.site_id == "site_main"

    pred_pers = PredictionInformedPersonalization(futuris_client=futuris)
    pers_adj = await pred_pers.evaluate_segment_personalization("checkout_segment")
    assert pers_adj is not None

    # ── 5. Specialist Agents & Deliberation ──
    comp_agent = CompetitiveIntelligenceAgent(intelx_client=intelx)
    agent_inp = AgentInput(
        goal="Competitor Battlecard Generation",
        events=[{"type": "page_view", "data": {"url": "https://example.com/vs-datadog"}}],
        context={"competitor_name": "Datadog"}
    )
    agent_out = await comp_agent.process(agent_inp)
    assert agent_out.decision == "SYNTHESIZE_COMPETITIVE_BATTLECARD"
    assert len(agent_out.proposed_actions) == 2
