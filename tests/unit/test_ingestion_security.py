"""Regression tests for the ingestion gateway security contract.

Covers audit defects:
  C1 — unauthenticated cross-tenant event injection
  C5 — silent "accepted" responses when nothing was persisted
  H3 — batch ingestion acknowledging unpersisted events
"""

from __future__ import annotations

import asyncio

from cortex_api.db_models import EventModel
from sqlalchemy import select

from tests.conftest import event_payload


def test_ingestion_requires_a_public_key(api_client):
    """C1: no credential ⇒ 401, and nothing reaches the event store."""
    response = api_client.post("/v1/events", json=event_payload())
    assert response.status_code == 401
    assert "X-Cortex-Public-Key" in response.json()["detail"]


def test_ingestion_rejects_unknown_key(api_client):
    response = api_client.post("/v1/events", json=event_payload(), headers={"X-Cortex-Public-Key": "pk_live_deadbeef"})
    assert response.status_code == 401


def test_ingestion_rejects_cross_tenant_payload(api_client, provisioned_key):
    """C1: a valid key cannot write into a different tenant."""
    plaintext, tenant_id, site_id = provisioned_key
    response = api_client.post(
        "/v1/events",
        json=event_payload(tenant_id="victim_corp"),
        headers={"X-Cortex-Public-Key": plaintext},
    )
    assert response.status_code == 403
    assert "Tenant mismatch" in response.json()["detail"]


def test_ingestion_rejects_key_scoped_to_another_site(api_client, provisioned_key):
    plaintext, _, _ = provisioned_key
    response = api_client.post(
        "/v1/events",
        json=event_payload(site_id="some_other_site"),
        headers={"X-Cortex-Public-Key": plaintext},
    )
    assert response.status_code == 403


def test_ingestion_persists_and_dispatches(api_client, session_factory, fake_redis, provisioned_key):
    """Happy path: credential-derived tenant, durable row, stream dispatch."""
    plaintext, tenant_id, site_id = provisioned_key
    response = api_client.post(
        "/v1/events",
        json=event_payload(event_id="evt_persist_1"),
        headers={"X-Cortex-Public-Key": plaintext},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert body["dispatched"] is True

    async def _read():
        async with session_factory() as session:
            rows = (await session.execute(select(EventModel))).scalars().all()
            return [(row.id, row.tenant_id, row.site_id) for row in rows]

    rows = asyncio.run(_read())
    assert rows == [("evt_persist_1", tenant_id, site_id)]
    assert len(fake_redis.streams) == 1

    async def _read_last_used():
        from cortex_api.db_models import ApiKeyModel

        async with session_factory() as session:
            key = (await session.execute(select(ApiKeyModel))).scalars().first()
            return key.last_used_at is not None

    assert asyncio.run(_read_last_used()) is True


def test_neutral_tenant_placeholder_is_accepted(api_client, session_factory, provisioned_key):
    """The browser SDK sends tenant_id="default"; the credential decides the tenant."""
    plaintext, tenant_id, _ = provisioned_key
    response = api_client.post(
        "/v1/events",
        json=event_payload(event_id="evt_sdk_default", tenant_id="default"),
        headers={"X-Cortex-Public-Key": plaintext},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"

    async def _stored_tenant():
        async with session_factory() as session:
            row = (await session.execute(select(EventModel).where(EventModel.id == "evt_sdk_default"))).scalar_one()
            return row.tenant_id

    assert asyncio.run(_stored_tenant()) == tenant_id


def test_duplicate_event_is_idempotent(api_client, session_factory, fake_redis, provisioned_key):
    """C5/§23.5: duplicate event_ids are acknowledged once and never double-written."""
    plaintext, _, _ = provisioned_key
    headers = {"X-Cortex-Public-Key": plaintext}
    first = api_client.post("/v1/events", json=event_payload(event_id="evt_dup_1"), headers=headers)
    second = api_client.post("/v1/events", json=event_payload(event_id="evt_dup_1"), headers=headers)

    assert first.json()["status"] == "accepted"
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert second.json()["dispatched"] is False

    async def _count():
        async with session_factory() as session:
            return len((await session.execute(select(EventModel))).scalars().all())

    assert asyncio.run(_count()) == 1
    assert len(fake_redis.streams) == 1


def test_persistence_failure_is_not_reported_as_accepted(api_client, provisioned_key, monkeypatch):
    """C5: a failed write must never surface as 'accepted'."""
    plaintext, _, _ = provisioned_key
    from cortex_api import events_router

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated storage failure")

    monkeypatch.setattr(events_router, "_to_model", _boom)
    response = api_client.post(
        "/v1/events",
        json=event_payload(event_id="evt_fail_1"),
        headers={"X-Cortex-Public-Key": plaintext},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "not_persisted"
    assert response.json()["dispatched"] is False


def test_batch_requires_uniform_site_and_key(api_client, provisioned_key):
    """H3: a batch mixing sites is rejected instead of silently writing events[0]'s site."""
    plaintext, _, site_id = provisioned_key
    headers = {"X-Cortex-Public-Key": plaintext}
    mixed = [event_payload(event_id="evt_b1", site_id=site_id), event_payload(event_id="evt_b2", site_id="other_site")]
    response = api_client.post("/v1/events/batch", json=mixed, headers=headers)
    assert response.status_code == 400
    assert "same site_id" in response.json()["detail"]


def test_batch_persists_all_events(api_client, session_factory, provisioned_key):
    plaintext, tenant_id, site_id = provisioned_key
    headers = {"X-Cortex-Public-Key": plaintext}
    batch = [event_payload(event_id=f"evt_batch_{i}") for i in range(3)]
    response = api_client.post("/v1/events/batch", json=batch, headers=headers)
    assert response.status_code == 200
    assert [item["status"] for item in response.json()] == ["accepted"] * 3

    async def _count():
        async with session_factory() as session:
            rows = (await session.execute(select(EventModel))).scalars().all()
            return {(row.id, row.tenant_id) for row in rows}

    assert asyncio.run(_count()) == {(f"evt_batch_{i}", tenant_id) for i in range(3)}


def test_batch_replays_are_idempotent(api_client, session_factory, provisioned_key):
    plaintext, _, _ = provisioned_key
    headers = {"X-Cortex-Public-Key": plaintext}
    batch = [event_payload(event_id=f"evt_replay_{i}") for i in range(2)]
    assert api_client.post("/v1/events/batch", json=batch, headers=headers).status_code == 200
    second = api_client.post("/v1/events/batch", json=batch, headers=headers)
    assert [item["status"] for item in second.json()] == ["duplicate", "duplicate"]

    async def _count():
        async with session_factory() as session:
            return len((await session.execute(select(EventModel))).scalars().all())

    assert asyncio.run(_count()) == 2


def test_batch_enforces_max_size(api_client, provisioned_key):
    plaintext, _, _ = provisioned_key
    headers = {"X-Cortex-Public-Key": plaintext}
    oversized = [event_payload(event_id=f"evt_big_{i}") for i in range(51)]
    assert api_client.post("/v1/events/batch", json=oversized, headers=headers).status_code == 400


def test_query_events_rejects_unauthenticated_in_production(api_client, provisioned_key, monkeypatch):
    """H1/C4: production refuses anonymous reads; development bypass is honoured only there."""
    from cortex_api import auth

    monkeypatch.setattr(auth, "DEV_AUTH_BYPASS", False)
    assert api_client.get("/v1/events").status_code == 401


def test_query_events_is_tenant_scoped(api_client, session_factory, provisioned_key, monkeypatch):
    """H1: an authenticated viewer sees only their own tenant's events."""
    from cortex_api import auth
    from jose import jwt

    monkeypatch.setattr(auth, "DEV_AUTH_BYPASS", False)
    plaintext, tenant_id, site_id = provisioned_key
    api_client.post(
        "/v1/events", json=event_payload(event_id="evt_scope_1"), headers={"X-Cortex-Public-Key": plaintext}
    )

    async def _insert_foreign():
        async with session_factory() as session:
            session.add(
                EventModel(
                    id="evt_foreign",
                    tenant_id="other_tenant",
                    site_id="other_site",
                    type="page_view",
                    occurred_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                    actor_type="visitor",
                    actor_id="vis_foreign",
                    source="web-sdk",
                    data={},
                    server_received_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                )
            )
            await session.commit()

    asyncio.run(_insert_foreign())

    token = jwt.encode({"sub": "usr_viewer", "role": "cortex_viewer", "tenant_id": tenant_id}, "", algorithm="HS256")
    response = api_client.get("/v1/events", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    ids = {row["event_id"] for row in response.json()}
    assert ids == {"evt_scope_1"}


def _viewer_token(tenant_id: str) -> str:
    from jose import jwt

    return jwt.encode({"sub": "usr_viewer", "role": "cortex_viewer", "tenant_id": tenant_id}, "", algorithm="HS256")


def test_query_events_paginates_beyond_the_page_cap(api_client, session_factory, provisioned_key):
    """M2: the read path must expose a tenant's whole history, not only the newest 200 rows.

    Found by ``scripts/pressure_test.py``: the endpoint clamped ``limit`` to 200 and had no
    ``offset``, so every accepted event older than the 200 most recent ones was unreadable.
    """
    from datetime import UTC, datetime, timedelta

    plaintext, tenant_id, site_id = provisioned_key
    base = datetime.now(UTC)

    async def _insert_many():
        async with session_factory() as session:
            for index in range(450):
                session.add(
                    EventModel(
                        id=f"evt_page_{index:04d}",
                        tenant_id=tenant_id,
                        site_id=site_id,
                        type="page_view",
                        occurred_at=base + timedelta(seconds=index),
                        actor_type="visitor",
                        actor_id=f"vis_{index}",
                        source="web-sdk",
                        data={},
                        server_received_at=base,
                    )
                )
            await session.commit()

    asyncio.run(_insert_many())

    headers = {"Authorization": f"Bearer {_viewer_token(tenant_id)}"}
    first = api_client.get("/v1/events", params={"limit": 200}, headers=headers)
    assert first.status_code == 200
    assert len(first.json()) == 200

    second = api_client.get("/v1/events", params={"limit": 200, "offset": 200}, headers=headers)
    assert second.status_code == 200
    second_ids = [row["event_id"] for row in second.json()]
    assert second_ids, "offset must reach events the first page could not show"
    assert not set(second_ids) & {row["event_id"] for row in first.json()}, "pages must not overlap"

    third = api_client.get("/v1/events", params={"limit": 200, "offset": 400}, headers=headers)
    assert third.status_code == 200
    seen = {row["event_id"] for row in first.json() + second.json() + third.json()}
    assert {f"evt_page_{index:04d}" for index in range(450)} <= seen

    # The clamp still protects the server from absurd page sizes.
    assert len(api_client.get("/v1/events", params={"limit": 10_000}, headers=headers).json()) <= 200


def test_query_events_surfaces_database_failures(api_client, provisioned_key, monkeypatch):
    """M2: a failing query must be a 5xx, never an empty page pretending the tenant has no data."""
    plaintext, tenant_id, site_id = provisioned_key
    headers = {"Authorization": f"Bearer {_viewer_token(tenant_id)}"}

    class _BrokenSession:
        async def execute(self, *_args, **_kwargs):
            raise RuntimeError("database is on fire")

    from cortex_api.config import get_db_session
    from cortex_api.main import app

    async def _broken() -> _BrokenSession:
        return _BrokenSession()

    app.dependency_overrides[get_db_session] = _broken
    try:
        response = api_client.get("/v1/events", headers=headers)
    finally:
        app.dependency_overrides.pop(get_db_session, None)

    assert response.status_code == 500, response.text
    assert response.json()["detail"] == "event query failed"
