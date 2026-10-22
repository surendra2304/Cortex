"""Approval decisions must actually move state — and only once.

Live test: ``POST /v1/friday/approvals/{id}/decide`` with ``approved: false`` returned
HTTP 400 ``'GovernedOperationsEngine' object has no attribute 'reject'``. The rejection
branch had never worked, and the raw AttributeError was echoed to the caller. These tests
drive the real endpoint end to end (recommend -> decide -> re-decide) so a regression in
either the engine or the router fails loudly.
"""

from __future__ import annotations

import asyncio

import pytest
from cortex_api.main import app
from cortex_core.governed_operations import (
    GovernedOperationsEngine,
    ImpactCategory,
    Recommendation,
    RecommendationAlreadyDecidedError,
)
from cortex_core.web_property import WebProperty
from cortex_tool_runtime import SideEffectLevel
from fastapi.testclient import TestClient

from tests.conftest import friday_headers


def _engine_with_recommendation(requires_approval: bool = True) -> tuple[GovernedOperationsEngine, str]:
    engine = GovernedOperationsEngine()
    engine.registry.register(
        WebProperty(
            property_id="site_test",
            name="Test site",
            allowed_domains=["example.com"],
            allowed_operations=["banner_injection", "config_update", "experiment_mutate"],
            target_environment="staging",
            approval_policy={},
            rollback_policy={},
            state_snapshot={},
        )
    )
    recommendation = Recommendation(
        recommendation_id="rec_decision_test",
        observation_id="obs_1",
        property_id="site_test",
        proposed_action="banner_injection",
        params={"variant": "annual_discount_banner"},
        category=ImpactCategory.CONTENT_PUBLISHING,
        impact_level=SideEffectLevel.HIGH_IMPACT,
        requires_approval=requires_approval,
        rationale="Lift conversions",
        confidence=0.8,
        expected_outcomes={"lift": 0.05},
    )
    engine.recommendations[recommendation.recommendation_id] = recommendation
    return engine, recommendation.recommendation_id


def test_engine_reject_is_terminal_and_records_the_decision():
    """The engine must expose a real rejection path with a terminal state."""
    engine, rec_id = _engine_with_recommendation()

    rejection = engine.reject(rec_id, approver_id="usr_supervisor", reason="Risk too high")

    assert rejection.recommendation_id == rec_id
    assert rejection.approver_id == "usr_supervisor"
    assert rejection.reason == "Risk too high"
    assert engine.recommendations[rec_id].status == "REJECTED"
    # A rejection is not an approval: nothing may become executable.
    assert engine.approvals == {}
    with pytest.raises(RecommendationAlreadyDecidedError):
        engine.authorize(rec_id, approver_id="usr_supervisor")
    with pytest.raises(RecommendationAlreadyDecidedError):
        engine.reject(rec_id, approver_id="usr_supervisor", reason="again")


def test_engine_reject_unknown_recommendation_raises_keyerror():
    engine = GovernedOperationsEngine()
    with pytest.raises(KeyError):
        engine.reject("rec_missing", approver_id="usr_supervisor")


def test_decide_endpoint_rejects_then_conflicts_on_re_decide(monkeypatch):
    """HTTP contract: approved=false -> approved:false, then 409 on any second decision."""
    from cortex_api import friday_router

    engine, rec_id = _engine_with_recommendation()
    monkeypatch.setattr(friday_router, "global_governed_engine", engine)

    client = TestClient(app)
    headers = friday_headers(monkeypatch)

    rejected = client.post(
        f"/v1/friday/approvals/{rec_id}/decide",
        json={"approved": False, "approver_id": "usr_supervisor", "reason": "Not worth the risk"},
        headers=headers,
    )
    assert rejected.status_code == 200, rejected.text
    body = rejected.json()
    assert body["approved"] is False
    assert body["recommendation_id"] == rec_id
    assert body["approver_id"] == "usr_supervisor"
    assert body["reason"] == "Not worth the risk"
    assert "AttributeError" not in rejected.text

    for second in (
        {"approved": True, "approver_id": "usr_supervisor"},
        {"approved": False, "approver_id": "usr_other"},
    ):
        again = client.post(f"/v1/friday/approvals/{rec_id}/decide", json=second, headers=headers)
        assert again.status_code == 409, again.text
        assert "already decided" in again.json()["detail"]


def test_decide_endpoint_approves_once_and_then_conflicts(monkeypatch):
    from cortex_api import friday_router

    engine, rec_id = _engine_with_recommendation()
    monkeypatch.setattr(friday_router, "global_governed_engine", engine)

    client = TestClient(app)
    headers = friday_headers(monkeypatch)

    approved = client.post(
        f"/v1/friday/approvals/{rec_id}/decide",
        json={"approved": True, "approver_id": "usr_supervisor", "reason": "Ship it"},
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approved"] is True
    assert engine.recommendations[rec_id].status == "APPROVED"

    again = client.post(
        f"/v1/friday/approvals/{rec_id}/decide",
        json={"approved": True, "approver_id": "usr_supervisor"},
        headers=headers,
    )
    assert again.status_code == 409


def test_decide_endpoint_requires_the_friday_service_token(monkeypatch):
    """No service token, no decision — and the anonymous request must not touch state."""
    from cortex_api import friday_router

    engine, rec_id = _engine_with_recommendation()
    monkeypatch.setattr(friday_router, "global_governed_engine", engine)

    client = TestClient(app)
    response = client.post(f"/v1/friday/approvals/{rec_id}/decide", json={"approved": True})
    assert response.status_code == 401
    assert engine.recommendations[rec_id].status == "PENDING_APPROVAL"


def test_in_process_approval_queue_is_terminal():
    """Replay is idempotent; a conflicting decision on a decided approval is refused."""
    from uuid import uuid4

    from cortex_upgrade.approval import ApprovalQueue
    from cortex_upgrade.models import SideEffect, ToolCall

    async def _run() -> None:
        queue = ApprovalQueue()
        call = ToolCall(uuid4(), "crm", {}, SideEffect.HIGH_IMPACT)
        request = await queue.request("tenant_test", "usr_principal", call)

        decided = await queue.decide(request.approval_id, "usr_admin", True, "approved")
        assert decided.approved is True

        replay = await queue.decide(request.approval_id, "usr_admin", True, "approved")
        assert replay.approved is True

        with pytest.raises(ValueError):
            await queue.decide(request.approval_id, "usr_admin", False, "changed my mind")

    asyncio.run(_run())
