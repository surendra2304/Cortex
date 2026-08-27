import os
import sys
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/identity/src"))
sys.path.insert(0, os.path.abspath("apps/api/src"))

from fastapi.testclient import TestClient
from nexus_api.main import app
from nexus_api.config import get_db_session
from nexus_api.db_models import VisitorModel, ProfileModel, LeadModel


def test_identify_pseudonymous_visitor():
    mock_db = AsyncMock()
    # Mock visitor query returning None (create new visitor)
    mock_exec_res = MagicMock()
    mock_exec_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_exec_res
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = override_db
    client = TestClient(app)

    # 1. Identify without user_id
    res = client.post("/v1/identify", json={"visitor_id": "vis_anon_1", "traits": {"country": "US"}})
    assert res.status_code == 200
    data = res.json()["result"]
    assert data["visitor_id"] == "vis_anon_1"
    assert data["is_identified"] is False
    assert data["attributes"]["country"] == "US"

    app.dependency_overrides.clear()


def test_identify_authenticated_profile_stitching():
    mock_db = AsyncMock()
    # Mock existing visitor
    mock_vis = VisitorModel(
        id="vis_anon_2",
        tenant_id="tenant_default",
        site_id="site_1",
        attributes={"plan": "pro"}
    )
    mock_exec_res = MagicMock()
    mock_exec_res.scalar_one_or_none.side_effect = [mock_vis, None]  # 1st: visitor exists, 2nd: profile not yet found
    mock_exec_res.scalars.return_value = []
    mock_db.execute.return_value = mock_exec_res
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = override_db
    client = TestClient(app)

    res = client.post(
        "/v1/identify",
        json={
            "visitor_id": "vis_anon_2",
            "user_id": "usr_real_777",
            "traits": {"email": "alex@enterprise.com", "company": "Acme Inc"}
        }
    )
    assert res.status_code == 200
    data = res.json()["result"]
    assert data["visitor_id"] == "vis_anon_2"
    assert data["is_identified"] is True
    assert data["primary_email"] == "alex@enterprise.com"

    app.dependency_overrides.clear()


def test_get_visitor_and_lead_endpoints():
    mock_db = AsyncMock()
    mock_vis = VisitorModel(
        id="vis_lookup_1",
        tenant_id="tenant_default",
        site_id="site_main",
        profile_id="prof_123",
        attributes={"country": "DE"},
        first_seen_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow()
    )
    mock_prof = ProfileModel(
        id="prof_123",
        tenant_id="tenant_default",
        primary_email="user@de.com",
        identities=[{"user_id": "usr_99"}],
        traits={"tier": "enterprise"}
    )
    mock_lead = LeadModel(
        id="lead_123",
        tenant_id="tenant_default",
        profile_id="prof_123",
        score=95.0,
        status="qualified",
        source="web-sdk",
        lead_metadata={"budget": 50000},
        created_at=datetime.utcnow()
    )

    mock_res_vis = MagicMock()
    mock_res_vis.scalar_one_or_none.side_effect = [mock_vis, mock_prof]
    mock_res_lead = MagicMock()
    mock_res_lead.scalar_one_or_none.return_value = mock_lead

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = override_db
    client = TestClient(app)

    # Test GET /v1/visitors/:id
    mock_db.execute.return_value = mock_res_vis
    res_v = client.get("/v1/visitors/vis_lookup_1")
    assert res_v.status_code == 200
    v_data = res_v.json()["visitor"]
    assert v_data["id"] == "vis_lookup_1"
    assert v_data["profile"]["primary_email"] == "user@de.com"

    # Test GET /v1/leads/:id
    mock_db.execute.return_value = mock_res_lead
    res_l = client.get("/v1/leads/lead_123")
    assert res_l.status_code == 200
    l_data = res_l.json()["lead"]
    assert l_data["id"] == "lead_123"
    assert l_data["score"] == 95.0

    app.dependency_overrides.clear()
