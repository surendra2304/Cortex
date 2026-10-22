"""Unit tests for Tier-1 resilience upgrades: TTLCache, peer transport pooling, and probes."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from cortex_core.resilience import CircuitState, SubsystemCircuit
from cortex_integrations.peer_transport import (
    close_shared_client,
    get_shared_client,
)

from cortex_upgrade.cache import TTLCache


def test_ttl_cache_basic_operations():
    cache = TTLCache[str, int](maxsize=3, default_ttl_seconds=1.0)
    cache.set("a", 10)
    cache.set("b", 20)

    assert cache.get("a") == 10
    assert cache.get("b") == 20
    assert cache.get("c") is None
    assert len(cache) == 2
    assert "a" in cache

    # LRU eviction when maxsize is exceeded
    cache.set("c", 30)
    cache.set("d", 40)
    # Cache size is 3, "a" was accessed earlier so "b" is oldest if not accessed, or "a" if "b" accessed
    assert len(cache) == 3

    # Delete operation
    assert cache.delete("d") is True
    assert cache.delete("d") is False
    assert cache.get("d") is None

    # Clear
    cache.clear()
    assert len(cache) == 0


def test_ttl_cache_expiration():
    cache = TTLCache[str, str](maxsize=10, default_ttl_seconds=0.05)
    cache.set("ephemeral", "hello")
    assert cache.get("ephemeral") == "hello"

    time.sleep(0.08)
    assert cache.get("ephemeral") is None
    assert "ephemeral" not in cache


def test_ttl_cache_thread_safety():
    cache = TTLCache[int, int](maxsize=500, default_ttl_seconds=10.0)

    def worker(offset: int):
        for i in range(100):
            cache.set(offset + i, (offset + i) * 2)
            val = cache.get(offset + i)
            assert val == (offset + i) * 2

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(worker, i * 100) for i in range(5)]
        for f in futures:
            f.result()

    assert len(cache) <= 500


@pytest.mark.asyncio
async def test_peer_transport_shared_client_lifecycle():
    client1 = get_shared_client()
    assert client1 is not None
    assert not client1.is_closed

    client2 = get_shared_client()
    assert client1 is client2

    await close_shared_client()
    assert client1.is_closed

    # Next call re-creates
    client3 = get_shared_client()
    assert not client3.is_closed
    await close_shared_client()


@pytest.mark.asyncio
async def test_subsystem_circuit_state_machine():
    circuit = SubsystemCircuit(name="test_service", failure_threshold=2, recovery_timeout_seconds=0.1)
    assert await circuit.before() is True
    assert circuit.state == CircuitState.CLOSED

    # First failure
    await circuit.record_failure("error 1")
    assert await circuit.before() is True
    assert circuit.state == CircuitState.CLOSED

    # Second failure trips circuit open
    await circuit.record_failure("error 2")
    assert circuit.state == CircuitState.OPEN
    assert await circuit.before() is False

    # Wait for recovery timeout to half-open
    time.sleep(0.12)
    assert await circuit.before() is True  # Half-open trial allowed
    assert circuit.state == CircuitState.HALF_OPEN

    # Success resets to closed
    await circuit.record_success()
    assert circuit.state == CircuitState.CLOSED
    assert await circuit.before() is True


def test_standardized_probes(api_client, monkeypatch):
    async def _no_missing(engine):
        return []

    monkeypatch.setattr("cortex_api.schema.missing_tables", _no_missing)

    # Liveness probe
    res_health = api_client.get("/health")
    assert res_health.status_code == 200
    data_health = res_health.json()
    assert data_health["status"] in ("ok", "healthy", "UP")
    assert data_health["service"] == "cortex"
    assert "version" in data_health

    # Readiness probe
    res_ready = api_client.get("/ready")
    assert res_ready.status_code == 200
    data_ready = res_ready.json()
    assert data_ready["status"] in ("READY", "ready")
    assert data_ready["dependencies"]["postgres"] == "UP"
    assert data_ready["dependencies"]["redis"] == "UP"

    # Readiness alias
    res_health_ready = api_client.get("/health/ready")
    assert res_health_ready.status_code == 200
    assert res_health_ready.json()["status"] in ("READY", "ready")

    # Status / Telemetry probe
    res_status = api_client.get("/status")
    assert res_status.status_code == 200
    data_status = res_status.json()
    assert data_status["status"] == "operational"
    assert data_status["service"] == "cortex"
    assert data_status["uptime_seconds"] >= 0


def test_standardized_error_envelope(api_client, monkeypatch):
    from tests.conftest import friday_headers

    headers = friday_headers(monkeypatch)

    # Verify validation error on /plan returns standardized envelope
    res_val = api_client.post("/plan", json={"invalid_field": 123}, headers=headers)
    assert res_val.status_code == 422
    data = res_val.json()
    assert data["success"] is False
    assert data["error"] == "VALIDATION_ERROR"
    assert "detail" in data
    assert "message" in data
