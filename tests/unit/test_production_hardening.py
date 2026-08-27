import pytest
import os
import sys
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

for p in [
    "packages/core/src",
    "packages/event_schema/src",
    "packages/agents/src",
    "packages/ai_universe_adapter/src",
    "packages/tool_runtime/src",
    "packages/integrations/src",
    "packages/policy_engine/src",
    "packages/workflow_engine/src",
    "packages/identity/src",
    "packages/analytics/src",
    "packages/intelligence/src",
    "packages/memory/src",
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(p))

from nexus_api.main import app
from nexus_api.config import get_db_session, get_redis_client


def test_liveness_probe():
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "UP"


def test_prometheus_metrics_endpoint():
    client = TestClient(app)
    res = client.get("/metrics")
    assert res.status_code == 200
    text = res.text
    assert "events_ingested_total" in text
    assert "cognitive_loop_duration_seconds" in text
    assert "ai_universe_calls_total" in text
    assert "strategy_performance_gauge" in text


def test_readiness_probe_success():
    mock_db = AsyncMock()
    mock_db.execute.return_value = MagicMock()
    mock_redis = AsyncMock()
    mock_redis.ping.return_value = True

    async def override_db():
        yield mock_db

    async def override_redis():
        return mock_redis

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_redis_client] = override_redis

    client = TestClient(app)
    res = client.get("/health/ready")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "READY"
    assert data["dependencies"]["postgres"] == "UP"
    assert data["dependencies"]["redis"] == "UP"

    app.dependency_overrides.clear()
