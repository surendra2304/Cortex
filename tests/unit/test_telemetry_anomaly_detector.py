"""
Unit tests for Real-Time Telemetry Anomaly & Outlier Detector.
"""

from datetime import UTC, datetime, timedelta
import pytest
from cortex_analytics.anomaly_detector import (
    AnomalyIncident,
    AnomalySeverity,
    MetricType,
    StreamingMetricBaseline,
    TelemetryAnomalyDetector,
)


@pytest.fixture
def detector() -> TelemetryAnomalyDetector:
    return TelemetryAnomalyDetector()


def test_streaming_metric_baseline_updates() -> None:
    baseline = StreamingMetricBaseline(tenant_id="tenant-prod", metric_name="latency_p95", alpha=0.2)
    # Feed stable baseline values
    for _ in range(20):
        mean, std, z = baseline.update(100.0)

    assert 99.0 <= mean <= 101.0
    assert std > 0.0

    # Feed an outlier
    mean, std, z = baseline.update(500.0)
    assert z > 2.0


def test_evaluate_normal_telemetry_returns_none(detector: TelemetryAnomalyDetector) -> None:
    # Seed baseline with normal data
    for _ in range(15):
        incident = detector.evaluate_point("tenant-alpha", "latency_p95", 100.0)
        assert incident is None

    # Slightly higher but normal point
    incident = detector.evaluate_point("tenant-alpha", "latency_p95", 105.0)
    assert incident is None
    assert len(detector.list_incidents("tenant-alpha")) == 0


def test_evaluate_critical_anomaly_triggers_incident(detector: TelemetryAnomalyDetector) -> None:
    # Establish stable baseline of 100ms
    for _ in range(25):
        detector.evaluate_point("tenant-beta", "latency_p95", 100.0)

    # Spike to 1500ms (15x normal)
    incident = detector.evaluate_point("tenant-beta", "latency_p95", 1500.0)
    assert incident is not None
    assert isinstance(incident, AnomalyIncident)
    assert incident.severity in [AnomalySeverity.WARNING, AnomalySeverity.CRITICAL]
    assert incident.observed_value == 1500.0
    assert "latency" in incident.recommendation.lower()

    # Severe spike (10,000ms) triggers critical auto-remediation flag
    critical_inc = detector.evaluate_point("tenant-beta", "latency_p95", 10000.0, cooldown_seconds=0.0)
    assert critical_inc is not None
    assert critical_inc.severity == AnomalySeverity.CRITICAL
    assert critical_inc.auto_remediation_triggered is True


def test_cooldown_and_anti_flapping(detector: TelemetryAnomalyDetector) -> None:
    # Seed baseline
    for _ in range(20):
        detector.evaluate_point("tenant-gamma", "error_5xx_rate", 0.01)

    # First violation -> triggers incident
    inc1 = detector.evaluate_point("tenant-gamma", "error_5xx_rate", 0.85, cooldown_seconds=60.0)
    assert inc1 is not None

    # Immediate second violation within cooldown (with consecutive threshold = 2)
    # The detector will increment consecutive violations
    inc2 = detector.evaluate_point("tenant-gamma", "error_5xx_rate", 0.85, cooldown_seconds=60.0)
    # With consecutive violations reaching 2, it allows evaluation
    assert inc2 is not None
    assert inc2.consecutive_violations == 2


def test_tenant_isolation_anomaly_detector(detector: TelemetryAnomalyDetector) -> None:
    # Tenant 1 has high latency baseline
    for _ in range(20):
        detector.evaluate_point("tenant-1", "latency_p95", 1000.0)

    # Tenant 2 has low latency baseline
    for _ in range(20):
        detector.evaluate_point("tenant-2", "latency_p95", 50.0)

    base1 = detector.get_baseline("tenant-1", "latency_p95")
    base2 = detector.get_baseline("tenant-2", "latency_p95")

    assert base1.mean > 800.0
    assert base2.mean < 100.0
    assert len(detector.list_incidents("tenant-1")) == 0
    assert len(detector.list_incidents("tenant-2")) == 0
