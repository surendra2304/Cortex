"""
Unit tests for Redis Stream Worker DLQ quarantine and PEL recovery.
"""

from unittest.mock import AsyncMock, MagicMock
import pytest
from apps.worker.src.cortex_worker.main import (
    DLQ_STREAM,
    MAX_DELIVERY_ATTEMPTS,
    STREAM_NAME,
    CONSUMER_GROUP,
    deliver_message,
    route_to_dlq,
)


@pytest.mark.asyncio
async def test_route_to_dlq_publishes_event_to_dlq_stream():
    redis_mock = AsyncMock()
    message_id = "1729000000-0"
    payload = '{"bad": "data"}'
    reason = "Poison validation failure"

    await route_to_dlq(redis_mock, message_id, payload, reason)

    redis_mock.xadd.assert_awaited_once()
    call_args = redis_mock.xadd.call_args
    assert call_args[0][0] == DLQ_STREAM
    fields = call_args[0][1]
    assert fields["original_message_id"] == message_id
    assert fields["payload"] == payload
    assert fields["reason"] == reason
    assert "timestamp" in fields


@pytest.mark.asyncio
async def test_deliver_message_poison_quarantined_and_acknowledged():
    redis_mock = AsyncMock()
    orchestrator_mock = MagicMock()
    delivery_attempts = {}

    # Completely malformed JSON is poison
    poison_payload = "{invalid_json"

    acknowledged = await deliver_message(
        redis_client=redis_mock,
        message_id="msg_poison_1",
        payload_str=poison_payload,
        orchestrator=orchestrator_mock,
        delivery_attempts=delivery_attempts,
    )

    assert acknowledged is True
    # Verify DLQ quarantine
    redis_mock.xadd.assert_awaited_once()
    assert redis_mock.xadd.call_args[0][0] == DLQ_STREAM
    # Verify XACK
    redis_mock.xack.assert_awaited_once_with(STREAM_NAME, CONSUMER_GROUP, "msg_poison_1")
    assert "msg_poison_1" not in delivery_attempts


@pytest.mark.asyncio
async def test_deliver_message_max_attempts_quarantined_to_dlq():
    redis_mock = AsyncMock()
    orchestrator_mock = MagicMock()
    # Mock orchestrator raising error on processing
    orchestrator_mock.run_cognitive_loop = AsyncMock(side_effect=RuntimeError("Cognitive loop failure"))

    delivery_attempts = {"msg_retry_1": MAX_DELIVERY_ATTEMPTS - 1}
    # Valid JSON payload, but execution fails
    valid_payload = '{"event_id": "evt_1", "type": "page_view", "site_id": "site_test", "actor": {"id": "act_1", "type": "visitor"}}'

    acknowledged = await deliver_message(
        redis_client=redis_mock,
        message_id="msg_retry_1",
        payload_str=valid_payload,
        orchestrator=orchestrator_mock,
        delivery_attempts=delivery_attempts,
    )

    assert acknowledged is True
    # Verify quarantined to DLQ after exhausting attempts
    redis_mock.xadd.assert_awaited_once()
    assert redis_mock.xadd.call_args[0][0] == DLQ_STREAM
    # Verify XACK
    redis_mock.xack.assert_awaited_once_with(STREAM_NAME, CONSUMER_GROUP, "msg_retry_1")
    assert "msg_retry_1" not in delivery_attempts
