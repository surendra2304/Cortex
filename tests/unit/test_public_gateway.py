import os
import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/event_schema/src"))
sys.path.insert(0, os.path.abspath("packages/agents/src"))
sys.path.insert(0, os.path.abspath("packages/ai_universe_adapter/src"))
sys.path.insert(0, os.path.abspath("apps/api/src"))

from cortex_api.config import get_db_session
from cortex_api.db_models import LeadModel, VisitorModel
from cortex_api.main import app
from fastapi.testclient import TestClient

from tests.conftest import auth_headers


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
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_vis
    mock_db.execute.return_value = mock_res

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = override_db
    client = TestClient(app)

    headers = auth_headers()
    res = client.get("/v1/visitors/vis_123", headers=headers)
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
        created_at=datetime.now(UTC),
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

    metadata = {"email": "lead@corp.com", "name": "Test Contact", "company": "Example"}
    headers = auth_headers()
    res = client.post(
        "/v1/leads",
        headers=headers,
        json={
            "profile_id": "profile_test_1",
            "status": "new",
            "source": "website",
            "metadata": metadata,
        },
    )
    assert res.status_code == 200
    lead = res.json()["lead"]
    assert lead["status"] == "new"
    assert lead["score"] == 50.0
    stored_lead = mock_db.add.call_args.args[0]
    assert stored_lead.profile_id == "profile_test_1"
    assert stored_lead.source == "website"
    assert stored_lead.lead_metadata == metadata

    res_list = client.get("/v1/leads", headers=headers)
    assert res_list.status_code == 200
    assert res_list.json()["total"] >= 1

    app.dependency_overrides.clear()


def test_public_gateway_agents():
    client = TestClient(app)
    # Audit C4: these endpoints used to be anonymous. They now require a JWT;
    # the assertions below cover both the rejection and the authorised path.
    assert client.get("/v1/agents").status_code == 401
    headers = auth_headers()
    res = client.get("/v1/agents", headers=headers)
    assert res.status_code == 200
    agents = res.json()["agents"]
    assert len(agents) == 4

    run_payload = {"goal": "Test run", "context": {"site": "demo"}, "events": []}
    res_run = client.post("/v1/agents/agent_growth/run", json=run_payload, headers=headers)
    assert res_run.status_code == 200
    assert res_run.json()["output"]["agent_id"] == "agent_growth"


def test_public_gateway_actions_and_audit(api_client, session_factory):
    """The audit endpoint reads persisted records, so this test needs the DB override.

    Using a bare TestClient made it depend on the process-wide engine, i.e. on a
    data/cortex.db that happens to exist next to the checkout.

    The approval flow is the real one: a pending approval-queue row (created by
    the cognitive loop when the policy gates an action) is approved and executed
    through the tool bus. The fabricated in-memory action store that used to
    shadow this endpoint was removed (route-shadowing + fabricated-data defect).
    """
    import asyncio
    from datetime import timedelta

    from cortex_api.db_models import ApprovalQueueModel

    client = api_client
    approval_id = "appr_gateway_test_1"

    async def _insert() -> None:
        async with session_factory() as session:
            session.add(
                ApprovalQueueModel(
                    id=approval_id,
                    tenant_id="tenant_test",
                    action_type="account_update",
                    target="lead_qualification",
                    params={"tier": "enterprise_tier_1"},
                    rationale="gateway test approval",
                    evidence_refs=["test"],
                    risk_score=0.8,
                    status="pending",
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
            await session.commit()

    asyncio.run(_insert())

    # Audit C4: approving a high-impact action must require an authenticated operator.
    assert client.post(f"/v1/actions/{approval_id}/approve").status_code == 401
    headers = auth_headers()
    res_appr = client.post(f"/v1/actions/{approval_id}/approve", headers=headers)
    assert res_appr.status_code == 200, res_appr.text
    assert res_appr.json()["status"] == "approved"
    assert res_appr.json()["execution"]["tool"] == "account_update"

    res_audit = client.get("/v1/audit/actions", headers=headers)
    assert res_audit.status_code == 200
    assert res_audit.json()["resource_type"] == "actions"


def test_public_gateway_health():
    """The existing /v1/health endpoint should remain reachable after FRIDAY router changes."""
    client = TestClient(app)
    res = client.get("/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"
