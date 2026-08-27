"""
Unit tests for the FRIDAY Cross-System Integration Gateway.

Covers:
  1. verify_friday_token — mock mode bypass, valid key, invalid key, missing key
  2. POST /v1/friday/command — builds EventSchema with friday_system actor,
     calls Orchestrator.run_cognitive_loop(), returns 10-phase trace
  3. GET /v1/friday/health_summary — returns HealthSummary with correct shape
  4. GET /v1/friday/priority_leads — returns priority leads with recommendations
  5. GET /v1/friday/incidents — returns empty list or hypothesis-enriched incidents
  6. FridayCommand Pydantic model validation
  7. ActorType.FRIDAY_SYSTEM presence in event schema

All DB and orchestrator calls are mocked so these run without infrastructure.

Auth pattern for endpoint tests:
  All FRIDAY endpoints use verify_friday_token (X-Friday-Api-Key header).
  Endpoint tests override this dependency via app.dependency_overrides so
  they are completely independent of env-var state — no timing or ordering
  sensitivity between tests.
"""
import os
import sys
import json
import pytest
from datetime import datetime, timedelta
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

for _p in [
    "packages/core/src",
    "packages/event_schema/src",
    "packages/agents/src",
    "packages/ai_universe_adapter/src",
    "packages/tool_runtime/src",
    "packages/integrations/src",
    "packages/policy_engine/src",
    "packages/workflow_engine/src",
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(_p))

# Ensure a clean environment before importing the app
os.environ.setdefault("MOCK_MODE", "true")
os.environ.pop("FRIDAY_API_KEY", None)

from fastapi.testclient import TestClient
from nexus_api.main import app
from nexus_api.config import get_db_session
from nexus_api.auth import verify_friday_token
from nexus_api.db_models import LeadModel, AuditRecordModel, EventModel


# ===========================================================================
# Shared helpers
# ===========================================================================

# A canned FRIDAY identity that all endpoint tests inject via dependency override
_FRIDAY_IDENTITY = {
    "sub": "friday_system",
    "role": "friday_system",
    "tenant_id": "system",
    "system": "FRIDAY",
}


async def _bypass_friday_auth():
    """FastAPI dependency override that bypasses X-Friday-Api-Key for tests."""
    return _FRIDAY_IDENTITY


def _mock_db_empty():
    """AsyncSession mock where every query returns empty results."""
    mock_db = AsyncMock()
    empty_scalars = MagicMock()
    empty_scalars.all.return_value = []
    empty_result = MagicMock()
    empty_result.scalars.return_value = empty_scalars
    empty_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = empty_result
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    return mock_db


def _make_db_override(mock_db):
    async def _override():
        yield mock_db
    return _override


def _client_with_auth_and_db(mock_db):
    """
    Returns a TestClient with both verify_friday_token and get_db_session overridden.
    Always restore overrides in tests using try/finally.
    """
    app.dependency_overrides[verify_friday_token] = _bypass_friday_auth
    app.dependency_overrides[get_db_session] = _make_db_override(mock_db)
    return TestClient(app)


# ===========================================================================
# 1. verify_friday_token — unit-level dependency tests
#    These test the dependency function directly, not the HTTP layer, so they
#    don't touch app.dependency_overrides at all.
# ===========================================================================

@pytest.mark.asyncio
async def test_friday_token_mock_bypass():
    """MOCK_MODE=true + no FRIDAY_API_KEY → bypass returns friday_system identity."""
    import nexus_api.auth as _auth
    original_key = _auth.FRIDAY_API_KEY
    original_env_key = os.environ.get("FRIDAY_API_KEY")
    original_mock = os.environ.get("MOCK_MODE")

    try:
        _auth.FRIDAY_API_KEY = ""
        os.environ.pop("FRIDAY_API_KEY", None)
        os.environ["MOCK_MODE"] = "true"

        result = await verify_friday_token(x_friday_api_key=None)
        assert result["sub"] == "friday_system"
        assert result["role"] == "friday_system"
        assert result["system"] == "FRIDAY"
    finally:
        _auth.FRIDAY_API_KEY = original_key
        if original_env_key is not None:
            os.environ["FRIDAY_API_KEY"] = original_env_key
        else:
            os.environ.pop("FRIDAY_API_KEY", None)
        if original_mock is not None:
            os.environ["MOCK_MODE"] = original_mock
        else:
            os.environ.pop("MOCK_MODE", None)


@pytest.mark.asyncio
async def test_friday_token_valid_key():
    """Correct X-Friday-Api-Key → returns friday_system identity."""
    import nexus_api.auth as _auth
    original_key = _auth.FRIDAY_API_KEY
    original_env_key = os.environ.get("FRIDAY_API_KEY")
    original_mock = os.environ.get("MOCK_MODE")

    try:
        _auth.FRIDAY_API_KEY = "test_secret_xyz_valid"
        os.environ["FRIDAY_API_KEY"] = "test_secret_xyz_valid"
        os.environ["MOCK_MODE"] = "false"

        result = await verify_friday_token(x_friday_api_key="test_secret_xyz_valid")
        assert result["sub"] == "friday_system"
        assert result["role"] == "friday_system"
    finally:
        _auth.FRIDAY_API_KEY = original_key
        if original_env_key is not None:
            os.environ["FRIDAY_API_KEY"] = original_env_key
        else:
            os.environ.pop("FRIDAY_API_KEY", None)
        if original_mock is not None:
            os.environ["MOCK_MODE"] = original_mock
        else:
            os.environ.pop("MOCK_MODE", None)


@pytest.mark.asyncio
async def test_friday_token_invalid_key_raises():
    """Wrong X-Friday-Api-Key → HTTP 403."""
    from fastapi import HTTPException
    import nexus_api.auth as _auth
    original_key = _auth.FRIDAY_API_KEY
    original_env_key = os.environ.get("FRIDAY_API_KEY")
    original_mock = os.environ.get("MOCK_MODE")

    try:
        _auth.FRIDAY_API_KEY = "correct_secret_abc"
        os.environ["FRIDAY_API_KEY"] = "correct_secret_abc"
        os.environ["MOCK_MODE"] = "false"

        with pytest.raises(HTTPException) as exc_info:
            await verify_friday_token(x_friday_api_key="wrong_secret")
        assert exc_info.value.status_code == 403
        assert "Invalid FRIDAY service token" in exc_info.value.detail
    finally:
        _auth.FRIDAY_API_KEY = original_key
        if original_env_key is not None:
            os.environ["FRIDAY_API_KEY"] = original_env_key
        else:
            os.environ.pop("FRIDAY_API_KEY", None)
        if original_mock is not None:
            os.environ["MOCK_MODE"] = original_mock
        else:
            os.environ.pop("MOCK_MODE", None)


@pytest.mark.asyncio
async def test_friday_token_missing_key_raises():
    """Missing X-Friday-Api-Key when a key IS configured → HTTP 401."""
    from fastapi import HTTPException
    import nexus_api.auth as _auth
    original_key = _auth.FRIDAY_API_KEY
    original_env_key = os.environ.get("FRIDAY_API_KEY")
    original_mock = os.environ.get("MOCK_MODE")

    try:
        _auth.FRIDAY_API_KEY = "configured_key_def"
        os.environ["FRIDAY_API_KEY"] = "configured_key_def"
        os.environ["MOCK_MODE"] = "false"

        with pytest.raises(HTTPException) as exc_info:
            await verify_friday_token(x_friday_api_key=None)
        assert exc_info.value.status_code == 401
    finally:
        _auth.FRIDAY_API_KEY = original_key
        if original_env_key is not None:
            os.environ["FRIDAY_API_KEY"] = original_env_key
        else:
            os.environ.pop("FRIDAY_API_KEY", None)
        if original_mock is not None:
            os.environ["MOCK_MODE"] = original_mock
        else:
            os.environ.pop("MOCK_MODE", None)


# ===========================================================================
# 2. POST /v1/friday/command
# ===========================================================================

def test_friday_command_routes_to_cognitive_loop():
    """
    POST /v1/friday/command builds a friday_system EventSchema and returns
    a FridayCommandResponse with the full 10-phase trace.
    """
    mock_db = _mock_db_empty()

    mock_loop_result = {
        "loop_id": "loop_test_abc123",
        "status": "success",
        "trace_id": "fri_trace_test_xyz",
        "agent_id": "agent_sales",
        "decision": "send_demo_invite",
        "executed_actions": 1,
        "trace": [
            {"phase": "1.Observe", "event_id": "fri_test_001", "type": "high_intent.detected"},
            {"phase": "10.Continue", "status": "cycle_complete"},
        ],
    }

    try:
        client = _client_with_auth_and_db(mock_db)

        with patch("nexus_api.friday_router._get_orchestrator") as mock_get_orch:
            mock_orch = MagicMock()
            mock_orch.run_cognitive_loop = AsyncMock(return_value=mock_loop_result)
            mock_get_orch.return_value = mock_orch

            payload = {
                "goal": "Convert enterprise visitor to booked demo",
                "context": {"visitor_id": "vis_ent_001", "company": "BigCorp Inc"},
                "required_capability": "sales",
                "requested_action": "high_intent.detected",
                "site_id": "nexus_main",
                "tenant_id": "tenant_bigcorp",
            }
            res = client.post("/v1/friday/command", json=payload)

        assert res.status_code == 200, res.text
        body = res.json()

        assert body["status"] == "success"
        assert body["nexus_loop_id"] == "loop_test_abc123"
        assert body["agent_id"] == "agent_sales"
        assert body["decision"] == "send_demo_invite"
        assert body["executed_actions"] == 1
        assert len(body["trace"]) == 2
        assert body["trace_id"] == "fri_trace_test_xyz"
        assert "processed_at" in body

        # Verify the orchestrator was called with a properly-formed EventSchema
        mock_orch.run_cognitive_loop.assert_called_once()
        event_arg = mock_orch.run_cognitive_loop.call_args[0][0]
        assert event_arg.actor.type.value == "friday_system"
        assert event_arg.actor.id == "friday_system"
        assert event_arg.type == "high_intent.detected"
        assert event_arg.data["friday_goal"] == "Convert enterprise visitor to booked demo"
        assert event_arg.data["friday_required_capability"] == "sales"
        assert event_arg.source == "friday_command_gateway"
    finally:
        app.dependency_overrides.clear()


def test_friday_command_with_idempotency_key():
    """command_id should equal the client-supplied idempotency_key."""
    mock_db = _mock_db_empty()
    mock_result = {
        "loop_id": "loop_idemp",
        "status": "success",
        "trace_id": "trc_idemp",
        "agent_id": "agent_growth",
        "decision": "inject_banner",
        "executed_actions": 0,
        "trace": [],
    }

    try:
        client = _client_with_auth_and_db(mock_db)

        with patch("nexus_api.friday_router._get_orchestrator") as mock_get_orch:
            mock_orch = MagicMock()
            mock_orch.run_cognitive_loop = AsyncMock(return_value=mock_result)
            mock_get_orch.return_value = mock_orch

            payload = {
                "goal": "Inject retention banner",
                "context": {},
                "required_capability": "growth",
                "requested_action": "exit_intent.detected",
                "idempotency_key": "fri_cmd_unique_key_abc",
            }
            res = client.post("/v1/friday/command", json=payload)

        assert res.status_code == 200
        assert res.json()["command_id"] == "fri_cmd_unique_key_abc"
    finally:
        app.dependency_overrides.clear()


def test_friday_command_orchestrator_error_returns_500():
    """If the cognitive loop raises, the endpoint returns HTTP 500."""
    mock_db = _mock_db_empty()

    try:
        client = _client_with_auth_and_db(mock_db)

        with patch("nexus_api.friday_router._get_orchestrator") as mock_get_orch:
            mock_orch = MagicMock()
            mock_orch.run_cognitive_loop = AsyncMock(
                side_effect=RuntimeError("AI Universe timeout")
            )
            mock_get_orch.return_value = mock_orch

            client_no_raise = TestClient(app, raise_server_exceptions=False)
            payload = {
                "goal": "Test error handling",
                "context": {},
                "required_capability": "reliability",
                "requested_action": "incident.p0",
            }
            res = client_no_raise.post("/v1/friday/command", json=payload)

        assert res.status_code == 500
        assert "AI Universe timeout" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_friday_command_missing_required_fields_returns_422():
    """Missing required fields in FridayCommand should return 422 Unprocessable Entity."""
    try:
        app.dependency_overrides[verify_friday_token] = _bypass_friday_auth
        client = TestClient(app)
        # Missing goal
        res = client.post("/v1/friday/command", json={"required_capability": "sales"})
        assert res.status_code == 422
    finally:
        app.dependency_overrides.clear()


# ===========================================================================
# 3. GET /v1/friday/health_summary
# ===========================================================================

def test_friday_health_summary_empty_db():
    """Health summary returns valid shape and 'healthy' indicator with empty DB."""
    mock_db = _mock_db_empty()
    try:
        client = _client_with_auth_and_db(mock_db)
        res = client.get("/v1/friday/health_summary")

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "ok"
        assert body["uptime_indicator"] == "healthy"
        assert body["active_incidents"] == 0
        assert len(body["active_agents"]) == 4
        assert all(a["status"] == "active" for a in body["active_agents"])
        assert body["recent_errors_24h"] == 0
        assert body["total_events_24h"] == 0
        assert body["cognitive_loops_today"] == 0
        assert "last_checked" in body
    finally:
        app.dependency_overrides.clear()


def test_friday_health_summary_degraded_with_errors():
    """Health summary shows 'degraded' uptime_indicator when error events exist."""
    mock_db = AsyncMock()

    scalars_with_errors = MagicMock()
    scalars_with_errors.all.return_value = ["e1", "e2", "e3"]   # 3 error events

    scalars_empty = MagicMock()
    scalars_empty.all.return_value = []

    # Queries: (1) error count, (2) total events, (3) audit loops
    mock_db.execute.side_effect = [
        MagicMock(scalars=MagicMock(return_value=scalars_with_errors)),
        MagicMock(scalars=MagicMock(return_value=scalars_with_errors)),
        MagicMock(scalars=MagicMock(return_value=scalars_empty)),
    ]
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()

    try:
        client = _client_with_auth_and_db(mock_db)
        res = client.get("/v1/friday/health_summary")

        assert res.status_code == 200
        body = res.json()
        assert body["uptime_indicator"] == "degraded"
        assert body["active_incidents"] == 3
    finally:
        app.dependency_overrides.clear()


def test_friday_health_summary_requires_friday_auth():
    """Calling health_summary without FRIDAY auth should return 401."""
    # No dependency override → real verify_friday_token fires
    # With MOCK_MODE=true and no key configured, mock bypass returns 200.
    # This test verifies the endpoint is wired to the dependency at all.
    import nexus_api.auth as _auth
    original = _auth.FRIDAY_API_KEY
    original_env = os.environ.get("FRIDAY_API_KEY")
    original_mock = os.environ.get("MOCK_MODE")

    try:
        _auth.FRIDAY_API_KEY = "required_key"
        os.environ["FRIDAY_API_KEY"] = "required_key"
        os.environ["MOCK_MODE"] = "false"

        client = TestClient(app)
        res = client.get("/v1/friday/health_summary")   # no X-Friday-Api-Key
        assert res.status_code == 401
    finally:
        _auth.FRIDAY_API_KEY = original
        if original_env is not None:
            os.environ["FRIDAY_API_KEY"] = original_env
        else:
            os.environ.pop("FRIDAY_API_KEY", None)
        if original_mock is not None:
            os.environ["MOCK_MODE"] = original_mock
        else:
            os.environ.pop("MOCK_MODE", None)


# ===========================================================================
# 4. GET /v1/friday/priority_leads
# ===========================================================================

def test_friday_priority_leads_empty_db_returns_demo_data():
    """When no leads exist, priority_leads returns illustrative demo leads."""
    mock_db = _mock_db_empty()
    try:
        client = _client_with_auth_and_db(mock_db)
        res = client.get("/v1/friday/priority_leads")

        assert res.status_code == 200, res.text
        leads = res.json()
        assert len(leads) >= 1
        first = leads[0]
        assert "lead_id" in first
        assert "score" in first
        assert "recommended_action" in first
        assert "intent_signals" in first
        assert first["score"] >= 90.0
        assert any(
            kw in first["recommended_action"].lower()
            for kw in ("immediate", "enterprise", "demo")
        )
    finally:
        app.dependency_overrides.clear()


def test_friday_priority_leads_with_real_leads():
    """Priority leads returns DB leads ordered by score desc with recommendations."""
    mock_db = AsyncMock()

    lead1 = LeadModel(
        id="lead_high_1",
        tenant_id="tenant_test",
        profile_id=None,
        score=88.5,
        status="new",
        source="web",
        lead_metadata={"pricing_views": 5, "demo_requested": True},
        created_at=datetime.utcnow(),
    )
    lead2 = LeadModel(
        id="lead_high_2",
        tenant_id="tenant_test",
        profile_id=None,
        score=72.0,
        status="engaged",
        source="stripe_webhook",
        lead_metadata={"checkout_started": True},
        created_at=datetime.utcnow(),
    )

    scalars = MagicMock()
    scalars.all.return_value = [lead1, lead2]
    mock_res = MagicMock()
    mock_res.scalars.return_value = scalars
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()

    try:
        client = _client_with_auth_and_db(mock_db)
        res = client.get("/v1/friday/priority_leads")

        assert res.status_code == 200
        leads = res.json()
        assert len(leads) == 2
        assert leads[0]["lead_id"] == "lead_high_1"
        assert leads[0]["score"] == 88.5
        assert "Immediate outreach" in leads[0]["recommended_action"]
        assert leads[1]["lead_id"] == "lead_high_2"
        assert any(
            kw in leads[1]["recommended_action"].lower()
            for kw in ("personalised", "send", "case study")
        )
    finally:
        app.dependency_overrides.clear()


# ===========================================================================
# 5. GET /v1/friday/incidents
# ===========================================================================

def test_friday_incidents_empty_returns_empty_list():
    """No incidents in DB → endpoint returns [] (all clear signal to FRIDAY)."""
    mock_db = _mock_db_empty()
    try:
        client = _client_with_auth_and_db(mock_db)
        res = client.get("/v1/friday/incidents")

        assert res.status_code == 200, res.text
        assert res.json() == []
    finally:
        app.dependency_overrides.clear()


def test_friday_incidents_returns_hypothesis():
    """Incidents include deterministic root-cause hypothesis from event payload."""
    mock_db = AsyncMock()

    event = EventModel(
        id="evt_err_001",
        tenant_id="tenant_test",
        site_id="site_main",
        type="error.database_timeout",
        occurred_at=datetime.utcnow(),
        actor_type="system",
        actor_id="worker_01",
        source="worker",
        data={"error_message": "connection timeout after 5000ms", "table": "events"},
        trace_id="trc_err_001",
        server_received_at=datetime.utcnow(),
    )

    scalars = MagicMock()
    scalars.all.return_value = [event]
    mock_res = MagicMock()
    mock_res.scalars.return_value = scalars
    mock_db.execute.return_value = mock_res
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()

    try:
        client = _client_with_auth_and_db(mock_db)
        res = client.get("/v1/friday/incidents")

        assert res.status_code == 200
        incidents = res.json()
        assert len(incidents) == 1
        inc = incidents[0]
        assert inc["incident_id"] == "evt_err_001"
        assert inc["event_type"] == "error.database_timeout"
        assert inc["severity"] == "high"
        assert "timeout" in inc["root_cause_hypothesis"].lower()
        assert inc["affected_site_id"] == "site_main"
    finally:
        app.dependency_overrides.clear()


# ===========================================================================
# 6. FridayCommand Pydantic model validation
# ===========================================================================

def test_friday_command_model_defaults_and_validation():
    """FridayCommand defaults and required-field enforcement."""
    from nexus_api.friday_router import FridayCommand
    from pydantic import ValidationError

    # Valid with defaults
    cmd = FridayCommand(
        goal="Optimise checkout conversion",
        required_capability="sales",
        requested_action="checkout.intent",
    )
    assert cmd.goal == "Optimise checkout conversion"
    assert cmd.site_id == "friday_command"   # default
    assert cmd.tenant_id == "default"        # default
    assert cmd.idempotency_key is None       # optional

    # Missing required field `goal`
    with pytest.raises(ValidationError):
        FridayCommand(required_capability="sales", requested_action="page_view")


def test_friday_actor_type_present_in_schema():
    """ActorType.FRIDAY_SYSTEM must be in the event schema enum."""
    from nexus_event_schema import ActorType
    assert ActorType.FRIDAY_SYSTEM.value == "friday_system"
    assert ActorType.FRIDAY_SYSTEM in list(ActorType)


def test_friday_role_in_hierarchy():
    """Role.FRIDAY_SYSTEM must exist and include all lower roles in the hierarchy."""
    from nexus_api.auth import Role, ROLE_HIERARCHY
    assert Role.FRIDAY_SYSTEM in ROLE_HIERARCHY
    hierarchy = ROLE_HIERARCHY[Role.FRIDAY_SYSTEM]
    assert Role.NEXUS_VIEWER in hierarchy
    assert Role.NEXUS_OPERATOR in hierarchy
    assert Role.NEXUS_ADMIN in hierarchy
    assert Role.FRIDAY_SYSTEM in hierarchy
