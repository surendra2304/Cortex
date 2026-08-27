import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/tool_runtime/src"))
sys.path.insert(0, os.path.abspath("packages/integrations/src"))
sys.path.insert(0, os.path.abspath("packages/policy_engine/src"))

from nexus_tool_runtime import ToolBus, Execution, SideEffectLevel
from nexus_integrations import (
    EmailToolExecutor, create_email_tool,
    CRMToolExecutor, create_crm_tool,
    WebhookToolExecutor, create_webhook_tool
)
from nexus_policy_engine import PolicyEngine


@pytest.mark.asyncio
async def test_email_tool_execution():
    bus = ToolBus()
    tool = create_email_tool()
    executor = EmailToolExecutor()
    bus.register_tool(tool, executor)

    params = {
        "to": "lead@customer.com",
        "subject": "Exclusive Enterprise Offer",
        "body": "Hi there, we have a custom plan tailored for your team."
    }
    exec_item = Execution(
        request_id="exec_mail_1",
        tool_name="email_tool",
        actor={"type": "agent", "id": "agent_sales"},
        reason="Follow up on pricing view",
        params=params
    )

    result = await bus.execute("email_tool", params, exec_item)
    assert result["status"] == "success"
    assert result["result"]["delivered"] is True
    assert result["result"]["recipient"] == "lead@customer.com"
    assert exec_item.verification["status"] == "verified"


@pytest.mark.asyncio
async def test_crm_tool_execution():
    bus = ToolBus()
    tool = create_crm_tool()
    executor = CRMToolExecutor()
    bus.register_tool(tool, executor)

    params = {
        "lead_id": "lead_999",
        "action": "upsert",
        "payload": {"status": "qualified", "score": 92.5}
    }
    exec_item = Execution(
        request_id="exec_crm_1",
        tool_name="crm_tool",
        actor={"type": "agent", "id": "agent_sales"},
        reason="Sync qualified score to HubSpot",
        params=params
    )

    result = await bus.execute("crm_tool", params, exec_item)
    assert result["status"] == "success"
    assert result["result"]["crm_sync_status"] == "synced"
    assert result["result"]["lead_id"] == "lead_999"


@pytest.mark.asyncio
async def test_webhook_tool_execution():
    bus = ToolBus()
    tool = create_webhook_tool()
    executor = WebhookToolExecutor()
    bus.register_tool(tool, executor)

    params = {
        "url": "https://hooks.slack.com/services/T00/B00/X00",
        "payload": {"text": "New VIP Lead identified!"}
    }
    result = await bus.execute("webhook_tool", params)
    assert result["status"] == "success"
    assert result["result"]["delivered"] is True
    assert result["result"]["target_url"] == params["url"]


@pytest.mark.asyncio
async def test_tool_idempotency_redis():
    mock_redis = AsyncMock()
    # 1st call returns True (acquired), 2nd returns False (already set)
    mock_redis.set.side_effect = [True, False]

    bus = ToolBus(redis_client=mock_redis)
    tool = create_email_tool()
    bus.register_tool(tool, EmailToolExecutor())

    params = {
        "to": "test@test.com",
        "subject": "Hello",
        "body": "World",
        "idempotency_key": "idemp_unique_key_123"
    }

    # First execution should succeed
    res1 = await bus.execute("email_tool", params)
    assert res1["status"] == "success"

    # Second duplicate execution should be skipped
    res2 = await bus.execute("email_tool", params)
    assert res2["status"] == "skipped"
    assert res2["reason"] == "duplicate_idempotent_request"
