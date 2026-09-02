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

from cortex_integrations import DeploymentSecurityGate, GateVerdict


@pytest.mark.asyncio
async def test_deployment_gate_scenarios_e2e():
    """
    End-to-End Deployment Gate Scenarios:
    Forge build -> Sentinel scan -> Critical blocks, High warns with override, Low allows.
    """
    gate = DeploymentSecurityGate()

    # Case 1: Critical blocks
    res_crit = await gate.evaluate_deployment(
        deployment_id="dep_scen_01",
        asset_id="site_main",
        endpoints=["/checkout"],
        simulated_findings=[{"severity": "critical", "title": "SQLi in payment form"}]
    )
    assert res_crit.verdict == GateVerdict.BLOCKED
    assert res_crit.requires_human_override is False

    # Case 2: High warns with human-in-the-loop override
    res_high = await gate.evaluate_deployment(
        deployment_id="dep_scen_02",
        asset_id="site_main",
        endpoints=["/api/v1/search"],
        simulated_findings=[{"severity": "high", "title": "XSS in search params"}]
    )
    assert res_high.verdict == GateVerdict.NEEDS_APPROVAL
    assert res_high.requires_human_override is True

    # Case 3: Medium/Low allows
    res_low = await gate.evaluate_deployment(
        deployment_id="dep_scen_03",
        asset_id="site_main",
        endpoints=["/docs"],
        simulated_findings=[{"severity": "low", "title": "Missing security header"}]
    )
    assert res_low.verdict == GateVerdict.APPROVED
    assert res_low.requires_human_override is False
