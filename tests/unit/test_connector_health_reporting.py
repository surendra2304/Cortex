import asyncio

from cortex_integrations.connector_manager import ConnectorManager


def test_unprobed_external_connectors_are_unverified_without_latency():
    result = asyncio.run(ConnectorManager().check_all())

    assert result["overall_status"] == "UNKNOWN"
    assert result["healthy_count"] == 0
    assert result["unverified_count"] == result["total_connectors"] == 7
    assert result["unhealthy_count"] == 0
    for connector in result["connectors"].values():
        assert connector["status"] == "UNKNOWN"
        assert connector["latency_ms"] is None
        assert connector["details"]["reason"] == "No live health probe is configured"


def test_simulated_outage_is_explicit_and_not_reported_as_measured_latency():
    manager = ConnectorManager()
    manager.set_mock_outage("payments", True)

    result = asyncio.run(manager.check_all())
    payment = result["connectors"]["payments"]

    assert result["overall_status"] == "DOWN"
    assert payment["status"] == "DOWN"
    assert payment["latency_ms"] is None
    assert payment["details"]["simulated"] is True
