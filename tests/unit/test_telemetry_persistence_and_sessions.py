"""Tests for Session Telemetry Persistence and Strict Tenant Isolation."""

import asyncio
from datetime import UTC, datetime

from cortex_api.db_models import EventModel, SessionModel
from sqlalchemy import select

from tests.conftest import auth_headers, event_payload

TENANT_A = "tenant_test"
TENANT_B = "tenant_other"
SITE_A = "site_test"


def test_event_ingestion_creates_and_updates_session_in_db(api_client, provisioned_key, session_factory):
    pub_key, tenant_id, site_id = provisioned_key
    headers = {"X-Cortex-Public-Key": pub_key}

    session_id = "ses_telemetry_live_1"
    evt1 = event_payload(
        event_id="evt_tel_1",
        tenant_id=tenant_id,
        site_id=site_id,
        session_id=session_id,
        actor={"type": "visitor", "id": "vis_tel_1"},
    )

    res1 = api_client.post("/v1/events", json=evt1, headers=headers)
    assert res1.status_code == 200
    assert res1.json()["status"] == "accepted"

    # Verify session is persisted in database
    async def _check_session():
        async with session_factory() as session:
            s = (await session.execute(select(SessionModel).where(SessionModel.id == session_id))).scalar_one_or_none()
            assert s is not None
            assert s.tenant_id == tenant_id
            assert s.site_id == site_id
            assert s.visitor_id == "vis_tel_1"
            assert s.started_at is not None
            assert s.ended_at is not None
            return s.started_at, s.ended_at

    started_at, ended_at = asyncio.run(_check_session())

    # Send second event in same session with slightly later timestamp
    evt2 = event_payload(
        event_id="evt_tel_2",
        tenant_id=tenant_id,
        site_id=site_id,
        session_id=session_id,
        actor={"type": "visitor", "id": "vis_tel_1"},
        occurred_at=datetime.now(UTC).isoformat(),
    )
    res2 = api_client.post("/v1/events", json=evt2, headers=headers)
    assert res2.status_code == 200

    # Verify session row was updated, not duplicated
    async def _check_count_and_ended():
        async with session_factory() as session:
            rows = (
                (await session.execute(select(SessionModel).where(SessionModel.id == session_id))).scalars().all()
            )
            assert len(rows) == 1
            assert rows[0].ended_at >= started_at

    asyncio.run(_check_count_and_ended())


def test_batch_event_ingestion_creates_sessions(api_client, provisioned_key, session_factory):
    pub_key, tenant_id, site_id = provisioned_key
    headers = {"X-Cortex-Public-Key": pub_key}

    batch = [
        event_payload(
            event_id="evt_batch_s1_1",
            tenant_id=tenant_id,
            site_id=site_id,
            session_id="ses_batch_1",
            actor={"type": "visitor", "id": "vis_batch_1"},
        ),
        event_payload(
            event_id="evt_batch_s1_2",
            tenant_id=tenant_id,
            site_id=site_id,
            session_id="ses_batch_1",
            actor={"type": "visitor", "id": "vis_batch_1"},
        ),
        event_payload(
            event_id="evt_batch_s2_1",
            tenant_id=tenant_id,
            site_id=site_id,
            session_id="ses_batch_2",
            actor={"type": "visitor", "id": "vis_batch_2"},
        ),
    ]

    res = api_client.post("/v1/events/batch", json=batch, headers=headers)
    assert res.status_code == 200
    assert len(res.json()) == 3
    assert all(r["status"] == "accepted" for r in res.json())

    async def _verify():
        async with session_factory() as session:
            s1 = (await session.execute(select(SessionModel).where(SessionModel.id == "ses_batch_1"))).scalar_one_or_none()
            s2 = (await session.execute(select(SessionModel).where(SessionModel.id == "ses_batch_2"))).scalar_one_or_none()
            assert s1 is not None and s1.tenant_id == tenant_id
            assert s2 is not None and s2.tenant_id == tenant_id

    asyncio.run(_verify())


def test_cross_tenant_session_injection_is_forbidden_403(api_client, provisioned_key, session_factory):
    pub_key, tenant_id, site_id = provisioned_key
    headers = {"X-Cortex-Public-Key": pub_key}

    # Seed an existing session for another tenant
    async def _seed_other_tenant_session():
        async with session_factory() as session:
            session.add(
                SessionModel(
                    id="ses_alien_victim_99",
                    tenant_id=TENANT_B,
                    site_id="site_other",
                    visitor_id="vis_other",
                    started_at=datetime.now(UTC),
                    created_at=datetime.now(UTC),
                )
            )
            await session.commit()

    asyncio.run(_seed_other_tenant_session())

    # Tenant A attempts to ingest an event claiming the other tenant's session_id
    malicious_event = event_payload(
        event_id="evt_spoofed_session",
        tenant_id=tenant_id,
        site_id=site_id,
        session_id="ses_alien_victim_99",
    )

    res = api_client.post("/v1/events", json=malicious_event, headers=headers)
    assert res.status_code == 403
    assert "Cross-tenant session access forbidden" in res.json()["detail"]


def test_sessions_query_and_replay_enforces_tenant_isolation(api_client, session_factory):
    async def _seed():
        async with session_factory() as session:
            session.add(
                SessionModel(
                    id="ses_iso_a",
                    tenant_id=TENANT_A,
                    site_id=SITE_A,
                    visitor_id="vis_a",
                    user_agent="Mozilla/5.0",
                    ip_address="192.168.1.1",
                    started_at=datetime.now(UTC),
                    created_at=datetime.now(UTC),
                )
            )
            session.add(
                EventModel(
                    id="evt_iso_a_1",
                    tenant_id=TENANT_A,
                    site_id=SITE_A,
                    session_id="ses_iso_a",
                    type="page_view",
                    occurred_at=datetime.now(UTC),
                    actor_type="visitor",
                    actor_id="vis_a",
                    source="web-sdk",
                    data={"page": "/home"},
                    server_received_at=datetime.now(UTC),
                )
            )
            session.add(
                SessionModel(
                    id="ses_iso_b",
                    tenant_id=TENANT_B,
                    site_id="site_b",
                    visitor_id="vis_b",
                    started_at=datetime.now(UTC),
                    created_at=datetime.now(UTC),
                )
            )
            await session.commit()

    asyncio.run(_seed())

    auth_a = auth_headers(tenant_id=TENANT_A)
    auth_b = auth_headers(tenant_id=TENANT_B)

    # 1. Listing is tenant-scoped
    res_list_a = api_client.get("/v1/sessions", headers=auth_a)
    assert res_list_a.status_code == 200
    ids_a = [s["id"] for s in res_list_a.json()]
    assert "ses_iso_a" in ids_a
    assert "ses_iso_b" not in ids_a

    # 2. Get session detail
    res_detail_own = api_client.get("/v1/sessions/ses_iso_a", headers=auth_a)
    assert res_detail_own.status_code == 200
    assert res_detail_own.json()["id"] == "ses_iso_a"
    assert res_detail_own.json()["event_count"] >= 1

    # Cross-tenant get session detail returns 404
    res_detail_cross = api_client.get("/v1/sessions/ses_iso_a", headers=auth_b)
    assert res_detail_cross.status_code == 404

    # 3. Session replay
    res_replay_own = api_client.get("/v1/sessions/ses_iso_a/replay", headers=auth_a)
    assert res_replay_own.status_code == 200
    assert res_replay_own.json()["session_id"] == "ses_iso_a"
    assert res_replay_own.json()["total_events"] >= 1

    # Cross-tenant session replay returns 404
    res_replay_cross = api_client.get("/v1/sessions/ses_iso_a/replay", headers=auth_b)
    assert res_replay_cross.status_code == 404
