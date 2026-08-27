import os
import sys
import pytest
from fastapi.testclient import TestClient
from jose import jwt

sys.path.insert(0, os.path.abspath("apps/api/src"))

from nexus_api.main import app
from nexus_api.auth import JWT_SECRET, Role


def generate_token(role: str, sub: str = "usr_test") -> str:
    return jwt.encode({"sub": sub, "role": role, "tenant_id": "tenant_test"}, JWT_SECRET, algorithm="HS256")


def test_rbac_roles_enforcement():
    client = TestClient(app)

    viewer_token = generate_token(Role.NEXUS_VIEWER.value)
    operator_token = generate_token(Role.NEXUS_OPERATOR.value)
    admin_token = generate_token(Role.NEXUS_ADMIN.value)

    # 1. Viewer can access GET /v1/agents
    res_viewer_agents = client.get("/v1/agents", headers={"Authorization": f"Bearer {viewer_token}"})
    assert res_viewer_agents.status_code == 200

    # 2. Viewer CANNOT trigger actions (POST /v1/actions/:id/approve)
    res_viewer_approve = client.post("/v1/actions/act_high_1/approve", json={}, headers={"Authorization": f"Bearer {viewer_token}"})
    assert res_viewer_approve.status_code == 403

    # 3. Operator CAN trigger action approval
    res_operator_approve = client.post("/v1/actions/act_high_1/approve", json={}, headers={"Authorization": f"Bearer {operator_token}"})
    assert res_operator_approve.status_code == 200
    assert res_operator_approve.json()["status"] == "approved"

    # 4. POST /v1/friday/command uses X-Friday-Api-Key header auth (not JWT Bearer).
    #    With a key configured and MOCK_MODE=false, any JWT Bearer token (even admin)
    #    correctly returns 401 (missing X-Friday-Api-Key header).
    import nexus_api.auth as _auth
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
        assert res_operator_friday.status_code == 401, \
            f"Expected 401 (missing X-Friday-Api-Key), got {res_operator_friday.status_code}"

        # 5. Admin JWT also returns 401 — FRIDAY uses its own auth scheme, not RBAC.
        res_admin_friday = client.post(
            "/v1/friday/command",
            json={"goal": "test", "required_capability": "growth", "requested_action": "page_view"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res_admin_friday.status_code == 401, \
            f"Expected 401 (missing X-Friday-Api-Key), got {res_admin_friday.status_code}"
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
