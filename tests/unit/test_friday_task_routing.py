"""The FRIDAY task gateway must fail closed on actions it cannot route.

Live probe that found this: ``POST /v1/friday/task`` with ``action="banner_injection"``
(an operation the property registry allows) returned

    {"status": "SUCCESS", "state": "COMPLETED", "progress": 1.0,
     "stage": "Task processed", "classification": "REAL", ...}

while performing no observation, no recommendation, no approval and no execution. A caller
— including an automated supervisor — would conclude a real change had been applied. The
fallback branch now refuses the request, and the response model no longer defaults to
claiming a real execution.
"""

from __future__ import annotations

import copy
import uuid
from unittest.mock import AsyncMock, MagicMock

from cortex_api.auth import verify_friday_token
from cortex_api.friday_router import FridayTaskResponse
from cortex_api.main import app
from cortex_core.governed_operations import global_governed_engine
from cortex_core.web_property import global_property_registry
from cortex_integrations.deployment_gate import GateVerdict  # noqa: F401  (imported for parity with the router)
from fastapi.testclient import TestClient

_FRIDAY_IDENTITY = {"sub": "friday_system", "role": "friday_system", "tenant_id": "system", "system": "FRIDAY"}


def _client() -> TestClient:
    app.dependency_overrides[verify_friday_token] = lambda: _FRIDAY_IDENTITY
    mock_db = AsyncMock()
    empty_scalars = MagicMock()
    empty_scalars.all.return_value = []
    empty_result = MagicMock()
    empty_result.scalars.return_value = empty_scalars
    mock_db.execute = AsyncMock(return_value=empty_result)
    app.dependency_overrides.clear()
    app.dependency_overrides[verify_friday_token] = lambda: _FRIDAY_IDENTITY
    return TestClient(app)


def test_unrouted_action_fails_closed_and_changes_nothing():
    """An allowed-by-policy but unrouted action must be refused, not acknowledged as done."""
    client = _client()
    before = copy.deepcopy(global_property_registry.get("site_storefront").state_snapshot)
    approvals_before = dict(global_governed_engine.approvals)

    response = client.post(
        "/v1/friday/task",
        json={
            "task_id": f"task_unrouted_{uuid.uuid4().hex[:8]}",
            "action": "banner_injection",
            "payload": {"property_id": "site_storefront", "params": {"variant": "x"}},
        },
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert "Unsupported action 'banner_injection'" in detail
    assert "execute_operation" in detail
    assert "SUCCESS" not in response.text
    assert global_property_registry.get("site_storefront").state_snapshot == before
    assert dict(global_governed_engine.approvals) == approvals_before


def test_task_response_never_defaults_to_claiming_a_real_execution():
    """The wire model must not label unclassified work as REAL."""
    response = FridayTaskResponse(
        task_id="t1",
        status="PENDING",
        state="PENDING",
        progress=0.0,
        stage="queued",
        property_id="site_storefront",
        summary="queued",
    )
    assert response.classification == "UNCLASSIFIED"
    assert response.classification != "REAL"
