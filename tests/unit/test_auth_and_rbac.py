import os
import sys

import pytest
from fastapi.testclient import TestClient
from jose import jwt

sys.path.insert(0, os.path.abspath("apps/api/src"))

from cortex_api.auth import JWT_SECRET, Role, verify_jwt_token
from cortex_api.main import app


def generate_token(role: str, sub: str = "usr_test") -> str:
    return jwt.encode({"sub": sub, "role": role, "tenant_id": "tenant_test"}, JWT_SECRET, algorithm="HS256")


@pytest.mark.asyncio
async def test_production_jwt_auth_is_unavailable_without_secret(monkeypatch):
    import cortex_api.auth as auth

    monkeypatch.setattr(auth, "APP_ENV", "production")
    monkeypatch.setattr(auth, "JWT_SECRET", "")
    monkeypatch.delenv("RENDER", raising=False)

    with pytest.raises(Exception) as exc:
        await verify_jwt_token(credentials=None)
    assert getattr(exc.value, "status_code", None) == 503


def test_rbac_roles_enforcement():
    client = TestClient(app)

    viewer_token = generate_token(Role.CORTEX_VIEWER.value)
    operator_token = generate_token(Role.CORTEX_OPERATOR.value)
    admin_token = generate_token(Role.CORTEX_ADMIN.value)

    # 1. Viewer can access GET /v1/agents
    res_viewer_agents = client.get("/v1/agents", headers={"Authorization": f"Bearer {viewer_token}"})
    assert res_viewer_agents.status_code == 200

    # 2. Viewer CANNOT trigger actions (POST /v1/actions/:id/approve) — the role
    #    check runs before any lookup, so even a non-existent id is refused 403.
    res_viewer_approve = client.post(
        "/v1/actions/act_rbac_check/approve", json={}, headers={"Authorization": f"Bearer {viewer_token}"}
    )
    assert res_viewer_approve.status_code == 403

    # 3. Operator passes RBAC; an unknown action id is a 404 (no fabricated
    #    in-memory action store serves it any more).
    res_operator_approve = client.post(
        "/v1/actions/act_rbac_check/approve", json={}, headers={"Authorization": f"Bearer {operator_token}"}
    )
    assert res_operator_approve.status_code == 404

    # 4. POST /v1/friday/command uses X-Friday-Api-Key header auth (not JWT Bearer).
    #    With a key configured and MOCK_MODE=false, any JWT Bearer token (even admin)
    #    correctly returns 401 (missing X-Friday-Api-Key header).
    import cortex_api.auth as _auth

    _saved_key = _auth.FRIDAY_API_KEY
    _saved_env_key = os.environ.get("FRIDAY_API_KEY")
    _saved_mock = os.environ.get("MOCK_MODE")
    try:
        _auth.FRIDAY_API_KEY = "rbac_test_secret_999"
        os.environ["FRIDAY_API_KEY"] = "rbac_test_secret_999"
        os.environ["MOCK_MODE"] = "false"

        res_operator_friday = client.post(
            "/v1/friday/command",
            json={"goal": "test", "required_capability": "growth", "requested_action": "page_view"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert (
            res_operator_friday.status_code == 401
        ), f"Expected 401 (missing X-Friday-Api-Key), got {res_operator_friday.status_code}"

        # 5. Admin JWT also returns 401 — FRIDAY uses its own auth scheme, not RBAC.
        res_admin_friday = client.post(
            "/v1/friday/command",
            json={"goal": "test", "required_capability": "growth", "requested_action": "page_view"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert (
            res_admin_friday.status_code == 401
        ), f"Expected 401 (missing X-Friday-Api-Key), got {res_admin_friday.status_code}"
    finally:
        _auth.FRIDAY_API_KEY = _saved_key
        if _saved_env_key is not None:
            os.environ["FRIDAY_API_KEY"] = _saved_env_key
        else:
            os.environ.pop("FRIDAY_API_KEY", None)
        if _saved_mock is not None:
            os.environ["MOCK_MODE"] = _saved_mock
        else:
            os.environ.pop("MOCK_MODE", None)


def test_approval_flow_executes_on_approval(api_client, session_factory):
    """The closed loop: a gated action becomes an approval request, and approving
    it executes the action through the tool bus and records the outcome.

    Regression lock for two defects: (1) the cognitive loop dropped gated
    proposals without ever creating an approval request, and (2) approving an
    approval-queue item only flipped its status — nothing executed. A stub
    endpoint in public_gateway also shadowed this real flow with fabricated
    in-memory actions.
    """
    import asyncio
    from datetime import UTC, datetime, timedelta

    from cortex_api.db_models import ApprovalQueueModel

    from tests.conftest import auth_headers

    approval_id = "appr_rbac_test_1"

    async def _insert() -> None:
        async with session_factory() as session:
            session.add(
                ApprovalQueueModel(
                    id=approval_id,
                    tenant_id="tenant_test",
                    action_type="account_update",
                    target="lead_qualification",
                    params={"tier": "enterprise_tier_1"},
                    rationale="RBAC test approval",
                    evidence_refs=["test"],
                    risk_score=0.8,
                    status="pending",
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
            await session.commit()

    asyncio.run(_insert())

    # Viewer is refused by RBAC before any lookup.
    res = api_client.post(
        f"/v1/actions/{approval_id}/approve", json={}, headers=auth_headers(role="cortex_viewer")
    )
    assert res.status_code == 403

    # While pending, the request is visible in the tenant's approval queue.
    pending = api_client.get("/v1/approvals/pending", headers=auth_headers()).json()
    row = next(item for item in pending if item["id"] == approval_id)
    assert row["execution_status"] is None

    # Operator approves: the action executes and the outcome is recorded.
    res = api_client.post(
        f"/v1/actions/{approval_id}/approve",
        json={"reason": "approved in test"},
        headers=auth_headers(role="cortex_operator"),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "approved"
    assert body["execution"]["tool"] == "account_update"
    assert body["execution"]["status"] in {"executed", "blocked", "skipped"}

    # The row records the execution.
    async def _read() -> dict:
        async with session_factory() as session:
            from sqlalchemy import select

            row = (await session.execute(select(ApprovalQueueModel).where(ApprovalQueueModel.id == approval_id))).scalar_one()
            return {
                "status": row.status,
                "execution_status": row.execution_status,
                "execution_result": row.execution_result,
            }

    state = asyncio.run(_read())
    assert state["status"] == "approved"
    assert state["execution_status"] in {"executed", "blocked", "skipped"}
    assert state["execution_result"] is not None

    # A decided approval leaves the pending list.
    pending = api_client.get("/v1/approvals/pending", headers=auth_headers()).json()
    assert all(item["id"] != approval_id for item in pending)

    # Re-deciding a decided approval is a conflict.
    res = api_client.post(
        f"/v1/actions/{approval_id}/approve", json={}, headers=auth_headers(role="cortex_operator")
    )
    assert res.status_code == 409
