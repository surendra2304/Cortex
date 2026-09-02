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

from cortex_api.main import app
from cortex_integrations import DeploymentSecurityGate, GateVerdict
from cortex_analytics import SecurityBaselineTracker


@pytest.mark.asyncio
async def test_deployment_security_gate_critical_blocks():
    gate = DeploymentSecurityGate()

    # 1. Critical finding -> BLOCKED
    res_crit = await gate.evaluate_deployment(
        deployment_id="dep_001",
        asset_id="site_main",
        endpoints=["/checkout"],
        simulated_findings=[
            {"severity": "critical", "title": "RCE on webhook parser"}
        ]
    )
    assert res_crit.verdict == GateVerdict.BLOCKED
    assert "CRITICAL" in res_crit.block_reason
    assert res_crit.requires_human_override is False

    # 2. High finding -> NEEDS_APPROVAL with override
    res_high = await gate.evaluate_deployment(
        deployment_id="dep_002",
        asset_id="site_main",
        endpoints=["/api/v1/search"],
        simulated_findings=[
            {"severity": "high", "title": "Reflected XSS"}
        ]
    )
    assert res_high.verdict == GateVerdict.NEEDS_APPROVAL
    assert res_high.requires_human_override is True
    assert res_high.approval_request_id is not None

    # 3. Medium / Low -> APPROVED
    res_med = await gate.evaluate_deployment(
        deployment_id="dep_003",
        asset_id="site_main",
        endpoints=["/pricing"],
        simulated_findings=[
            {"severity": "medium", "title": "Missing HSTS Header"}
        ]
    )
    assert res_med.verdict == GateVerdict.APPROVED
    assert res_med.block_reason is None


@pytest.mark.asyncio
async def test_forge_delivery_integration():
    gate = DeploymentSecurityGate()
    manifest = {
        "asset_id": "site_main",
        "deployed_endpoints": ["/v1/checkout", "/v1/pay"],
        "security_findings": []
    }
    delivery_res = await gate.process_forge_delivery("forge_task_77", manifest)
    assert delivery_res["traffic_routed"] is True
    assert delivery_res["gate_result"]["verdict"] == "APPROVED"


def test_security_baseline_and_compliance_report():
    tracker = SecurityBaselineTracker()

    # 1. Check regression detection
    tracker.record_resolved_finding("finding_sig_sqli_search")
    assert tracker.check_for_regression("finding_sig_sqli_search") is True
    assert tracker.check_for_regression("finding_sig_unknown") is False

    # 2. Generate Compliance Report
    report = tracker.generate_compliance_report()
    assert report["compliance_readiness_score"] > 90.0
    assert "SOC2_Type_II" in report["frameworks"]
    assert "critical" in report["sla_rules"]
    assert len(report["posture_trajectory"]) > 0


def test_deployment_gate_and_compliance_api_endpoints():
    client = TestClient(app)

    # 1. POST /v1/security/deployment-gate/evaluate
    res = client.post("/v1/security/deployment-gate/evaluate", json={
        "deployment_id": "dep_api_test_01",
        "asset_id": "site_main",
        "endpoints": ["/api/v1/auth"],
        "simulated_findings": [{"severity": "critical", "title": "Auth Bypass"}]
    })
    assert res.status_code == 200
    assert res.json()["verdict"] == "BLOCKED"

    # 2. GET /v1/security/compliance-report
    comp_res = client.get("/v1/security/compliance-report")
    assert comp_res.status_code == 200
    assert "compliance_readiness_score" in comp_res.json()
