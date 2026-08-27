import os
import sys
import pytest
from datetime import datetime

sys.path.insert(0, os.path.abspath("packages/ai_universe_adapter/src"))
sys.path.insert(0, os.path.abspath("packages/tool_runtime/src"))
sys.path.insert(0, os.path.abspath("packages/policy_engine/src"))

from nexus_ai_universe_adapter import IntelligenceRequest, IntelligenceResponse, AIUniverseClient, RecommendedAction
from nexus_tool_runtime import Tool, Execution, SideEffectLevel, PolicyDecision, ToolCapability, IdempotencyStrategy
from nexus_policy_engine import PolicyEngine


@pytest.mark.asyncio
async def test_ai_universe_client_fallback():
    client = AIUniverseClient(endpoint="http://127.0.0.1:9999", timeout_seconds=0.5)
    req = IntelligenceRequest(
        request_id="req_intel_123",
        task_type="anomaly_detection",
        goal="Detect sudden conversion drop",
        context={"site_id": "site_test"},
        evidence=[{"metric": "bounce_rate", "value": 0.85}],
        constraints=["no_destructive_actions"],
        required_output={"decision": "string", "confidence": "float"}
    )
    res = await client.evaluate(req)
    assert isinstance(res, IntelligenceResponse)
    assert res.request_id == "req_intel_123"
    assert res.decision == "NOOP"
    assert res.fallback_applied is True


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
