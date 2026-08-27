import os
import sys
import pytest

sys.path.insert(0, os.path.abspath("packages/tool_runtime/src"))
sys.path.insert(0, os.path.abspath("packages/integrations/src"))

from nexus_tool_runtime import ToolBus
from nexus_integrations import (
    EmailToolExecutor, create_email_tool,
    SMSToolExecutor, create_sms_tool,
    VoiceToolExecutor, create_voice_tool,
    CRMToolExecutor, create_crm_tool
)


@pytest.mark.asyncio
async def test_sendgrid_email_executor_mock():
    tool = create_email_tool()
    executor = EmailToolExecutor(mock_mode=True)
    bus = ToolBus()
    bus.register_tool(tool, executor)

    res = await bus.execute("email_tool", {
        "to": "vp@enterprise.com",
        "subject": "Enterprise Agreement",
        "body": "Your agreement is ready."
    })
    assert res["status"] == "success"
    assert res["result"]["delivered"] is True
    assert res["result"]["mode"] == "mock"


@pytest.mark.asyncio
async def test_twilio_sms_and_voice_executors_mock():
    bus = ToolBus()
    sms_tool = create_sms_tool()
    sms_exec = SMSToolExecutor(mock_mode=True)
    bus.register_tool(sms_tool, sms_exec)

    voice_tool = create_voice_tool()
    voice_exec = VoiceToolExecutor(mock_mode=True)
    bus.register_tool(voice_tool, voice_exec)

    # Test SMS
    sms_res = await bus.execute("sms_tool", {"to": "+15550199283", "body": "Security Alert: New Login"})
    assert sms_res["status"] == "success"
    assert sms_res["result"]["delivered"] is True
    assert "SM_mock_" in sms_res["result"]["message_sid"]

    # Test Voice
    voice_res = await bus.execute("voice_tool", {"to": "+15550199283", "twiml": "<Response><Say>Alert</Say></Response>"})
    assert voice_res["status"] == "success"
    assert voice_res["result"]["initiated"] is True
    assert "CA_mock_" in voice_res["result"]["call_sid"]


@pytest.mark.asyncio
async def test_hubspot_crm_executor_mock_actions():
    tool = create_crm_tool()
    executor = CRMToolExecutor(mock_mode=True)
    bus = ToolBus()
    bus.register_tool(tool, executor)

    # 1. Create contact
    c_res = await bus.execute("crm_tool", {
        "action": "create_contact",
        "lead_id": "lead_hs_1",
        "payload": {"email": "john@corp.com", "first_name": "John", "company": "Corp"}
    })
    assert c_res["status"] == "success"
    assert c_res["result"]["action"] == "create_contact"
    assert "hubspot_mock_" in c_res["result"]["crm_record_id"]

    # 2. Create deal
    d_res = await bus.execute("crm_tool", {
        "action": "create_deal",
        "lead_id": "lead_hs_1",
        "payload": {"deal_name": "Q3 Enterprise License", "amount": "50000"}
    })
    assert d_res["status"] == "success"
    assert d_res["result"]["action"] == "create_deal"
