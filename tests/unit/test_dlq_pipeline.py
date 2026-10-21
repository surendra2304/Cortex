"""Unit tests for the Dead Letter Queue and quarantine triage engine (cortex_upgrade.dlq)."""

from __future__ import annotations

import pytest
from cortex_upgrade.dlq import DeadLetterQueue
from cortex_upgrade.models import FailureKind


@pytest.fixture
def dlq():
    return DeadLetterQueue(max_messages_per_tenant=50)


@pytest.mark.asyncio
async def test_dlq_quarantine_message(dlq):
    msg = await dlq.quarantine(
        stream_id="1730000000-0",
        tenant_id="tenant_alpha",
        payload={"event": "bad_json_data", "attempt": 5},
        failure_kind=FailureKind.INVALID,
        error_details="Schema validation failed: missing visitor_id",
        delivery_attempts=5,
    )

    assert msg.message_id.startswith("dlq_")
    assert msg.tenant_id == "tenant_alpha"
    assert msg.failure_kind == "invalid"
    assert msg.reprocessed is False

    retrieved = await dlq.get_message(msg.message_id, "tenant_alpha")
    assert retrieved is not None
    assert retrieved.stream_id == "1730000000-0"


@pytest.mark.asyncio
async def test_dlq_strict_tenant_isolation(dlq):
    msg = await dlq.quarantine(
        stream_id="1730000001-0",
        tenant_id="tenant_secret",
        payload={"secret": "confidential_deal"},
        failure_kind=FailureKind.PERSISTENCE,
        error_details="Database connection timeout",
    )

    # Foreign tenant must NOT find the message
    assert await dlq.get_message(msg.message_id, "tenant_attacker") is None

    # Foreign tenant listing must NOT include the message
    foreign_list = await dlq.list_messages("tenant_attacker")
    assert len(foreign_list) == 0

    # Own tenant listing must contain it
    own_list = await dlq.list_messages("tenant_secret")
    assert len(own_list) == 1
    assert own_list[0].message_id == msg.message_id


@pytest.mark.asyncio
async def test_dlq_safe_reprocess_success(dlq):
    msg = await dlq.quarantine(
        stream_id="1730000002-0",
        tenant_id="tenant_beta",
        payload={"action": "retryable_action"},
        failure_kind=FailureKind.TRANSIENT,
        error_details="Transient upstream 503",
    )

    async def successful_processor(p: dict) -> bool:
        assert p.get("action") == "retryable_action"
        return True

    ok, detail = await dlq.reprocess(msg.message_id, "tenant_beta", successful_processor)
    assert ok is True
    assert "reprocessed" in detail.lower()

    updated = await dlq.get_message(msg.message_id, "tenant_beta")
    assert updated.reprocessed is True
    assert updated.reprocessed_at is not None

    # By default, list_messages excludes reprocessed messages
    pending = await dlq.list_messages("tenant_beta", include_reprocessed=False)
    assert len(pending) == 0

    all_msgs = await dlq.list_messages("tenant_beta", include_reprocessed=True)
    assert len(all_msgs) == 1


@pytest.mark.asyncio
async def test_dlq_reprocess_failure_logs_error(dlq):
    msg = await dlq.quarantine(
        stream_id="1730000003-0",
        tenant_id="tenant_gamma",
        payload={"action": "failing_action"},
        failure_kind=FailureKind.TIMEOUT,
        error_details="Timeout on external webhook",
    )

    async def failing_processor(p: dict) -> bool:
        raise RuntimeError("External dependency still down")

    ok, detail = await dlq.reprocess(msg.message_id, "tenant_gamma", failing_processor)
    assert ok is False
    assert "still down" in detail

    updated = await dlq.get_message(msg.message_id, "tenant_gamma")
    assert updated.reprocessed is False
    assert "RuntimeError" in (updated.reprocess_error or "")


@pytest.mark.asyncio
async def test_dlq_purge_message(dlq):
    msg = await dlq.quarantine(
        stream_id="1730000004-0",
        tenant_id="tenant_delta",
        payload={"trash": True},
        failure_kind=FailureKind.UNKNOWN,
        error_details="Corrupt payload",
    )

    # Cannot purge across tenant
    assert await dlq.purge(msg.message_id, "tenant_other") is False
    assert await dlq.get_message(msg.message_id, "tenant_delta") is not None

    # Purge with correct tenant
    assert await dlq.purge(msg.message_id, "tenant_delta") is True
    assert await dlq.get_message(msg.message_id, "tenant_delta") is None


@pytest.mark.asyncio
async def test_dlq_metrics(dlq):
    await dlq.quarantine("s1", "t1", {"x": 1}, FailureKind.TIMEOUT, "err")
    msg2 = await dlq.quarantine("s2", "t1", {"x": 2}, FailureKind.INVALID, "err")
    await dlq.quarantine("s3", "t2", {"x": 3}, FailureKind.PERSISTENCE, "err")

    # Reprocess one
    await dlq.reprocess(msg2.message_id, "t1", lambda p: _always_true())

    t1_metrics = await dlq.metrics("t1")
    assert t1_metrics["total_quarantined"] == 2
    assert t1_metrics["pending_triage"] == 1
    assert t1_metrics["reprocessed"] == 1

    global_metrics = await dlq.metrics()
    assert global_metrics["total_quarantined"] == 3
    assert global_metrics["pending_triage"] == 2
    assert global_metrics["tenants_with_poison_events"] == 2


async def _always_true() -> bool:
    return True
