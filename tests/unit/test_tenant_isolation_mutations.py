"""Tests for Strict Tenant Isolation on Mutations (cross-tenant 403, missing 404)."""

import asyncio
from datetime import UTC, datetime, timedelta

from cortex_api.db_models import ApprovalQueueModel, VisitorModel

from tests.conftest import auth_headers

TENANT_OWN = "tenant_test"
TENANT_OTHER = "tenant_other"
ACTION_ID_OTHER = "act_alien_999"
VISITOR_ID_OTHER = "vis_alien_888"


def test_cross_tenant_approval_is_forbidden_403(api_client, session_factory):
    async def _seed():
        async with session_factory() as session:
            session.add(
                ApprovalQueueModel(
                    id=ACTION_ID_OTHER,
                    tenant_id=TENANT_OTHER,
                    action_type="send_email",
                    target="user@example.com",
                    params={},
                    rationale="Test approval",
                    risk_score=0.8,
                    status="pending",
                    created_at=datetime.now(UTC),
                    expires_at=datetime.now(UTC) + timedelta(hours=24),
                )
            )
            await session.commit()

    asyncio.run(_seed())

    own_operator = auth_headers(role="cortex_operator", tenant_id=TENANT_OWN)
    other_operator = auth_headers(role="cortex_operator", tenant_id=TENANT_OTHER)

    # 1. Tenant A trying to approve Tenant B's action returns 403 Forbidden
    res_cross = api_client.post(f"/v1/actions/{ACTION_ID_OTHER}/approve", json={"reason": "Hacking"}, headers=own_operator)
    assert res_cross.status_code == 403
    assert "Cross-tenant action update forbidden" in res_cross.json()["detail"]

    # 2. Tenant A trying to reject Tenant B's action returns 403 Forbidden
    res_cross_reject = api_client.post(f"/v1/actions/{ACTION_ID_OTHER}/reject", json={"reason": "Hacking"}, headers=own_operator)
    assert res_cross_reject.status_code == 403
    assert "Cross-tenant action update forbidden" in res_cross_reject.json()["detail"]

    # 3. Nonexistent action returns 404 Not Found
    res_missing = api_client.post("/v1/actions/act_nonexistent_000/approve", json={}, headers=own_operator)
    assert res_missing.status_code == 404

    # 4. Legitimate tenant B operator can reject their own action
    res_legit = api_client.post(f"/v1/actions/{ACTION_ID_OTHER}/reject", json={"reason": "Normal rejection"}, headers=other_operator)
    assert res_legit.status_code == 200
    assert res_legit.json()["status"] == "rejected"


def test_cross_tenant_visitor_erasure_is_forbidden_403(api_client, session_factory):
    async def _seed():
        async with session_factory() as session:
            session.add(
                VisitorModel(
                    id=VISITOR_ID_OTHER,
                    tenant_id=TENANT_OTHER,
                    site_id="site_other",
                    attributes={"email": "victim@other.com"},
                    first_seen_at=datetime.now(UTC),
                    last_seen_at=datetime.now(UTC),
                )
            )
            await session.commit()

    asyncio.run(_seed())

    own_admin = auth_headers(role="cortex_admin", tenant_id=TENANT_OWN)
    other_admin = auth_headers(role="cortex_admin", tenant_id=TENANT_OTHER)

    # 1. Tenant A trying to erase Tenant B's visitor returns 403 Forbidden
    res_cross = api_client.post(f"/v1/privacy/delete/{VISITOR_ID_OTHER}", headers=own_admin)
    assert res_cross.status_code == 403
    assert "Cross-tenant visitor deletion forbidden" in res_cross.json()["detail"]

    # 2. Nonexistent visitor erasure returns 404 Not Found
    res_missing = api_client.post("/v1/privacy/delete/vis_does_not_exist_xyz", headers=own_admin)
    assert res_missing.status_code == 404

    # 3. Tenant B admin can erase their own visitor
    res_legit = api_client.post(f"/v1/privacy/delete/{VISITOR_ID_OTHER}", headers=other_admin)
    assert res_legit.status_code == 200
    assert "purged_records" in res_legit.json()


def test_cross_tenant_identity_resolve_is_forbidden_403(api_client, session_factory):
    async def _seed():
        async with session_factory() as session:
            session.add(
                VisitorModel(
                    id="vis_exclusive_b",
                    tenant_id=TENANT_OTHER,
                    site_id="site_other",
                    attributes={},
                    first_seen_at=datetime.now(UTC),
                    last_seen_at=datetime.now(UTC),
                )
            )
            await session.commit()

    asyncio.run(_seed())

    own_admin = auth_headers(role="cortex_admin", tenant_id=TENANT_OWN)

    payload = {
        "visitor_id": "vis_exclusive_b",
        "email": "hijack@example.com",
        "consent_granted": True,
    }

    res = api_client.post("/v1/identity/resolve", json=payload, headers=own_admin)
    assert res.status_code == 403
    assert "Cross-tenant visitor access forbidden" in res.json()["detail"]
