"""
Unit tests for Stripe PaymentsTool and Zendesk TicketingTool (mock mode),
and for the Stripe webhook receiver endpoint.
"""
import sys
import os
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

# ── Package paths ─────────────────────────────────────────────────────────────
for _p in [
    "packages/tool_runtime/src",
    "packages/integrations/src",
    "packages/core/src",
    "packages/event_schema/src",
    "packages/agents/src",
    "packages/ai_universe_adapter/src",
    "packages/policy_engine/src",
    "packages/workflow_engine/src",
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(_p))

from nexus_integrations import (
    PaymentsToolExecutor,
    create_payments_tool,
    TicketingToolExecutor,
    create_ticketing_tool,
)
from nexus_tool_runtime import ToolBus, ToolCapability, SideEffectLevel


# =============================================================================
# 1. Stripe PaymentsTool — Mock Mode
# =============================================================================

@pytest.mark.asyncio
async def test_payments_tool_create_payment_link_mock():
    """PaymentsTool should return a mock payment link when MOCK_MODE=true."""
    executor = PaymentsToolExecutor(mock_mode=True)
    bus = ToolBus()
    bus.register_tool(create_payments_tool(), executor)

    result = await bus.execute(
        "payments_tool",
        {
            "action": "create_payment_link",
            "payload": {"amount": 4900, "currency": "usd"},
        },
    )

    assert result["status"] == "success"
    r = result["result"]
    assert r["status"] == "created"
    assert "stripe_mock_" in r["payment_link_id"]
    assert "buy.stripe.com/mock" in r["url"]
    assert r["mode"] == "mock"


@pytest.mark.asyncio
async def test_payments_tool_retrieve_payment_intent_mock():
    """PaymentsTool should return a mock payment intent status."""
    executor = PaymentsToolExecutor(mock_mode=True)
    bus = ToolBus()
    bus.register_tool(create_payments_tool(), executor)

    result = await bus.execute(
        "payments_tool",
        {
            "action": "retrieve_payment_intent",
            "payload": {"payment_intent_id": "pi_mock_abc123", "amount": 9900},
        },
    )

    assert result["status"] == "success"
    r = result["result"]
    assert r["status"] == "succeeded"
    assert r["payment_intent_id"] == "pi_mock_abc123"
    assert r["mode"] == "mock"


@pytest.mark.asyncio
async def test_payments_tool_create_customer_mock():
    """PaymentsTool should return a mock Stripe customer record."""
    executor = PaymentsToolExecutor(mock_mode=True)
    bus = ToolBus()
    bus.register_tool(create_payments_tool(), executor)

    result = await bus.execute(
        "payments_tool",
        {
            "action": "create_customer",
            "payload": {"email": "ceo@enterprise.com", "name": "Enterprise CEO"},
        },
    )

    assert result["status"] == "success"
    r = result["result"]
    assert r["status"] == "created"
    assert "stripe_mock_" in r["customer_id"]
    assert r["email"] == "ceo@enterprise.com"
    assert r["mode"] == "mock"


@pytest.mark.asyncio
async def test_payments_tool_invalid_action_raises():
    """PaymentsTool should raise ValueError for unsupported actions."""
    executor = PaymentsToolExecutor(mock_mode=True)

    with pytest.raises(ValueError, match="Unsupported PaymentsTool action"):
        await executor.execute({"action": "refund_payment", "payload": {}})


def test_payments_tool_contract():
    """PaymentsTool Tool definition should declare HIGH_IMPACT and PAYMENT_INITIATE."""
    tool = create_payments_tool()
    assert tool.name == "payments_tool"
    assert tool.side_effect_level == SideEffectLevel.HIGH_IMPACT
    assert ToolCapability.PAYMENT_INITIATE in tool.capabilities


# =============================================================================
# 2. Zendesk TicketingTool — Mock Mode
# =============================================================================

@pytest.mark.asyncio
async def test_ticketing_tool_create_ticket_mock():
    """TicketingTool should return a mock ticket when MOCK_MODE=true."""
    executor = TicketingToolExecutor(mock_mode=True)
    bus = ToolBus()
    bus.register_tool(create_ticketing_tool(), executor)

    result = await bus.execute(
        "ticketing_tool",
        {
            "action": "create_ticket",
            "payload": {
                "subject": "Cannot access dashboard",
                "description": "User reports 403 errors after login.",
                "priority": "high",
                "requester_email": "user@corp.com",
            },
        },
    )

    assert result["status"] == "success"
    r = result["result"]
    assert r["status"] == "created"
    assert isinstance(r["ticket_id"], int)
    assert "zendesk.com" in r["ticket_url"]
    assert r["priority"] == "high"
    assert r["mode"] == "mock"


@pytest.mark.asyncio
async def test_ticketing_tool_update_ticket_mock():
    """TicketingTool should return a mock update confirmation."""
    executor = TicketingToolExecutor(mock_mode=True)
    bus = ToolBus()
    bus.register_tool(create_ticketing_tool(), executor)

    result = await bus.execute(
        "ticketing_tool",
        {
            "action": "update_ticket",
            "payload": {
                "ticket_id": 12345,
                "status": "solved",
                "comment": "Issue resolved by engineering team.",
            },
        },
    )

    assert result["status"] == "success"
    r = result["result"]
    assert r["status"] == "updated"
    assert r["ticket_id"] == 12345
    assert r["mode"] == "mock"


@pytest.mark.asyncio
async def test_ticketing_tool_invalid_action_raises():
    """TicketingTool should raise ValueError for unsupported actions."""
    executor = TicketingToolExecutor(mock_mode=True)

    with pytest.raises(ValueError, match="Unsupported TicketingTool action"):
        await executor.execute({"action": "delete_ticket", "payload": {}})


def test_ticketing_tool_contract():
    """TicketingTool definition should declare SENSITIVE and TICKETING_CREATE."""
    tool = create_ticketing_tool()
    assert tool.name == "ticketing_tool"
    assert tool.side_effect_level == SideEffectLevel.SENSITIVE
    assert ToolCapability.TICKETING_CREATE in tool.capabilities


# =============================================================================
# 3. Stripe Webhook Endpoint
# =============================================================================

@pytest.mark.asyncio
async def test_stripe_webhook_checkout_completed_mock_mode():
    """
    POST /v1/webhooks/stripe should accept a checkout.session.completed event
    in mock mode (no STRIPE_WEBHOOK_SECRET set) and push it to the Redis stream.
    """
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from unittest.mock import AsyncMock

    # Build a minimal app with only the stripe webhook router
    sys.path.insert(0, os.path.abspath("apps/api/src"))
    os.environ["MOCK_MODE"] = "true"
    os.environ.pop("STRIPE_WEBHOOK_SECRET", None)

    from nexus_api.stripe_webhook_router import router

    mini_app = FastAPI()

    mock_redis = AsyncMock()
    mock_redis.xadd = AsyncMock(return_value=b"stream_id")

    async def _get_redis_override():
        return mock_redis

    from nexus_api.config import get_redis_client
    mini_app.dependency_overrides[get_redis_client] = _get_redis_override
    mini_app.include_router(router)

    stripe_payload = json.dumps({
        "id": "evt_test_checkout_001",
        "type": "checkout.session.completed",
        "created": 1700000000,
        "data": {
            "object": {
                "id": "cs_test_001",
                "customer": "cus_test_12345",
                "customer_details": {"email": "buyer@enterprise.com"},
                "amount_total": 49900,
                "currency": "usd",
                "subscription": None,
            }
        },
    }).encode()

    client = TestClient(mini_app, raise_server_exceptions=True)
    response = client.post(
        "/v1/webhooks/stripe",
        content=stripe_payload,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert body["nexus_event_type"] == "checkout.completed"
    assert "stripe_evt_test_checkout_001" in body["nexus_event_id"] or "stripe_" in body["nexus_event_id"]

    # Verify Redis xadd was called with the mapped NEXUS event
    mock_redis.xadd.assert_called_once()
    call_args = mock_redis.xadd.call_args
    stream_name = call_args[0][0]
    stream_fields = call_args[0][1]
    nexus_event = json.loads(stream_fields["payload"])

    assert nexus_event["type"] == "checkout.completed"
    assert nexus_event["data"]["customer_id"] == "cus_test_12345"
    assert nexus_event["data"]["customer_email"] == "buyer@enterprise.com"
    assert nexus_event["source"] == "stripe_webhook"


@pytest.mark.asyncio
async def test_stripe_webhook_ignored_event_type():
    """
    POST /v1/webhooks/stripe with an unsupported event type should return
    status='acknowledged', action='ignored' without touching Redis.
    """
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from unittest.mock import AsyncMock

    os.environ["MOCK_MODE"] = "true"
    os.environ.pop("STRIPE_WEBHOOK_SECRET", None)

    # Re-import to pick up fresh env
    import importlib
    import nexus_api.stripe_webhook_router as _mod
    importlib.reload(_mod)

    mini_app = FastAPI()
    mock_redis = AsyncMock()

    async def _get_redis_override():
        return mock_redis

    from nexus_api.config import get_redis_client
    mini_app.dependency_overrides[get_redis_client] = _get_redis_override
    mini_app.include_router(_mod.router)

    stripe_payload = json.dumps({
        "id": "evt_test_unknown",
        "type": "payment_method.attached",
        "created": 1700000000,
        "data": {"object": {}},
    }).encode()

    client = TestClient(mini_app)
    response = client.post(
        "/v1/webhooks/stripe",
        content=stripe_payload,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "acknowledged"
    assert body["action"] == "ignored"

    # Redis stream must NOT have been written
    mock_redis.xadd.assert_not_called()
