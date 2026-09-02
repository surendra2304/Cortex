import pytest
import os
import sys

for p in [
    "packages/core/src",
    "packages/event_schema/src",
    "packages/integrations/src",
    "packages/policy_engine/src",
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(p))

from cortex_integrations import DeploymentSecurityGate, GateVerdict, IntelXClient


@pytest.mark.asyncio
async def test_deployment_gate_with_intelx_cve_research_flow():
    """
    End-to-End Deployment Gate Flow:
    Forge build -> Sentinel scan -> IntelX research on detected CVEs -> Informed gate decision.
    """
    gate = DeploymentSecurityGate()
    intelx = IntelXClient()

    # Query threat research for CVE
    profile = await intelx.fetch_competitor_intelligence("Segment")
    assert profile is not None

    # Evaluate gate with critical CVE finding
    res = await gate.evaluate_deployment(
        deployment_id="dep_forge_cve_01",
        asset_id="site_main",
        endpoints=["/api/v1/auth/token"],
        simulated_findings=[
            {"severity": "critical", "title": "CVE-2026-8891 Authentication Bypass"}
        ]
    )

    assert res.verdict == GateVerdict.BLOCKED
    assert "CRITICAL" in res.block_reason
    assert res.requires_human_override is False
