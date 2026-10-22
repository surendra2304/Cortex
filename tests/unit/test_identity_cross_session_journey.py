"""Tests for Identity Graph Linking and Cross-Session Research Journeys."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from cortex_api.db_models import EventModel, ProfileModel, SessionModel, VisitorModel
from cortex_identity import IdentityResolver
from sqlalchemy import select

from tests.conftest import auth_headers

TENANT_A = "tenant_test"
TENANT_B = "tenant_other"


@pytest.mark.asyncio
async def test_identity_cross_session_research_journey(session_factory):
    resolver = IdentityResolver()
    visitor_id = "vis_journey_test_1"
    now = datetime.now(UTC)

    async with session_factory() as session:
        # 1. Create two sessions for visitor_id under TENANT_A
        session.add(
            SessionModel(
                id="ses_j_1",
                tenant_id=TENANT_A,
                site_id="site_a",
                visitor_id=visitor_id,
                started_at=now - timedelta(hours=2),
                ended_at=now - timedelta(hours=1, minutes=45),
                created_at=now - timedelta(hours=2),
            )
        )
        session.add(
            SessionModel(
                id="ses_j_2",
                tenant_id=TENANT_A,
                site_id="site_a",
                visitor_id=visitor_id,
                started_at=now - timedelta(minutes=30),
                ended_at=now,
                created_at=now - timedelta(minutes=30),
            )
        )
        # Session for another tenant under same visitor_id
        session.add(
            SessionModel(
                id="ses_alien_j",
                tenant_id=TENANT_B,
                site_id="site_b",
                visitor_id=visitor_id,
                started_at=now,
                created_at=now,
            )
        )

        # 2. Add events for visitor_id
        session.add(
            EventModel(
                id="evt_j_1",
                tenant_id=TENANT_A,
                site_id="site_a",
                session_id="ses_j_1",
                type="page_view",
                occurred_at=now - timedelta(hours=2),
                actor_id=visitor_id,
                actor_type="visitor",
                server_received_at=now,
            )
        )
        session.add(
            EventModel(
                id="evt_j_2",
                tenant_id=TENANT_A,
                site_id="site_a",
                session_id="ses_j_2",
                type="whitepaper_download",
                occurred_at=now - timedelta(minutes=20),
                actor_id=visitor_id,
                actor_type="visitor",
                server_received_at=now,
            )
        )
        await session.commit()

    # 3. Identify visitor
    async with session_factory() as session:
        res = await resolver.resolve_identity(
            db=session,
            visitor_id=visitor_id,
            email="researcher@enterprise.com",
            tenant_id=TENANT_A,
            site_id="site_a",
            consent_granted=True,
            traits={"industry": "Biotech"},
        )

        assert res["is_identified"] is True
        assert res["primary_email"] == "researcher@enterprise.com"
        assert res["journey"]["session_count"] == 2
        assert set(res["journey"]["session_ids"]) == {"ses_j_1", "ses_j_2"}
        assert "ses_alien_j" not in res["journey"]["session_ids"]
        assert res["journey"]["total_events"] == 2
        assert res["traits"]["journey"]["session_count"] == 2


def test_visitor_profile_endpoint_returns_session_journey(api_client, session_factory):
    visitor_id = "vis_endpoint_journey_1"
    now = datetime.now(UTC)

    async def _seed():
        async with session_factory() as session:
            session.add(
                VisitorModel(
                    id=visitor_id,
                    tenant_id=TENANT_A,
                    site_id="site_a",
                    attributes={"interest": "AI"},
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
            session.add(
                SessionModel(
                    id="ses_vp_1",
                    tenant_id=TENANT_A,
                    site_id="site_a",
                    visitor_id=visitor_id,
                    started_at=now,
                    created_at=now,
                )
            )
            await session.commit()

    asyncio.run(_seed())

    headers = auth_headers(role="cortex_viewer", tenant_id=TENANT_A)
    res = api_client.get(f"/v1/visitors/{visitor_id}/profile", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["visitor_id"] == visitor_id
    assert data["sessions_count"] == 1
    assert data["sessions"][0]["id"] == "ses_vp_1"
