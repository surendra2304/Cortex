"""
Unit and integration tests for Advanced Operations API v4 endpoints:
- Multi-Armed Bandit:
  - POST /v1/experiments/bandit/create
  - POST /v1/experiments/bandit/select-arm
  - POST /v1/experiments/bandit/record-reward
  - GET  /v1/experiments/bandit/{experiment_id}
- External CRM & Commerce Sync Queue:
  - POST /v1/integrations/sync/enqueue
  - GET  /v1/integrations/sync/jobs
  - GET  /v1/integrations/sync/cursor
  - POST /v1/integrations/sync/process
- Streaming Telemetry Anomaly Detector:
  - POST /v1/analytics/anomalies/evaluate
  - GET  /v1/analytics/anomalies/incidents
- Cryptographic Tamper-Evident Compliance Ledger:
  - POST /v1/compliance/ledger/record
  - GET  /v1/compliance/ledger/blocks
  - GET  /v1/compliance/ledger/verify
  - GET  /v1/compliance/ledger/proof/{block_index}
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import jwt
import pytest
from cortex_api import auth as auth_module
from cortex_api.auth import Role
from fastapi.testclient import TestClient

SECRET = "unit-test-secret-at-least-32-bytes-long!!"


def _auth_headers(role: Role = Role.CORTEX_ADMIN, tenant_id: str = "tenant_adv_v4") -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": "tester_v4",
            "role": role.value,
            "tenant_id": tenant_id,
            "exp": datetime.now(UTC) + timedelta(minutes=10),
        },
        SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def configure_auth(monkeypatch):
    monkeypatch.setattr(auth_module, "JWT_SECRET", SECRET)
    monkeypatch.setattr(auth_module, "OIDC_JWKS_URL", "")
    monkeypatch.setattr(auth_module, "DEV_AUTH_BYPASS", False)


# ── 1. Multi-Armed Bandit Tests ───────────────────────────────────────────────


def test_bandit_api_lifecycle(api_client: TestClient):
    headers = _auth_headers(Role.CORTEX_OPERATOR)
    viewer_headers = _auth_headers(Role.CORTEX_VIEWER)

    # 1. Create experiment
    payload = {
        "experiment_id": "api-bandit-1",
        "name": "API Banner Bandit",
        "algorithm": "thompson_sampling",
        "arm_configs": [
            {"arm_id": "arm_blue", "label": "Blue Banner"},
            {"arm_id": "arm_green", "label": "Green Banner"},
        ],
    }
    resp = api_client.post("/v1/experiments/bandit/create", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["experiment_id"] == "api-bandit-1"
    assert len(data["arms"]) == 2

    # 2. Select arm
    sel_resp = api_client.post(
        "/v1/experiments/bandit/select-arm",
        json={"experiment_id": "api-bandit-1", "context": {"device": "mobile"}},
        headers=viewer_headers,
    )
    assert sel_resp.status_code == 200
    sel_data = sel_resp.json()
    assert sel_data["arm_id"] in ["arm_blue", "arm_green"]

    # 3. Record reward
    rew_resp = api_client.post(
        "/v1/experiments/bandit/record-reward",
        json={"experiment_id": "api-bandit-1", "arm_id": sel_data["arm_id"], "converted": True},
        headers=headers,
    )
    assert rew_resp.status_code == 200
    rew_data = rew_resp.json()
    assert rew_data["arms"][sel_data["arm_id"]]["conversions"] == 1

    # 4. Get status
    get_resp = api_client.get("/v1/experiments/bandit/api-bandit-1", headers=viewer_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["experiment_id"] == "api-bandit-1"


# ── 2. External Sync Queue Tests ──────────────────────────────────────────────


def test_sync_queue_api_lifecycle(api_client: TestClient):
    headers = _auth_headers(Role.CORTEX_OPERATOR)
    viewer_headers = _auth_headers(Role.CORTEX_VIEWER)

    # 1. Enqueue sync job
    job_payload = {
        "provider": "hubspot",
        "entity_type": "contact",
        "external_id": "hub-999",
        "payload": {"firstname": "Sarah", "email": "sarah@tech.co"},
        "direction": "outbound",
    }
    resp = api_client.post("/v1/integrations/sync/enqueue", json=job_payload, headers=headers)
    assert resp.status_code == 200
    job_data = resp.json()
    assert job_data["status"] == "QUEUED"
    assert job_data["provider"] == "hubspot"

    # 2. List jobs
    list_resp = api_client.get("/v1/integrations/sync/jobs?provider=hubspot", headers=viewer_headers)
    assert list_resp.status_code == 200
    jobs = list_resp.json()
    assert len(jobs) >= 1

    # 3. Get cursor
    cursor_resp = api_client.get(
        "/v1/integrations/sync/cursor?provider=hubspot&entity_type=contact",
        headers=viewer_headers,
    )
    assert cursor_resp.status_code == 200
    cursor_data = cursor_resp.json()
    assert cursor_data["cursor_token"] is not None

    # 4. Process pending sync batch
    proc_resp = api_client.post("/v1/integrations/sync/process", json={"max_jobs": 10}, headers=headers)
    assert proc_resp.status_code == 200
    proc_data = proc_resp.json()
    assert proc_data["processed_count"] >= 1


# ── 3. Streaming Anomaly Detector Tests ────────────────────────────────────────


def test_telemetry_anomaly_api(api_client: TestClient):
    headers = _auth_headers(Role.CORTEX_OPERATOR)
    viewer_headers = _auth_headers(Role.CORTEX_VIEWER)

    # Ingest baseline points
    for _ in range(15):
        resp = api_client.post(
            "/v1/analytics/anomalies/evaluate",
            json={"metric_name": "latency_p95", "value": 100.0},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["is_anomalous"] is False

    # Ingest massive spike
    spike_resp = api_client.post(
        "/v1/analytics/anomalies/evaluate",
        json={"metric_name": "latency_p95", "value": 5000.0, "cooldown_seconds": 0.0},
        headers=headers,
    )
    assert spike_resp.status_code == 200
    spike_data = spike_resp.json()
    assert spike_data["is_anomalous"] is True
    assert spike_data["incident"]["observed_value"] == 5000.0

    # List incidents
    inc_resp = api_client.get("/v1/analytics/anomalies/incidents", headers=viewer_headers)
    assert inc_resp.status_code == 200
    incidents = inc_resp.json()
    assert len(incidents) >= 1


# ── 4. Compliance & Audit Ledger Tests ─────────────────────────────────────────


def test_compliance_ledger_api(api_client: TestClient):
    headers = _auth_headers(Role.CORTEX_OPERATOR)
    viewer_headers = _auth_headers(Role.CORTEX_VIEWER)

    # 1. Record block
    rec_resp = api_client.post(
        "/v1/compliance/ledger/record",
        json={
            "action_type": "HIGH_IMPACT_APPROVAL_EXECUTED",
            "actor_id": "operator_42",
            "payload": {"resource": "cortex-core-gateway", "approved": True},
        },
        headers=headers,
    )
    assert rec_resp.status_code == 200
    block_data = rec_resp.json()
    assert block_data["block_index"] == 0
    assert len(block_data["signature"]) == 64

    # 2. List blocks
    list_resp = api_client.get("/v1/compliance/ledger/blocks", headers=viewer_headers)
    assert list_resp.status_code == 200
    blocks = list_resp.json()
    assert len(blocks) == 1

    # 3. Verify ledger integrity
    ver_resp = api_client.get("/v1/compliance/ledger/verify", headers=viewer_headers)
    assert ver_resp.status_code == 200
    ver_data = ver_resp.json()
    assert ver_data["is_valid"] is True
    assert ver_data["total_blocks"] == 1
    assert ver_data["merkle_root"] is not None

    # 4. Get Merkle proof
    proof_resp = api_client.get("/v1/compliance/ledger/proof/0", headers=viewer_headers)
    assert proof_resp.status_code == 200
    proof_data = proof_resp.json()
    assert proof_data["block_index"] == 0
    assert proof_data["verified"] is True
