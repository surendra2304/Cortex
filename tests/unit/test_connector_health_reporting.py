import asyncio

from cortex_integrations.connector_manager import ConnectorManager

UNPROBED = ("email", "crm", "sms", "payments")
PEERS = ("futuris", "intelx", "sentinel")


def test_unprobed_external_connectors_are_unverified_without_latency(monkeypatch):
    # Contract update: the three FRIDAY-Universe peers now perform a real health probe through
    # their clients, so this test pins the honest split instead of the old "everything UNKNOWN".
    # Without a configured base URL each peer reports NOT_CONFIGURED (mapped to UNKNOWN) and
    # says why, rather than the generic "no live health probe is configured".
    for variable in ("FUTURIS_BASE_URL", "INTELX_BASE_URL", "SENTINEL_BASE_URL"):
        monkeypatch.delenv(variable, raising=False)

    result = asyncio.run(ConnectorManager().check_all())

    assert result["overall_status"] == "UNKNOWN"
    assert result["healthy_count"] == 0
    assert result["unverified_count"] == result["total_connectors"] == 7
    assert result["unhealthy_count"] == 0
    for name in UNPROBED:
        connector = result["connectors"][name]
        assert connector["status"] == "UNKNOWN"
        assert connector["latency_ms"] is None
        assert connector["details"]["reason"] == "No live health probe is configured"
    for name in PEERS:
        connector = result["connectors"][name]
        assert connector["status"] == "UNKNOWN", "an undeployed peer must not be reported UP"
        assert connector["latency_ms"] is None
        assert connector["details"]["mode"] == "deterministic_fallback"
        assert connector["details"]["status"] == "NOT_CONFIGURED"
        assert "_BASE_URL is not configured" in connector["details"]["detail"]


def test_configured_but_unreachable_peer_reports_down_with_the_reason(monkeypatch):
    # A configured peer that does not answer must be DOWN — never UNKNOWN, and never UP.
    monkeypatch.setenv("INTELX_BASE_URL", "http://127.0.0.1:9")
    result = asyncio.run(ConnectorManager().check_all())

    intelx = result["connectors"]["intelx"]
    assert intelx["status"] == "DOWN"
    assert intelx["latency_ms"] is None
    assert intelx["details"]["peer_reachable"] is False
    assert intelx["details"]["mode"] == "deterministic_fallback"
    assert result["overall_status"] == "DOWN"


def test_simulated_outage_is_explicit_and_not_reported_as_measured_latency():
    manager = ConnectorManager()
    manager.set_mock_outage("payments", True)

    result = asyncio.run(manager.check_all())
    payment = result["connectors"]["payments"]

    assert result["overall_status"] == "DOWN"
    assert payment["status"] == "DOWN"
    assert payment["latency_ms"] is None
    assert payment["details"]["simulated"] is True
