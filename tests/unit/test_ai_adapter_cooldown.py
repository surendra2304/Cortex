"""AI Universe fail-fast cooldown (pressure hardening, 2026-10-07).

A dead or hanging AI Universe peer must not wedge the cognitive loop: after a few
consecutive server-side failures, live calls are skipped for a cooldown window
and the honest deterministic fallback answers immediately. 4xx client errors are
request problems, not outages, and do not trip the cooldown.
"""

from __future__ import annotations

import os
import sys
import time

import httpx
import pytest

sys.path.insert(0, os.path.abspath("packages/ai_universe_adapter/src"))
sys.path.insert(0, os.path.abspath("packages/event_schema/src"))

from cortex_ai_universe_adapter import AIUniverseClient, IntelligenceRequest


def _request() -> IntelligenceRequest:
    return IntelligenceRequest(
        request_id="req_cooldown_1",
        task_type="intervention_planning",
        goal="cooldown test",
        context={},
        constraints=[],
    )


def _client(**kwargs) -> AIUniverseClient:
    kwargs.setdefault("endpoint", "http://127.0.0.1:1")  # nothing listens here
    kwargs.setdefault("max_retries", 1)
    kwargs.setdefault("cooldown_after_failures", 3)
    kwargs.setdefault("cooldown_seconds", 30.0)
    return AIUniverseClient(**kwargs)


@pytest.mark.asyncio
async def test_failures_trip_cooldown_and_skip_live_calls():
    client = _client()
    for _ in range(3):
        resp = await client.evaluate(_request())
        assert resp.fallback_applied is True
    assert client._consecutive_failures == 3

    # In cooldown: the next call must return instantly without a network attempt.
    started = time.monotonic()
    resp = await client.evaluate(_request())
    elapsed = time.monotonic() - started
    assert resp.fallback_applied is True
    assert "cooldown" in resp.summary
    assert elapsed < 0.5, f"cooldown call took {elapsed:.2f}s — live call was attempted"


@pytest.mark.asyncio
async def test_success_resets_the_cooldown():
    client = _client()
    client._consecutive_failures = 2
    client._cooldown_until = time.monotonic() + 30

    def _ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "request_id": "req_cooldown_1",
                "decision": "ESCALATE",
                "confidence": 0.9,
                "summary": "ok",
                "key_evidence": [],
                "unresolved_disagreements": [],
                "recommended_actions": [],
                "generated_at": "2026-10-07T00:00:00+00:00",
            },
        )

    transport = httpx.MockTransport(_ok)
    real_client = httpx.AsyncClient
    try:
        httpx.AsyncClient = lambda **kw: real_client(transport=transport, **{k: v for k, v in kw.items() if k != "timeout"})
        resp = await client.evaluate(_request())
    finally:
        httpx.AsyncClient = real_client
    assert resp.decision == "ESCALATE"
    assert client._consecutive_failures == 0
    assert client._cooldown_until == 0.0


@pytest.mark.asyncio
async def test_client_errors_do_not_trip_cooldown():
    client = _client()

    def _bad(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, text="unprocessable")

    transport = httpx.MockTransport(_bad)
    real_client = httpx.AsyncClient
    try:
        httpx.AsyncClient = lambda **kw: real_client(transport=transport, **{k: v for k, v in kw.items() if k != "timeout"})
        for _ in range(5):
            resp = await client.evaluate(_request())
            assert resp.fallback_applied is True
    finally:
        httpx.AsyncClient = real_client
    # 4xx is a request problem: no cooldown, no failure counting.
    assert client._consecutive_failures == 0
    assert client._cooldown_until == 0.0
