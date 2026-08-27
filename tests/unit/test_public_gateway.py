import os
import sys
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/event_schema/src"))
sys.path.insert(0, os.path.abspath("packages/agents/src"))
sys.path.insert(0, os.path.abspath("packages/ai_universe_adapter/src"))
sys.path.insert(0, os.path.abspath("apps/api/src"))

from fastapi.testclient import TestClient
from nexus_api.main import app
from nexus_api.config import get_db_session
from nexus_api.db_models import VisitorModel, LeadModel


def test_tracing_header_propagation():
    client = TestClient(app)
    res = client.get("/v1/health", headers={"X-Trace-ID": "trc_custom_999"})
    assert res.status_code == 200
    assert res.headers.get("X-Trace-ID") == "trc_custom_999"


def test_public_gateway_visitors():
    mock_db = AsyncMock()
    mock_vis = VisitorModel(
        id="vis_123",
        tenant_id="tenant_1",
        site_id="site_main",
        profile_id=None,
        attributes={"country": "US", "browser": "Chrome"},
        first_seen_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow()
    )
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_vis
    mock_db.execute.return_value = mock_res

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = override_db
    client = TestClient(app)

    res = client.get("/v1/visitors/vis_123")
    assert res.status_code == 200
    data = res.json()
    assert data["visitor"]["id"] == "vis_123"
    assert "trace_id" in data

    app.dependency_overrides.clear()


def test_public_gateway_leads():
    mock_db = AsyncMock()
    mock_lead = LeadModel(
        id="lead_test_1",
        tenant_id="tenant_default",
        profile_id=None,
        score=90.0,
        status="new",
        source="web",
        lead_metadata={"email": "lead@corp.com"},
        created_at=datetime.utcnow()
    )
    mock_res_list = MagicMock()
    mock_res_list.scalars.return_value.all.return_value = [mock_lead]
    mock_db.execute.return_value = mock_res_list
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = override_db
    client = TestClient(app)

    res = client.post("/v1/leads", json={"email": "lead@corp.com", "score": 90.0})
    assert res.status_code == 200
    lead = res.json()["lead"]
    assert lead["score"] == 90.0

    res_list = client.get("/v1/leads")
    assert res_list.status_code == 200
    assert res_list.json()["total"] >= 1

    app.dependency_overrides.clear()


def test_public_gateway_agents():
    client = TestClient(app)
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
    client = TestClient(app)
    res_appr = client.post("/v1/actions/act_high_1/approve")
    assert res_appr.status_code == 200
    assert res_appr.json()["action"]["status"] == "approved"

    res_audit = client.get("/v1/audit/actions")
    assert res_audit.status_code == 200
    assert res_audit.json()["resource_type"] == "actions"


def test_friday_command_bridge():
    client = TestClient(app)
    res = client.post("/v1/friday/command", json={"command": "STATUS_REPORT"})
    assert res.status_code == 200
    assert res.json()["executed_by"] == "FRIDAY_SUPERVISOR_BRIDGE"
