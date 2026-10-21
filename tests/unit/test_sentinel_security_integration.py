import os
import sys

import pytest

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

from cortex_integrations import SentinelEventListener, SentinelFinding, SentinelPayload
from cortex_intelligence import AssetExposureMonitor
from cortex_workflow_engine import SecurityIncidentWorkflow

from tests.conftest import auth_headers, friday_headers


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
                affected_endpoint="/checkout",
            )
        ],
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

    triage_res = await workflow.execute_security_incident_triage(finding=finding_dict, asset_exposure=exposure)

    assert triage_res["severity"] == "critical"
    assert triage_res["exposure_level"] == "critical"
    assert triage_res["status"] == "active_monitoring"
    assert triage_res["friday_alert_sent"] is True


def test_sentinel_findings_api_endpoint(monkeypatch, api_client, provisioned_key):
    client = api_client
    _, tenant_id, site_id = provisioned_key
    payload = {
        "sentinel_task_id": "task_api_sec_001",
        "asset_id": site_id,
        "posture_score": 88.5,
        "findings": [
            {
                "finding_id": "find_api_01",
                "severity": "high",
                "title": "Cross-Site Scripting (Reflected)",
                "description": "Reflected XSS on user profile search query parameter.",
                "attack_vector": "browser_xss",
                "affected_endpoint": "/search",
            }
        ],
    }

    assert client.post("/v1/sentinel/findings", json=payload).status_code == 401
    res = client.post("/v1/sentinel/findings", headers=friday_headers(monkeypatch), json=payload)
    assert res.status_code == 202, res.text
    data = res.json()
    assert data["status"] == "ingested"
    assert data["findings_count"] == 1
    assert data["tenant_id"] == tenant_id
    assert len(data["security_incidents_triaged"]) == 1

    tenant_read = client.get(
        "/v1/sentinel/findings",
        params={"asset_id": site_id},
        headers=auth_headers(role="cortex_viewer", tenant_id=tenant_id),
    )
    assert tenant_read.status_code == 200, tenant_read.text
    assert tenant_read.json()["total"] == 1
    assert tenant_read.json()["findings"][0]["finding_id"] == "find_api_01"
    assert tenant_read.json()["findings"][0]["sentinel_task_id"] == "task_api_sec_001"

    other_tenant_read = client.get(
        "/v1/sentinel/findings",
        headers=auth_headers(role="cortex_viewer", tenant_id="tenant_other"),
    )
    assert other_tenant_read.status_code == 200
    assert other_tenant_read.json()["findings"] == []
    assert other_tenant_read.json()["total"] == 0

    tenant_exposure = client.get(
        "/v1/sentinel/exposure",
        headers=auth_headers(role="cortex_viewer", tenant_id=tenant_id),
    )
    assert tenant_exposure.status_code == 403
    exp_res = client.get(
        "/v1/sentinel/exposure",
        headers=auth_headers(role="cortex_platform_admin", tenant_id="system"),
    )
    assert exp_res.status_code == 200
    assert "assets" in exp_res.json()


def test_sentinel_scan_rejects_unregistered_asset(monkeypatch, api_client):
    payload = {
        "sentinel_task_id": "task_unknown_asset",
        "asset_id": "site_not_registered_to_any_tenant",
        "posture_score": 99.0,
        "findings": [],
    }
    response = api_client.post(
        "/v1/sentinel/findings",
        headers=friday_headers(monkeypatch),
        json=payload,
    )
    assert response.status_code == 404, response.text


def test_sentinel_scan_replay_replaces_findings_and_preserves_clean_posture(
    monkeypatch, api_client, provisioned_key
):
    _, tenant_id, site_id = provisioned_key
    headers = friday_headers(monkeypatch)
    first = {
        "sentinel_task_id": "task_replayable_scan",
        "asset_id": site_id,
        "posture_score": 61.0,
        "findings": [
            {
                "finding_id": "finding_before_rescan",
                "severity": "medium",
                "title": "Finding discovered before remediation",
                "description": "This finding should disappear after a clean replay.",
            }
        ],
    }
    first_response = api_client.post("/v1/sentinel/findings", headers=headers, json=first)
    assert first_response.status_code == 202, first_response.text
    assert first_response.json()["tenant_id"] == tenant_id

    # The same tenant/site/task now represents a clean re-scan; old findings must be replaced.
    replay = {
        **first,
        "posture_score": 100.0,
        "findings": [],
    }
    replay_response = api_client.post("/v1/sentinel/findings", headers=headers, json=replay)
    assert replay_response.status_code == 202, replay_response.text
    assert replay_response.json()["findings_count"] == 0

    visible = api_client.get(
        "/v1/sentinel/findings",
        params={"asset_id": site_id},
        headers=auth_headers(role="cortex_viewer", tenant_id=tenant_id),
    )
    assert visible.status_code == 200, visible.text
    data = visible.json()
    assert data["findings"] == []
    assert data["total"] == 0
    assert data["posture_score"] == 100.0
    assert data["posture_source"] == "sentinel_push"
