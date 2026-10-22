"""At-least-once delivery semantics for the stream worker (upgrade 2026-10-07).

Locks the contract that the worker only acknowledges a stream message when it was
processed successfully or proven poison (unparseable — no retry can fix it), and
that messages stranded in the pending entries list are reclaimed and reprocessed
instead of being lost. Before this upgrade the worker acknowledged every message
regardless of processing outcome, silently dropping failed events.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/event_schema/src"))
sys.path.insert(0, os.path.abspath("packages/agents/src"))
sys.path.insert(0, os.path.abspath("packages/ai_universe_adapter/src"))
sys.path.insert(0, os.path.abspath("packages/tool_runtime/src"))
sys.path.insert(0, os.path.abspath("packages/integrations/src"))
sys.path.insert(0, os.path.abspath("packages/policy_engine/src"))
sys.path.insert(0, os.path.abspath("apps/worker/src"))
sys.path.insert(0, os.path.abspath("apps/api/src"))

import cortex_worker.main as worker_main
from cortex_worker.main import deliver_message, ensure_stream_group, process_event_with_status, run_pel_recovery


class _FakeSession:
    """Stand-in for the DB session so unit tests never touch a real database."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


@pytest.fixture(autouse=True)
def _no_real_db(monkeypatch):
    monkeypatch.setattr(worker_main, "AsyncSessionLocal", lambda: _FakeSession())
    # run the recovery loop without the production 30s cadence
    monkeypatch.setattr(worker_main, "PEL_RECOVERY_INTERVAL_SECONDS", 0)


def _valid_payload(event_id: str = "evt_delivery_1") -> str:
    return json.dumps(
        {
            "event_id": event_id,
            "tenant_id": "tenant_test",
            "site_id": "site_test",
            "type": "page_view",
            "occurred_at": "2026-10-07T12:00:00Z",
            "actor": {"type": "user", "id": "usr_test"},
            "source": "web",
            "data": {},
        }
    )


def _ok_orchestrator():
    orchestrator = AsyncMock()
    orchestrator.run_cognitive_loop.return_value = {
        "loop_id": "loop_test",
        "agent_id": "agent_growth",
        "decision": "NO_ACTION",
        "executed_actions": 0,
        "trace": [],
        "status": "success",
    }
    return orchestrator


def _failing_orchestrator(exc: Exception = RuntimeError("transient")):
    orchestrator = AsyncMock()
    orchestrator.run_cognitive_loop.side_effect = exc
    return orchestrator


# ── process_event_with_status ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_malformed_json_is_poison():
    status, result = await process_event_with_status("1-1", "NOT JSON {{{", _ok_orchestrator())
    assert status == "poison"
    assert result is None


@pytest.mark.asyncio
async def test_schema_invalid_payload_is_poison():
    status, result = await process_event_with_status(
        "1-2", json.dumps({"event_id": "x", "bogus": 1}), _ok_orchestrator()
    )
    assert status == "poison"
    assert result is None


@pytest.mark.asyncio
async def test_successful_loop_is_ok():
    status, result = await process_event_with_status("1-3", _valid_payload(), _ok_orchestrator())
    assert status == "ok"
    assert result["loop_id"] == "loop_test"


@pytest.mark.asyncio
async def test_loop_exception_is_error_not_poison():
    status, result = await process_event_with_status("1-4", _valid_payload(), _failing_orchestrator())
    assert status == "error"
    assert result is None


# ── deliver_message acknowledgement policy ────────────────────────────────────


@pytest.mark.asyncio
async def test_deliver_acks_on_success():
    redis_client = AsyncMock()
    attempts: dict[str, int] = {}
    acked = await deliver_message(redis_client, "1-1", _valid_payload(), _ok_orchestrator(), attempts)
    assert acked is True
    redis_client.xack.assert_awaited_once()
    assert attempts == {}


@pytest.mark.asyncio
async def test_deliver_acks_poison():
    redis_client = AsyncMock()
    attempts: dict[str, int] = {}
    acked = await deliver_message(redis_client, "1-2", "NOT JSON", _ok_orchestrator(), attempts)
    assert acked is True
    redis_client.xack.assert_awaited_once()


@pytest.mark.asyncio
async def test_deliver_leaves_failed_message_pending():
    redis_client = AsyncMock()
    attempts: dict[str, int] = {}
    acked = await deliver_message(redis_client, "1-3", _valid_payload(), _failing_orchestrator(), attempts)
    assert acked is False
    redis_client.xack.assert_not_awaited()
    assert attempts == {"1-3": 1}


@pytest.mark.asyncio
async def test_deliver_acks_after_max_attempts(monkeypatch):
    monkeypatch.setattr(worker_main, "MAX_DELIVERY_ATTEMPTS", 3)
    redis_client = AsyncMock()
    attempts: dict[str, int] = {"1-4": 2}  # already failed twice
    acked = await deliver_message(redis_client, "1-4", _valid_payload(), _failing_orchestrator(), attempts)
    assert acked is True
    redis_client.xack.assert_awaited_once()
    assert attempts == {}


# ── PEL recovery ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pel_recovery_reclaims_and_reprocesses_stranded_message():
    redis_client = AsyncMock()
    stranded_id = "1791387638625-2"
    entry = {
        "message_id": stranded_id,
        "consumer": "dead-consumer",
        "time_since_delivered": 61000,
        "times_delivered": 1,
    }
    redis_client.xpending_range.side_effect = [[entry], asyncio.CancelledError()]
    redis_client.xclaim.return_value = [(stranded_id, {"payload": _valid_payload("evt_stranded")})]

    attempts: dict[str, int] = {}
    await run_pel_recovery(redis_client, _ok_orchestrator(), attempts)

    redis_client.xclaim.assert_awaited_once()
    assert redis_client.xclaim.await_args.kwargs["message_ids"] == [stranded_id]
    redis_client.xack.assert_awaited_once_with(worker_main.STREAM_NAME, worker_main.CONSUMER_GROUP, stranded_id)


@pytest.mark.asyncio
async def test_pel_recovery_acks_exhausted_messages_without_reprocessing():
    redis_client = AsyncMock()
    stranded_id = "1791387638625-9"
    entry = {"message_id": stranded_id, "consumer": "dead", "time_since_delivered": 61000, "times_delivered": 5}
    redis_client.xpending_range.side_effect = [[entry], asyncio.CancelledError()]
    attempts: dict[str, int] = {stranded_id: worker_main.MAX_DELIVERY_ATTEMPTS}
    await run_pel_recovery(redis_client, _ok_orchestrator(), attempts)
    redis_client.xclaim.assert_not_awaited()
    redis_client.xack.assert_awaited_once_with(worker_main.STREAM_NAME, worker_main.CONSUMER_GROUP, stranded_id)


# ── consumer-group self-healing ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ensure_stream_group_ignores_other_errors():
    redis_client = AsyncMock()
    assert await ensure_stream_group(redis_client, ConnectionError("refused")) is False
    redis_client.xgroup_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_stream_group_recreates_on_nogroup():
    redis_client = AsyncMock()
    assert await ensure_stream_group(redis_client, Exception("NOGROUP No such consumer group")) is True
    redis_client.xgroup_create.assert_awaited_once()
