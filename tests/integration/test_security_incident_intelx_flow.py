import pytest
import os
import sys

for p in [
    "packages/core/src",
    "packages/event_schema/src",
    "packages/integrations/src",
    "packages/intelligence/src",
    "packages/workflow_engine/src",
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(p))

from nexus_integrations import SentinelEventListener, SentinelPayload, SentinelFinding, IntelXClient
from nexus_intelligence import AssetExposureMonitor
from nexus_workflow_engine import SecurityIncidentWorkflow


@pytest.mark.asyncio
async def test_sentinel_intelx_enriched_security_incident_flow():
    """
    End-to-End Security Incident Flow with IntelX Threat Enrichment:
    Sentinel finding -> IntelX threat research -> Enriched risk posture -> Incident triage & FRIDAY dispatch.
    """
    monitor = AssetExposureMonitor()
    listener = SentinelEventListener(exposure_monitor=monitor)
    intelx = IntelXClient()
    sec_workflow = SecurityIncidentWorkflow()

    # 1. Ingest finding
    payload = SentinelPayload(
        sentinel_task_id="task_sec_intelx_01",
        asset_id="site_main",
        posture_score=72.0,
        findings=[
            SentinelFinding(
                finding_id="find_cve_2026_09",
                severity="critical",
                title="Zero-Day Prototype Pollution in Webhook Handler",
                description="Prototype pollution leading to remote execution.",
                attack_vector="api_json_body",
                affected_endpoint="/v1/webhooks/incoming"
            )
        ]
    )
    await listener.handle_findings(payload)

    # 2. IntelX market signals & regulatory posture check
    signals = await intelx.fetch_market_signals("saas_devops")
    assert len(signals) > 0

    # 3. Security workflow triage
    exposure = monitor.evaluate_exposure(payload.asset_id, "/v1/webhooks/incoming")
    incident = await sec_workflow.execute_security_incident_triage(
        finding=payload.findings[0].model_dump(),
        asset_exposure=exposure
    )

    assert incident["severity"] == "critical"
    assert incident["friday_alert_sent"] is True
