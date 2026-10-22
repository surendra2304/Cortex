"""Invariant locks: compliance/telemetry endpoints must never invent data.

Live-testing the running API showed four endpoints returning fabricated values regardless
of what was stored (a synthesized ``aud_sample_1`` audit row, three hardcoded audit export
records, a fixed 184500/850 usage meter, and a canned analytics series). For an
observability product that is the worst possible failure mode: dashboards and audit trails
that look populated while recording nothing.
"""

from __future__ import annotations

import asyncio

from cortex_api.db_models import AuditRecordModel, EventModel

from tests.conftest import auth_headers, event_payload


def test_audit_logs_are_empty_when_nothing_was_recorded(api_client):
    """No synthesized rows: an empty audit trail reads as empty, not as 'aud_sample_1'."""
    response = api_client.get("/v1/audit/actions", headers=auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["logs"] == []
    assert body["count"] == 0
    assert "aud_sample" not in response.text


def test_audit_logs_reflect_persisted_records(api_client, session_factory):
    from datetime import UTC, datetime

    async def _insert() -> None:
        async with session_factory() as session:
            session.add(
                AuditRecordModel(
                    id="aud_real_1",
                    tenant_id="tenant_test",
                    actor_id="usr_test",
                    action="event.read",
                    target_resource="events",
                    changes={},
                    trace_id="trc_real",
                    timestamp=datetime.now(UTC),
                )
            )
            await session.commit()

    asyncio.run(_insert())
    body = api_client.get("/v1/audit/event", headers=auth_headers()).json()
    assert [row["id"] for row in body["logs"]] == ["aud_real_1"]
    assert body["logs"][0]["actor_id"] == "usr_test"


def test_audit_logs_reject_cross_tenant_reads(api_client):
    """A viewer cannot read another tenant's audit trail by changing a query parameter."""
    from tests.conftest import auth_headers as mint

    response = api_client.get("/v1/audit/actions?tenant_id=tenant_victim", headers=mint(role="cortex_operator"))
    assert response.status_code == 403
    assert "Cross-tenant" in response.json()["detail"]


def test_audit_export_has_no_sample_records(api_client):
    """The compliance export used to inject three invented records when the DB was empty."""
    response = api_client.get("/audit/export", headers=auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["total_audit_records"] == 0
    assert body["records"] == []


def test_analytics_metrics_are_event_derived(api_client, provisioned_key):
    """The analytics series must count stored events, and unsupported metrics must say so."""
    plaintext, tenant_id, site_id = provisioned_key
    for index in range(4):
        assert (
            api_client.post(
                "/v1/events",
                json=event_payload(event_id=f"evt_an_{index}"),
                headers={"X-Cortex-Public-Key": plaintext},
            ).status_code
            == 200
        )

    body = api_client.get("/v1/analytics/page_views", headers=auth_headers()).json()
    assert body["supported"] is True
    assert sum(point["value"] for point in body["values"]) == 4
    assert "2026-08-27" not in str(body["values"])

    unsupported = api_client.get("/v1/analytics/revenue", headers=auth_headers()).json()
    assert unsupported["supported"] is False
    assert unsupported["values"] == []
    assert "no aggregation source" in unsupported["note"]


def test_event_model_is_the_metering_source(api_client, session_factory, provisioned_key):
    """Guard against re-introducing hardcoded meters: the DB row count is the contract."""
    plaintext, tenant_id, site_id = provisioned_key
    api_client.post(
        "/v1/events", json=event_payload(event_id="evt_meter_lock"), headers={"X-Cortex-Public-Key": plaintext}
    )

    async def _count() -> int:
        from sqlalchemy import func, select

        async with session_factory() as session:
            return (
                await session.execute(
                    select(func.count()).select_from(EventModel).where(EventModel.tenant_id == tenant_id)
                )
            ).scalar_one()

    rows = asyncio.run(_count())
    row = api_client.get("/v1/tenant/usage", headers=auth_headers()).json()
    assert row["events_ingested"] == rows
