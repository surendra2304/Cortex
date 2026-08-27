import os
import sys
import pytest
from unittest.mock import AsyncMock, patch
import httpx

sys.path.insert(0, os.path.abspath("packages/ai_universe_adapter/src"))
sys.path.insert(0, os.path.abspath("packages/tool_runtime/src"))
sys.path.insert(0, os.path.abspath("packages/policy_engine/src"))

from nexus_ai_universe_adapter import IntelligenceRequest, IntelligenceResponse, AIUniverseClient, RecommendedAction
from nexus_tool_runtime import Tool, Execution, SideEffectLevel, PolicyDecision, ToolCapability, IdempotencyStrategy
from nexus_policy_engine import PolicyEngine


@pytest.mark.asyncio
async def test_ai_universe_client_fallback_and_confidence():
    client = AIUniverseClient(endpoint="http://127.0.0.1:9999", timeout_seconds=0.2, max_retries=2)
    req = IntelligenceRequest(
        request_id="req_intel_test_fallback",
        task_type="anomaly_detection",
        goal="Detect dropoff",
        context={"site_id": "site_test"},
        evidence=[{"metric": "bounce_rate", "value": 0.85}],
        trust_labels={"site_id": "system_fact", "bounce_rate": "verified_telemetry"},
        provenance={"trace_id": "trc_test_123"},
        constraints=["no_destructive_actions"]
    )
    res = await client.evaluate(req)
    assert isinstance(res, IntelligenceResponse)
    assert res.request_id == "req_intel_test_fallback"
    assert res.decision == "NOOP_FALLBACK"
    assert res.confidence == 0.0
    assert res.fallback_applied is True


@pytest.mark.asyncio
async def test_ai_universe_client_success_and_dissent():
    client = AIUniverseClient(endpoint="https://mock-ai-universe.dev", api_key="test_key")
    req = IntelligenceRequest(
        request_id="req_intel_test_success",
        task_type="lead_scoring",
        goal="Score visitor",
        context={"user_id": "usr_999"},
        evidence=[],
        trust_labels={"user_id": "verified_telemetry"}
    )

    mock_response_data = {
        "request_id": "req_intel_test_success",
        "decision": "INTERVENE",
        "confidence": 0.91,
        "summary": "High intent detected.",
        "key_evidence": ["enterprise_pricing_view"],
        "provenance": {"model": "universe-v4"},
        "unresolved_disagreements": ["variant_allocation_dispute"],
        "recommended_actions": [],
        "safety_notes": ["Approved for sensitive tool dispatch."]
    }

    mock_httpx_resp = AsyncMock()
    mock_httpx_resp.status_code = 200
    mock_httpx_resp.json = lambda: mock_response_data

    with patch("httpx.AsyncClient.post", return_value=mock_httpx_resp):
        res = await client.evaluate(req)
        assert res.decision == "INTERVENE"
        assert res.confidence == 0.91
        assert "variant_allocation_dispute" in res.unresolved_disagreements
        assert res.fallback_applied is False


def test_tool_runtime_and_policy_engine():
    engine = PolicyEngine(human_in_the_loop_enabled=True)

    read_tool = Tool(
        name="inspect_session_logs",
        version="1.0.0",
        capabilities=[ToolCapability.SESSION_INSPECT],
        side_effect_level=SideEffectLevel.READ,
        rate_limit=100
    )

    high_impact_tool = Tool(
        name="inject_emergency_banner",
        version="1.0.0",
        capabilities=[ToolCapability.BANNER_INJECTION],
        side_effect_level=SideEffectLevel.HIGH_IMPACT,
        rate_limit=10
    )

    dangerous_tool = Tool(
        name="purge_tenant_database",
        version="1.0.0",
        capabilities=[],
        side_effect_level=SideEffectLevel.DANGEROUS,
        rate_limit=1
    )

    exec_read = Execution(
        request_id="exec_1",
        tool_name=read_tool.name,
        actor={"type": "agent", "id": "diagnostics_agent"},
        reason="Check visitor drop-off path"
    )

    exec_impact = Execution(
        request_id="exec_2",
        tool_name=high_impact_tool.name,
        actor={"type": "agent", "id": "ops_agent"},
        reason="Publish incident alert banner"
    )

    exec_danger = Execution(
        request_id="exec_3",
        tool_name=dangerous_tool.name,
        actor={"type": "agent", "id": "test_agent"},
        reason="E2E test teardown"
    )

    # Test READ policy
    dec_read = engine.evaluate(exec_read, read_tool)
    assert dec_read.approved is True
    assert dec_read.requires_human_approval is False

    # Test HIGH_IMPACT policy
    dec_impact = engine.evaluate(exec_impact, high_impact_tool)
    assert dec_impact.approved is False
    assert dec_impact.requires_human_approval is True

    # Test DANGEROUS policy
    dec_danger = engine.evaluate(exec_danger, dangerous_tool)
    assert dec_danger.approved is False
    assert dec_danger.requires_human_approval is True
