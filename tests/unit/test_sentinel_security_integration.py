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


def test_asset_exposure_monitor():
    monitor = AssetExposureMonitor()
    
    # 1. Check pre-registered critical asset
    checkout_exp = monitor.evaluate_exposure("site_main", "/checkout")
    assert checkout_exp["exposure_level"] == "critical"
    assert checkout_exp["data_sensitivity"] == "high"

    # 2. Check dynamic unauthenticated sensitive route inference
    login_exp = monitor.evaluate_exposure("site_main", "/api/v1/auth/login")
    assert login_exp["exposure_level"] == "critical"

    # 3. Check public standard asset
    pricing_exp = monitor.evaluate_exposure("site_main", "/pricing")
    assert pricing_exp["exposure_level"] == "standard"


@pytest.mark.asyncio
async def test_sentinel_listener_and_security_incident_workflow():
    monitor = AssetExposureMonitor()
    listener = SentinelEventListener(exposure_monitor=monitor)
    workflow = SecurityIncidentWorkflow()

    payload = SentinelPayload(
        sentinel_task_id="task_sec_999",
        asset_id="site_main",
        posture_score=82.0,
        findings=[
            SentinelFinding(
                finding_id="find_sqli_01",
                severity="critical",
                title="SQL Injection on unauthenticated checkout parameter",
                description="Union-based SQLi vulnerability identified on payment discount field.",
                attack_vector="web_request",
                affected_endpoint="/checkout"
            )
        ]
    )

    # 1. Ingest findings via listener
    ingest_res = await listener.handle_findings(payload)
    assert ingest_res["status"] == "ingested"
    assert ingest_res["findings_count"] == 1
    assert ingest_res["posture_score"] == 82.0

    # 2. Run security incident triage workflow
    finding_dict = payload.findings[0].model_dump()
    finding_dict["asset_id"] = payload.asset_id
    exposure = monitor.evaluate_exposure(payload.asset_id, "/checkout")

    triage_res = await workflow.execute_security_incident_triage(
        finding=finding_dict,
        asset_exposure=exposure
    )

    assert triage_res["severity"] == "critical"
    assert triage_res["exposure_level"] == "critical"
    assert triage_res["status"] == "active_monitoring"
    assert triage_res["friday_alert_sent"] is True


def test_sentinel_findings_api_endpoint():
    client = TestClient(app)

    # POST findings to /v1/sentinel/findings
    payload = {
        "sentinel_task_id": "task_api_sec_001",
        "asset_id": "site_main",
        "posture_score": 88.5,
        "findings": [
            {
                "finding_id": "find_api_01",
                "severity": "high",
                "title": "Cross-Site Scripting (Reflected)",
                "description": "Reflected XSS on user profile search query parameter.",
                "attack_vector": "browser_xss",
                "affected_endpoint": "/search"
            }
        ]
    }

    res = client.post("/v1/sentinel/findings", json=payload)
    assert res.status_code == 202
    data = res.json()
    assert data["status"] == "ingested"
    assert data["findings_count"] == 1
    assert len(data["security_incidents_triaged"]) == 1

    # GET exposure
    exp_res = client.get("/v1/sentinel/exposure")
    assert exp_res.status_code == 200
    assert "assets" in exp_res.json()
