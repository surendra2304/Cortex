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

    # 4. Operator CANNOT invoke Friday admin command
    res_operator_friday = client.post("/v1/friday/command", json={"command": "recalibrate"}, headers={"Authorization": f"Bearer {operator_token}"})
    assert res_operator_friday.status_code == 403

    # 5. Admin CAN invoke Friday command
    res_admin_friday = client.post("/v1/friday/command", json={"command": "recalibrate"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin_friday.status_code == 200
    assert res_admin_friday.json()["status"] == "acknowledged"
