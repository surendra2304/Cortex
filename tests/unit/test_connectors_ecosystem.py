import pytest
import os
import sys
from unittest.mock import AsyncMock, MagicMock
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

from cortex_integrations import (
    create_calendar_tool,
    CalendarToolExecutor,
    get_connector_registry,
    CONNECTOR_HEALTH
)
from cortex_api.main import app


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
    book_res = await executor.execute({
        "action": "book_meeting",
        "payload": {"email": "alex@enterprise.com", "scheduled_time": "2026-08-29T10:00:00Z"}
    })
    assert book_res["status"] == "booked"
    assert "cal_book_" in book_res["booking_id"]


def test_connector_registry_endpoint():
    client = TestClient(app)
    res = client.get("/connectors")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 6
    names = [c["name"] for c in data]
    assert any("SendGrid" in n for n in names)
    assert any("Twilio" in n for n in names)
    assert any("HubSpot" in n for n in names)
    assert any("Calendly" in n for n in names)
    assert any("Stripe" in n for n in names)
    assert any("Zendesk" in n for n in names)
