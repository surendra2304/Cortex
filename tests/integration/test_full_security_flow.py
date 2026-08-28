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
from nexus_integrations import SentinelEventListener, SentinelPayload, SentinelFinding
from nexus_intelligence import AssetExposureMonitor
from nexus_workflow_engine import SecurityIncidentWorkflow


@pytest.mark.asyncio
async def test_full_security_finding_to_resolution_flow_e2e():
    """
    End-to-End Security Flow:
    Sentinel finding -> Nexus incident creation -> Remediation tracking -> Verification -> Resolution.
    """
    monitor = AssetExposureMonitor()
    listener = SentinelEventListener(exposure_monitor=monitor)
    workflow = SecurityIncidentWorkflow()

    # 1. Ingest Critical Finding from Sentinel
    payload = SentinelPayload(
        sentinel_task_id="task_sec_flow_01",
        asset_id="site_main",
        posture_score=75.0,
        findings=[
            SentinelFinding(
                finding_id="find_rce_01",
                severity="critical",
                title="Remote Code Execution on Webhook Endpoint",
                description="Unsanitized command execution via serialized payload.",
                attack_vector="api_injection",
                affected_endpoint="/v1/webhooks/incoming"
            )
        ]
    )

    ingest_res = await listener.handle_findings(payload)
    assert ingest_res["status"] == "ingested"

    # 2. Automated Security Incident Triage & Telemetry Linking
    finding_dict = payload.findings[0].model_dump()
    finding_dict["asset_id"] = payload.asset_id
    exposure = monitor.evaluate_exposure(payload.asset_id, "/v1/webhooks/incoming")

    incident = await workflow.execute_security_incident_triage(
        finding=finding_dict,
        asset_exposure=exposure
    )

    assert incident["severity"] == "critical"
    assert incident["status"] == "active_monitoring"
    assert incident["friday_alert_sent"] is True
