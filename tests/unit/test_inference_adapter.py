"""Contract tests for Cortex's canonical Inference adapter."""

from __future__ import annotations

from typing import Any

import pytest

from cortex_ai_universe_adapter import (
    AIUniverseClient,
    IntelligenceRequest,
)


class _Response:
    status_code = 200

    def json(self) -> dict[str, Any]:
        return {
            "task_id": "task-42",
            "trace_id": "trace-42",
            "status": "SUCCESS",
            "answer": "Review the candidate using verified evidence.",
            "confidence": 0.72,
            "evidence": ["source:metrics"],
            "proposed_actions": [
                {
                    "action": "review_lead",
                    "target": "lead:42",
                    "parameters": {"priority": "normal"},
                    "is_executable_command": False,
                }
            ],
            "failure_state": None,
        }


class _FakeAsyncClient:
    requests: list[dict[str, Any]] = []

    def __init__(self, timeout: float):
        self.timeout = timeout

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str]) -> _Response:
        self.requests.append({"url": url, "payload": json, "headers": headers})
        return _Response()


@pytest.mark.asyncio
async def test_inference_adapter_uses_v1_ask_and_keeps_actions_advisory(monkeypatch):
    import cortex_ai_universe_adapter as adapter_module

    monkeypatch.setenv("INFERENCE_BASE_URL", "http://inference:8000")
    monkeypatch.setenv("INFERENCE_API_KEY", "test-internal-key")
    monkeypatch.delenv("AI_UNIVERSE_BASE_URL", raising=False)
    _FakeAsyncClient.requests = []
    monkeypatch.setattr(adapter_module.httpx, "AsyncClient", _FakeAsyncClient)

    client = AIUniverseClient(max_retries=1)
    request = IntelligenceRequest(
        request_id="cortex-request-42",
        task_type="lead_scoring",
        goal="Assess this lead using the available evidence.",
        context={"tenant_id": "tenant-test"},
        evidence=[{"value": "visitor provided text", "trust_label": "untrusted_user_input"}],
        trust_labels={"evidence": "untrusted_user_input"},
        provenance={"trace_id": "trace-cortex-42"},
        constraints=["Do not execute actions"],
        required_output={"decision": "string"},
    )

    response = await client.evaluate(request)

    assert _FakeAsyncClient.requests[0]["url"] == "http://inference:8000/v1/ask"
    sent = _FakeAsyncClient.requests[0]["payload"]
    assert sent["task_id"] == "cortex-request-42"
    assert sent["trace_id"] == "trace-cortex-42"
    assert sent["context"]["context"]["tenant_id"] == "tenant-test"
    assert sent["untrusted_data_source"] == "cortex_evidence"
    assert "visitor provided text" in sent["untrusted_data"]
    assert _FakeAsyncClient.requests[0]["headers"]["Authorization"] == "Bearer test-internal-key"
    assert response.request_id == "cortex-request-42"
    assert response.provenance["source"] == "inference"
    assert response.recommended_actions[0].action_type == "review_lead"


@pytest.mark.asyncio
async def test_inference_adapter_fails_closed_to_deterministic_fallback_without_endpoint(monkeypatch):
    import cortex_ai_universe_adapter as adapter_module

    monkeypatch.delenv("INFERENCE_BASE_URL", raising=False)
    monkeypatch.delenv("AI_UNIVERSE_BASE_URL", raising=False)
    client = AIUniverseClient(max_retries=1)

    async def unexpected_client(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("No endpoint is configured; the network must not be called.")

    monkeypatch.setattr(adapter_module.httpx, "AsyncClient", unexpected_client)
    response = await client.evaluate(
        IntelligenceRequest(
            request_id="cortex-request-offline",
            task_type="anomaly_detection",
            goal="Review the supplied event.",
        )
    )

    assert response.fallback_applied is True
    assert response.decision == "NOOP_FALLBACK"
    assert response.recommended_actions == []
