"""Unit tests for Cortex cognitive reasoning and task decomposition endpoints."""

from __future__ import annotations

import pytest
from cortex_api.main import app
from fastapi.testclient import TestClient

from tests.conftest import friday_headers


@pytest.fixture
def client():
    return TestClient(app)


def test_plan_endpoint_requires_auth(client):
    """Test /plan rejects unauthenticated requests with 401."""
    res = client.post("/plan", json={"goal": "Test goal"})
    assert res.status_code == 401


def test_plan_endpoint_success(client, monkeypatch):
    """Test /plan creates a structured cognitive execution plan when authenticated."""
    headers = friday_headers(monkeypatch)
    payload = {
        "goal": "Optimize visitor conversion on pricing page",
        "context": {"page": "/pricing", "bounce_rate": 0.45},
        "constraints": ["no_breaking_changes", "rate_limit_safe"],
        "priority": "HIGH",
    }
    res = client.post("/plan", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "planned"
    assert data["goal"] == payload["goal"]
    assert len(data["steps"]) >= 3
    assert "reasoning" in data["required_capabilities"]
    assert data["estimated_duration_sec"] > 0
    assert data["observed_at"]


def test_decompose_endpoint_success(client, monkeypatch):
    """Test /decompose decomposes a high-level goal into verifiable subtasks."""
    headers = friday_headers(monkeypatch)
    payload = {
        "goal": "Deploy proactive cart recovery workflow",
        "max_subtasks": 3,
    }
    res = client.post("/decompose", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "decomposed"
    assert data["goal"] == payload["goal"]
    assert len(data["subtasks"]) == 3
    assert data["total_subtasks"] == 3
    assert data["subtasks"][0]["required_capability"] == "analytics"
    assert data["observed_at"]


def test_execute_endpoint_success(client, monkeypatch):
    """Test /execute dispatches task envelope via universal protocol."""
    headers = friday_headers(monkeypatch)
    payload = {
        "task_id": "test_exec_001",
        "action": "health_summary",
        "payload": {"param": "value"},
        "dry_run": True,
    }
    res = client.post("/execute", json=payload, headers=headers)
    assert res.status_code in (200, 202)
    data = res.json()
    assert data["task_id"] == "test_exec_001"
