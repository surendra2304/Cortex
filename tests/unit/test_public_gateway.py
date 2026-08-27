import os
import sys
import pytest
from datetime import datetime

sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/event_schema/src"))
sys.path.insert(0, os.path.abspath("packages/agents/src"))
sys.path.insert(0, os.path.abspath("packages/ai_universe_adapter/src"))
sys.path.insert(0, os.path.abspath("apps/api/src"))

from fastapi.testclient import TestClient
from nexus_api.main import app

client = TestClient(app)


def test_tracing_header_propagation():
    res = client.get("/v1/health", headers={"X-Trace-ID": "trc_custom_999"})
    assert res.status_code == 200
    assert res.headers.get("X-Trace-ID") == "trc_custom_999"


def test_public_gateway_visitors():
    res = client.get("/v1/visitors/vis_123")
    assert res.status_code == 200
    data = res.json()
    assert data["visitor"]["id"] == "vis_123"
    assert "trace_id" in data


def test_public_gateway_leads():
    res = client.post("/v1/leads", json={"email": "lead@corp.com", "score": 90.0})
    assert res.status_code == 200
    lead = res.json()["lead"]
    assert lead["score"] == 90.0

    res_list = client.get("/v1/leads")
    assert res_list.status_code == 200
    assert res_list.json()["total"] >= 1


def test_public_gateway_agents():
    res = client.get("/v1/agents")
    assert res.status_code == 200
    agents = res.json()["agents"]
    assert len(agents) == 4

    run_payload = {
        "goal": "Test run",
        "context": {"site": "demo"},
        "events": []
    }
    res_run = client.post("/v1/agents/agent_growth/run", json=run_payload)
    assert res_run.status_code == 200
    assert res_run.json()["output"]["agent_id"] == "agent_growth"


def test_public_gateway_actions_and_audit():
    res_appr = client.post("/v1/actions/act_high_1/approve")
    assert res_appr.status_code == 200
    assert res_appr.json()["action"]["status"] == "approved"

    res_audit = client.get("/v1/audit/actions")
    assert res_audit.status_code == 200
    assert res_audit.json()["resource_type"] == "actions"


def test_friday_command_bridge():
    res = client.post("/v1/friday/command", json={"command": "STATUS_REPORT"})
    assert res.status_code == 200
    assert res.json()["executed_by"] == "FRIDAY_SUPERVISOR_BRIDGE"
