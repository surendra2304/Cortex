import os
import sys

import pytest
from fastapi.testclient import TestClient

for p in [
    "packages/core/src",
    "packages/event_schema/src",
    "packages/agents/src",
    "packages/ai_universe_adapter/src",
    "packages/tool_runtime/src",
    "packages/integrations/src",
    "packages/policy_engine/src",
    "packages/workflow_engine/src",
    "packages/identity/src",
    "packages/analytics/src",
    "packages/intelligence/src",
    "packages/memory/src",
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(p))

from cortex_api.main import app
from cortex_integrations import CalendarToolExecutor, create_calendar_tool

from tests.conftest import auth_headers


def test_calendar_tool_creation():
    tool = create_calendar_tool()
    assert tool.name == "calendar_tool"
    assert tool.auth_scope == "integrations:calendar"
    assert tool.rate_limit == 30


@pytest.mark.asyncio
async def test_calendar_tool_executor_mock_actions():
    executor = CalendarToolExecutor(mock_mode=True)

    # 1. Availability check
    avail_res = await executor.execute({"action": "check_availability"})
    assert avail_res["status"] == "available"
    assert len(avail_res["available_slots"]) > 0

    # 2. Book meeting
    book_res = await executor.execute(
        {
            "action": "book_meeting",
            "payload": {"email": "alex@enterprise.com", "scheduled_time": "2026-08-29T10:00:00Z"},
        }
    )
    assert book_res["status"] == "booked"
    assert "cal_book_" in book_res["booking_id"]


def test_connector_registry_endpoint():
    client = TestClient(app)
    # Audit C4: connector inventory is operator-only.
    assert client.get("/connectors").status_code == 401
    res = client.get("/connectors", headers=auth_headers())
    assert res.status_code == 200
    data = res.json()
    # The registry is LIVE: real health checks, honest statuses. With no probes
    # configured every connector is UNVERIFIED — never a fabricated HEALTHY.
    assert len(data) == 7
    by_id = {c["id"]: c for c in data}
    assert set(by_id) == {"email", "crm", "sms", "payments", "futuris", "intelx", "sentinel"}
    assert all(c["status"] == "UNVERIFIED" for c in data)
    assert all(c["failure_count"] == 1 for c in data)  # not healthy -> at least one failure
    names = [c["name"] for c in data]
    assert any("SendGrid" in n for n in names)
    assert any("Twilio" in n for n in names)
    assert any("HubSpot" in n for n in names)
    assert any("Stripe" in n for n in names)
    # A simulated outage must surface in the registry (no static table).
    from cortex_integrations import global_connector_manager

    global_connector_manager.set_mock_outage("payments", True)
    try:
        res = client.get("/connectors", headers=auth_headers())
        payments = next(c for c in res.json() if c["id"] == "payments")
        assert payments["status"] == "UNHEALTHY"
    finally:
        global_connector_manager.set_mock_outage("payments", False)
