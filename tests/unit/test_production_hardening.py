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

from cortex_api.config import get_db_session, get_redis_client
from cortex_api.main import app


def test_liveness_probe():
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "UP"
    # Evidence contract: a liveness answer must say what it proves and when.
    assert res.json()["evidence_class"] == "process_liveness"
    assert res.json()["observed_at"]
    assert res.json()["timestamp"] == res.json()["observed_at"]


def test_liveness_probe_answers_head_request():
    res = TestClient(app).head("/health")
    assert res.status_code == 200


def test_versioned_health_probe_carries_evidence_fields():
    res = TestClient(app).get("/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "healthy"
    assert body["evidence_class"] == "process_liveness"
    assert body["observed_at"]


def test_prometheus_metrics_endpoint():
    client = TestClient(app)
    res = client.get("/metrics")
    assert res.status_code == 200
    text = res.text
    assert "events_ingested_total" in text
    assert "cognitive_loop_duration_seconds" in text
    assert "ai_universe_calls_total" in text
    assert "strategy_performance_gauge" in text


def test_readiness_probe_success(monkeypatch):
    """Required dependencies up ⇒ READY, and unconfigured optional probes are reported.

    The schema probe is stubbed: it inspects the process-wide engine, so this test asserts
    the readiness *decision* rather than whatever schema happens to exist next to the
    checkout (a missing data/ directory made it fail for the wrong reason).
    """

    async def _no_missing_tables(engine):  # noqa: ANN001 - signature of the real probe
        return []

    monkeypatch.setattr("cortex_api.schema.missing_tables", _no_missing_tables)

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
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "READY"
    assert data["required_dependencies"] == ["postgres", "schema", "redis"]
    assert data["dependencies"]["postgres"] == "UP"
    assert data["dependencies"]["redis"] == "UP"
    for dependency in ("ai_universe", "sentinel", "intelx", "futuris"):
        assert data["dependencies"][dependency].startswith("UNKNOWN:")
        assert dependency in data["degraded"]
    assert data["evidence_class"] == "dependency_readiness"
    assert data["observed_at"]

    app.dependency_overrides.clear()


def test_readiness_probe_fails_when_required_redis_is_unavailable():
    mock_db = AsyncMock()
    mock_db.execute.return_value = MagicMock()
    mock_redis = AsyncMock()
    mock_redis.ping.side_effect = ConnectionError("Redis is unavailable")

    async def override_db():
        yield mock_db

    async def override_redis():
        return mock_redis

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_redis_client] = override_redis

    try:
        res = TestClient(app).get("/health/ready")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "NOT_READY"
        assert data["dependencies"]["postgres"] == "UP"
        assert data["dependencies"]["redis"].startswith("DOWN:")
    finally:
        app.dependency_overrides.clear()
