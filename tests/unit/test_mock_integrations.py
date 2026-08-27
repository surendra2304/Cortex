import os
import sys
import pytest

sys.path.insert(0, os.path.abspath("packages/tool_runtime/src"))
sys.path.insert(0, os.path.abspath("packages/integrations/src"))

from nexus_tool_runtime import ToolBus
from nexus_integrations import (
    EmailToolExecutor, create_email_tool,
    CRMToolExecutor, create_crm_tool,
    WebhookToolExecutor, create_webhook_tool
)


@pytest.mark.asyncio
async def test_email_tool_mock_mode():
    tool = create_email_tool()
    executor = EmailToolExecutor(mock_mode=True)
    bus = ToolBus()
    bus.register_tool(tool, executor)

    params = {"to": "founder@startup.io", "subject": "Welcome", "body": "Welcome to NEXUS!"}
    result = await bus.execute("email_tool", params)

    assert result["status"] == "success"
    assert result["result"]["delivered"] is True
    assert result["result"]["mode"] == "mock"
    assert "msg_mock_" in result["result"]["message_id"]


@pytest.mark.asyncio
async def test_crm_tool_mock_mode():
    tool = create_crm_tool()
    executor = CRMToolExecutor(mock_mode=True)
    bus = ToolBus()
    bus.register_tool(tool, executor)

    params = {"lead_id": "lead_mock_123", "action": "upsert", "payload": {"company": "Acme Inc"}}
    result = await bus.execute("crm_tool", params)

    assert result["status"] == "success"
    assert result["result"]["crm_sync_status"] == "synced"
    assert result["result"]["mode"] == "mock"
    assert "crm_mock_rec_" in result["result"]["crm_record_id"]


@pytest.mark.asyncio
async def test_webhook_tool_mock_mode():
    tool = create_webhook_tool()
    executor = WebhookToolExecutor(mock_mode=True)
    bus = ToolBus()
    bus.register_tool(tool, executor)

    params = {"url": "https://api.external-partner.com/events", "payload": {"event": "visitor_identified"}}
    result = await bus.execute("webhook_tool", params)

    assert result["status"] == "success"
    assert result["result"]["delivered"] is True
    assert result["result"]["mode"] == "mock"
    assert result["result"]["status_code"] == 200
