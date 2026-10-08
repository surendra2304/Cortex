"""Cross-tenant read isolation (IDOR regression locks, upgrade 2026-10-07).

Live-confirmed defect: ``GET /v1/visitors/{id}`` and ``GET /v1/leads/{id}``
looked records up by id alone, so a JWT for tenant B read tenant A's visitor
profile (including email) and lead. The orchestrator's Contextualize lookups had
the same gap. These tests lock the tenant scoping on every id-based read path.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/event_schema/src"))
sys.path.insert(0, os.path.abspath("packages/agents/src"))
sys.path.insert(0, os.path.abspath("packages/ai_universe_adapter/src"))
sys.path.insert(0, os.path.abspath("packages/tool_runtime/src"))
sys.path.insert(0, os.path.abspath("packages/integrations/src"))
sys.path.insert(0, os.path.abspath("packages/policy_engine/src"))
sys.path.insert(0, os.path.abspath("packages/identity/src"))
sys.path.insert(0, os.path.abspath("apps/api/src"))

from cortex_api.db_models import LeadModel, ProfileModel, VisitorModel

from tests.conftest import auth_headers

OWN_TENANT = "tenant_test"
OTHER_TENANT = "tenant_other"
VISITOR_ID = "vis_idor_lock_1"
PROFILE_ID = "prof_idor_lock_1"
LEAD_ID = "lead_idor_lock_1"


def test_cross_tenant_visitor_read_is_404(api_client, session_factory):
    _seed_with(session_factory)
    own = auth_headers(tenant_id=OWN_TENANT)
    other = auth_headers(tenant_id=OTHER_TENANT)

    # Own tenant can read its visitor (with profile).
    res = api_client.get(f"/v1/visitors/{VISITOR_ID}", headers=own)
    assert res.status_code == 200
    assert res.json()["visitor"]["profile"]["primary_email"] == "victim@example.com"

    # Another tenant must not — not even learn that the id exists.
    res = api_client.get(f"/v1/visitors/{VISITOR_ID}", headers=other)
    assert res.status_code == 404
    assert "victim@example.com" not in res.text


def test_cross_tenant_lead_read_is_404(api_client, session_factory):
    _seed_with(session_factory)
    own = auth_headers(tenant_id=OWN_TENANT)
    other = auth_headers(tenant_id=OTHER_TENANT)

    res = api_client.get(f"/v1/leads/{LEAD_ID}", headers=own)
    assert res.status_code == 200
    assert res.json()["lead"]["id"] == LEAD_ID

    res = api_client.get(f"/v1/leads/{LEAD_ID}", headers=other)
    assert res.status_code == 404
    assert "victim@example.com" not in res.text


def test_lead_lists_are_tenant_scoped(api_client, session_factory):
    _seed_with(session_factory)

    own = api_client.get("/v1/leads", headers=auth_headers(tenant_id=OWN_TENANT)).json()
    assert {lead["id"] for lead in own["leads"]} == {LEAD_ID}

    other = api_client.get("/v1/leads", headers=auth_headers(tenant_id=OTHER_TENANT)).json()
    assert {lead["id"] for lead in other["leads"]} == {"lead_other_1"}


def test_understand_router_scoped_reads_stay_scoped(api_client, session_factory):
    """Regression lock: the understand-layer id reads were already tenant-scoped."""
    _seed_with(session_factory)
    other = auth_headers(tenant_id=OTHER_TENANT)

    res = api_client.get(f"/v1/leads/{LEAD_ID}/score", headers=other)
    assert res.status_code == 404

    res = api_client.get(f"/v1/visitors/{VISITOR_ID}/profile", headers=other)
    assert res.status_code == 404


def _seed_with(session_factory) -> None:
    """Seed through the test session factory (the DB the api_client override uses)."""

    async def _insert() -> None:
        async with session_factory() as session:
            session.add(
                VisitorModel(
                    id=VISITOR_ID,
                    tenant_id=OWN_TENANT,
                    site_id="site_test",
                    profile_id=PROFILE_ID,
                    attributes={"email": "victim@example.com"},
                    first_seen_at=datetime.now(UTC),
                    last_seen_at=datetime.now(UTC),
                )
            )
            session.add(
                ProfileModel(
                    id=PROFILE_ID,
                    tenant_id=OWN_TENANT,
                    primary_email="victim@example.com",
                    identities=[],
                    traits={},
                )
            )
            session.add(
                LeadModel(
                    id=LEAD_ID,
                    tenant_id=OWN_TENANT,
                    profile_id=PROFILE_ID,
                    score=0.9,
                    status="new",
                    source="test",
                    lead_metadata={"email": "victim@example.com"},
                )
            )
            session.add(
                LeadModel(
                    id="lead_other_1",
                    tenant_id=OTHER_TENANT,
                    profile_id="prof_other_1",
                    score=0.1,
                    status="new",
                    source="test",
                    lead_metadata={},
                )
            )
            await session.commit()

    asyncio.run(_insert())
