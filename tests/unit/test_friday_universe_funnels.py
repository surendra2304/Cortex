"""
Unit and integration tests for FRIDAY Universe Funnels, Web Property Governance, and SDK routes.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
import jwt
import pytest
from cortex_analytics.funnels import (
    FridayConversionGoalType,
    FridayUniverseFunnelManager,
    FunnelAnalysisReport,
    global_funnel_manager,
)
from cortex_api import auth as auth_module
from cortex_api.auth import Role
from cortex_core.web_property import global_property_registry
from fastapi.testclient import TestClient

SECRET = "unit-test-secret-at-least-32-bytes-long!!"


def _auth_headers(role: Role = Role.CORTEX_ADMIN, tenant_id: str = "tenant_universe") -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": "tester_universe",
            "role": role.value,
            "tenant_id": tenant_id,
            "exp": datetime.now(UTC) + timedelta(minutes=10),
        },
        SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def configure_auth(monkeypatch):
    monkeypatch.setattr(auth_module, "JWT_SECRET", SECRET)
    monkeypatch.setattr(auth_module, "OIDC_JWKS_URL", "")
    monkeypatch.setattr(auth_module, "DEV_AUTH_BYPASS", False)


def test_friday_universe_web_property_registered() -> None:
    prop = global_property_registry.get("site_friday_universe")
    assert prop is not None
    assert prop.property_id == "site_friday_universe"
    assert "https://friday-universe.duckdns.org" in prop.allowed_domains
    assert prop.is_domain_allowed("https://friday-universe.duckdns.org")
    assert prop.is_operation_allowed("funnel_track")
    assert prop.is_operation_allowed("mab_optimize")


def test_friday_universe_funnel_manager_definitions() -> None:
    mgr = FridayUniverseFunnelManager()
    funnels = mgr.list_funnels()
    assert len(funnels) == 4

    # Option A: Demo
    f_demo = mgr.get_funnel("funnel_enterprise_demo")
    assert f_demo is not None
    assert f_demo.primary_goal == FridayConversionGoalType.DEMO_BOOKING
    assert len(f_demo.steps) == 3

    # Option B: SaaS
    f_saas = mgr.get_funnel("funnel_saas_subscription")
    assert f_saas is not None
    assert f_saas.primary_goal == FridayConversionGoalType.PAID_SUBSCRIPTION
    assert len(f_saas.steps) == 3

    # Option C: Waitlist
    f_waitlist = mgr.get_funnel("funnel_waitlist_signup")
    assert f_waitlist is not None
    assert f_waitlist.primary_goal == FridayConversionGoalType.WAITLIST_SIGNUP
    assert len(f_waitlist.steps) == 3

    # Option D: 10-Agent Journey
    f_journey = mgr.get_funnel("funnel_10_agent_mesh_journey")
    assert f_journey is not None
    assert f_journey.primary_goal == FridayConversionGoalType.MULTI_STEP_JOURNEY
    assert len(f_journey.steps) == 4


def test_funnel_evaluation_and_drop_off() -> None:
    mgr = FridayUniverseFunnelManager()

    # Session 1: completed all 4 steps of 10-Agent Journey
    now = datetime.now(UTC)
    s1_events = [
        {"type": "page_view", "path": "/", "occurred_at": (now - timedelta(minutes=5)).isoformat()},
        {"type": "agent_showcase_explore", "path": "/agents", "occurred_at": (now - timedelta(minutes=4)).isoformat()},
        {"type": "pricing_view", "path": "/pricing", "occurred_at": (now - timedelta(minutes=3)).isoformat()},
        {"type": "checkout_completed", "path": "/convert", "occurred_at": (now - timedelta(minutes=2)).isoformat()},
    ]

    # Session 2: dropped off at step 2 (pricing)
    s2_events = [
        {"type": "page_view", "path": "/", "occurred_at": (now - timedelta(minutes=10)).isoformat()},
        {"type": "agent_showcase_explore", "path": "/agents", "occurred_at": (now - timedelta(minutes=9)).isoformat()},
    ]

    # Session 3: bounced after homepage
    s3_events = [
        {"type": "page_view", "path": "/", "occurred_at": (now - timedelta(minutes=20)).isoformat()},
    ]

    sessions = {"sess_1": s1_events, "sess_2": s2_events, "sess_3": s3_events}
    report = mgr.evaluate_funnel("funnel_10_agent_mesh_journey", sessions)

    assert isinstance(report, FunnelAnalysisReport)
    assert report.total_sessions_analyzed == 3
    assert report.completed_sessions == 1
    assert 33.0 <= report.overall_conversion_rate_pct <= 34.0
    assert report.steps[0].visitors_reached == 3
    assert report.steps[1].visitors_reached == 2
    assert report.steps[2].visitors_reached == 1
    assert report.steps[3].visitors_reached == 1


def test_seed_associated_bandit_experiments() -> None:
    mgr = FridayUniverseFunnelManager()
    exp_ids = mgr.seed_associated_bandit_experiments("tenant_universe")
    assert len(exp_ids) == 4
    assert "exp_enterprise_demo_cta" in exp_ids
    assert "exp_saas_pricing_tier" in exp_ids
    assert "exp_developer_waitlist_hook" in exp_ids
    assert "exp_agent_mesh_onboarding" in exp_ids


def test_funnel_api_endpoints(api_client: TestClient) -> None:
    viewer_headers = _auth_headers(Role.CORTEX_VIEWER)
    operator_headers = _auth_headers(Role.CORTEX_OPERATOR)

    # 1. Definitions
    resp_def = api_client.get("/v1/funnels/definitions", headers=viewer_headers)
    assert resp_def.status_code == 200
    defs = resp_def.json()
    assert len(defs) == 4

    # 2. Friday Universe Status
    resp_status = api_client.get("/v1/funnels/friday-universe", headers=viewer_headers)
    assert resp_status.status_code == 200
    status_data = resp_status.json()
    assert status_data["site_id"] == "site_friday_universe"
    assert status_data["domain"] == "https://friday-universe.duckdns.org"

    # 3. Seed MAB Experiments
    resp_seed = api_client.post("/v1/funnels/seed-bandit-experiments", headers=operator_headers)
    assert resp_seed.status_code == 200
    seed_data = resp_seed.json()
    assert len(seed_data["seeded_experiment_ids"]) == 4

    # 4. Evaluate funnel
    eval_payload = {
        "sessions_events": {
            "s1": [{"type": "page_view", "path": "/"}],
        }
    }
    resp_eval = api_client.post(
        "/v1/funnels/funnel_enterprise_demo/evaluate",
        json=eval_payload,
        headers=viewer_headers,
    )
    assert resp_eval.status_code == 200
    eval_data = resp_eval.json()
    assert eval_data["funnel_id"] == "funnel_enterprise_demo"


def test_sdk_script_endpoints(api_client: TestClient) -> None:
    # Test GET /sdk.js and /cortex.js
    resp_sdk = api_client.get("/sdk.js")
    assert resp_sdk.status_code == 200
    assert "javascript" in resp_sdk.headers.get("content-type", "").lower()
    assert len(resp_sdk.content) > 1000

    resp_cortex = api_client.get("/cortex.js")
    assert resp_cortex.status_code == 200
    assert "javascript" in resp_cortex.headers.get("content-type", "").lower()


def test_sdk_script_endpoints_fallback(api_client: TestClient, monkeypatch: Any) -> None:
    # Test GET /sdk.js when disk file is absent (e.g. fresh clone in CI)
    import cortex_api.main as main_mod

    monkeypatch.setattr(main_mod, "_sdk_script_path", lambda: None)
    resp = api_client.get("/sdk.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers.get("content-type", "").lower()
    assert len(resp.content) > 1000
    assert b"window.Cortex" in resp.content

