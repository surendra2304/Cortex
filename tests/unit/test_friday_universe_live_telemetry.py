"""
Unit & integration tests simulating live telemetry ingestion from https://friday-universe.duckdns.org via @cortex/sdk.
"""

from datetime import UTC, datetime, timedelta
import jwt
from typing import Any
import pytest
from fastapi.testclient import TestClient

from cortex_analytics.funnels import global_funnel_manager
from cortex_api import auth as auth_module
from cortex_api.auth import Role

SECRET = "unit-test-secret-at-least-32-bytes-long!!"


def _admin_headers(tenant_id: str = "tenant_test") -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": "admin_universe",
            "role": Role.CORTEX_ADMIN.value,
            "tenant_id": tenant_id,
            "exp": datetime.now(UTC) + timedelta(minutes=15),
        },
        SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def override_jwt_secret(monkeypatch: Any):
    monkeypatch.setattr(auth_module, "JWT_SECRET", SECRET)


def test_live_telemetry_sdk_ingestion_lifecycle(api_client: TestClient, provisioned_key: tuple[str, str, str]):
    """
    Simulates real visitor telemetry emitted from @cortex/sdk embedded on https://friday-universe.duckdns.org.
    """
    plaintext_key, tenant_id, site_id = provisioned_key
    visitor_id = "vid_universe_live_1001"
    session_id = "ses_universe_live_2001"

    headers = {
        "X-Cortex-Public-Key": plaintext_key,
        "X-Site-ID": site_id,
    }

    # 1. Visitor arrives on landing page
    event_landing = {
        "event_id": f"evt_landing_{visitor_id}",
        "tenant_id": tenant_id,
        "type": "page_view_home",
        "site_id": site_id,
        "session_id": session_id,
        "actor": {"id": visitor_id, "type": "visitor"},
        "data": {
            "url": "https://friday-universe.duckdns.org",
            "title": "FRIDAY Universe — Autonomous AI Operating System",
            "referrer": "https://news.ycombinator.com",
            "utm_source": "hackernews",
            "utm_medium": "referral",
        },
    }
    resp1 = api_client.post("/v1/events", json=event_landing, headers=headers)
    assert resp1.status_code in (200, 202)

    # 2. Visitor explores the 10-Agent showcase
    event_agents = {
        "event_id": f"evt_agents_{visitor_id}",
        "tenant_id": tenant_id,
        "type": "agent_showcase_viewed",
        "site_id": site_id,
        "session_id": session_id,
        "actor": {"id": visitor_id, "type": "visitor"},
        "data": {"agent_focused": "Cortex", "active_tab": "CRM & Telemetry Operations"},
    }
    resp2 = api_client.post("/v1/events", json=event_agents, headers=headers)
    assert resp2.status_code in (200, 202)

    # 3. Visitor triggers a rage click on an interactive element
    event_rage = {
        "event_id": f"evt_rage_{visitor_id}",
        "tenant_id": tenant_id,
        "type": "rage_click",
        "site_id": site_id,
        "session_id": session_id,
        "actor": {"id": visitor_id, "type": "visitor"},
        "data": {"selector": "button#interactive-mesh-demo", "click_count": 6, "duration_ms": 780},
    }
    resp3 = api_client.post("/v1/events", json=event_rage, headers=headers)
    assert resp3.status_code in (200, 202)

    # 4. Visitor views pricing plans
    event_pricing = {
        "event_id": f"evt_pricing_{visitor_id}",
        "tenant_id": tenant_id,
        "type": "pricing_plan_viewed",
        "site_id": site_id,
        "session_id": session_id,
        "actor": {"id": visitor_id, "type": "visitor"},
        "data": {"plan_selected": "fleet_enterprise", "billing_interval": "annual"},
    }
    resp4 = api_client.post("/v1/events", json=event_pricing, headers=headers)
    assert resp4.status_code in (200, 202)

    # 5. Visitor opens demo modal and submits enterprise booking
    event_demo_modal = {
        "event_id": f"evt_demo_open_{visitor_id}",
        "tenant_id": tenant_id,
        "type": "demo_modal_opened",
        "site_id": site_id,
        "session_id": session_id,
        "actor": {"id": visitor_id, "type": "visitor"},
        "data": {"trigger_source": "hero_primary_cta"},
    }
    api_client.post("/v1/events", json=event_demo_modal, headers=headers)

    event_demo_submit = {
        "event_id": f"evt_demo_submit_{visitor_id}",
        "tenant_id": tenant_id,
        "type": "demo_request_submitted",
        "site_id": site_id,
        "session_id": session_id,
        "actor": {"id": visitor_id, "type": "visitor"},
        "data": {
            "email": "lead@enterprise-corp.com",
            "team_size": "20-100",
            "assigned_bandit_arm": "arm_variant_b",
        },
    }
    resp5 = api_client.post("/v1/events", json=event_demo_submit, headers=headers)
    assert resp5.status_code in (200, 202)


def test_funnel_evaluation_with_live_telemetry_events(api_client: TestClient):
    """
    Verifies that funnel evaluation endpoints correctly calculate step drop-offs and overall conversion.
    """
    admin_hdr = _admin_headers()

    # 1. Evaluate Enterprise Demo Funnel with matching event types
    sample_session_events = {
        "ses_sample_1": [
            {"type": "page_view", "occurred_at": datetime.now(UTC).isoformat()},
            {"type": "demo_modal_open", "occurred_at": datetime.now(UTC).isoformat()},
            {"type": "demo_request_submitted", "occurred_at": datetime.now(UTC).isoformat()},
        ],
        "ses_sample_2": [
            {"type": "page_view", "occurred_at": datetime.now(UTC).isoformat()},
        ],
    }

    resp_eval = api_client.post(
        "/v1/funnels/funnel_enterprise_demo/evaluate",
        json={"sessions_events": sample_session_events},
        headers=admin_hdr,
    )
    assert resp_eval.status_code == 200
    report = resp_eval.json()
    assert report["funnel_id"] == "funnel_enterprise_demo"
    assert report["name"] == "Enterprise Demo & Meeting Booking"
    assert len(report["steps"]) == 3
    assert report["steps"][0]["step_id"] == "step_landing"
    assert report["steps"][1]["step_id"] == "step_demo_view"
    assert report["steps"][2]["step_id"] == "step_demo_submitted"
    assert report["total_sessions_analyzed"] == 2
    assert report["completed_sessions"] == 1
    assert report["overall_conversion_rate_pct"] == 50.0

    # 2. Query all FRIDAY Universe funnels
    resp_fu = api_client.get("/v1/funnels/friday-universe?window_hours=48", headers=admin_hdr)
    assert resp_fu.status_code == 200
    funnels_data = resp_fu.json()["funnels"]
    assert len(funnels_data) == 4
    funnel_ids = {f["funnel_id"] for f in funnels_data}
    assert "funnel_enterprise_demo" in funnel_ids
    assert "funnel_saas_subscription" in funnel_ids
    assert "funnel_waitlist_signup" in funnel_ids
    assert "funnel_10_agent_mesh_journey" in funnel_ids


def test_seed_and_evaluate_thompson_sampling_bandits(api_client: TestClient):
    """
    Verifies that Thompson Sampling MAB experiments are properly seeded and initialized.
    """
    admin_hdr = _admin_headers()
    resp_seed = api_client.post("/v1/funnels/seed-bandit-experiments", headers=admin_hdr)
    assert resp_seed.status_code == 200
    seed_data = resp_seed.json()
    assert seed_data["status"] == "ACTIVE"
    experiment_ids = seed_data["seeded_experiment_ids"]
    assert len(experiment_ids) == 4
    assert "exp_enterprise_demo_cta" in experiment_ids
    assert "exp_saas_pricing_tier" in experiment_ids
    assert "exp_developer_waitlist_hook" in experiment_ids
    assert "exp_agent_mesh_onboarding" in experiment_ids
