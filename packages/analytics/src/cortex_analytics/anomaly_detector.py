"""
Real-Time Telemetry Anomaly & Outlier Detector for Cortex.

Provides streaming anomaly detection on high-frequency operational metrics:
- Exponentially Weighted Moving Average (EWMA) and Variance (EWMSD) for O(1) online updates
- Robust Modified Z-Score via Median Absolute Deviation (MAD) for heavy-tailed telemetry
- Dynamic multi-level severity classification (NORMAL, WARNING, CRITICAL)
- Anti-flapping hysteresis with configurable consecutive violation counters and alert cooldowns
- Automated incident generation and handoff to self-healing remediation playbooks
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AnomalySeverity(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class MetricType(str, Enum):
    LATENCY_P95 = "latency_p95"
    ERROR_5XX_RATE = "error_5xx_rate"
    FUNNEL_DROPOFF_RATE = "funnel_dropoff_rate"
    VISITOR_SPIKE_VELOCITY = "visitor_spike_velocity"
    RAGE_CLICK_FREQUENCY = "rage_click_frequency"


class AnomalyIncident(BaseModel):
    incident_id: str
    tenant_id: str
    metric_name: str
    observed_value: float
    baseline_mean: float
    baseline_std: float
    z_score: float
    severity: AnomalySeverity
    consecutive_violations: int
    recommendation: str
    auto_remediation_triggered: bool = False
    detected_at: str = Field(default_factory=lambda: _utcnow().isoformat())


class StreamingMetricBaseline:
    """
    Tracks online EWMA and robust sliding window for a single tenant metric.
    """

    def __init__(
        self,
        tenant_id: str,
        metric_name: str,
        alpha: float = 0.15,
        window_size: int = 50,
        warning_z: float = 2.0,
        critical_z: float = 3.5,
        min_std: float = 2.0,
        consecutive_threshold: int = 2,
    ) -> None:
        self.tenant_id = tenant_id
        self.metric_name = metric_name
        self.alpha = alpha
        self.window_size = window_size
        self.warning_z = warning_z
        self.critical_z = critical_z
        self.min_std = min_std
        self.consecutive_threshold = consecutive_threshold

        self.mean: float = 0.0
        self.variance: float = 1.0
        self.count: int = 0
        self.recent_values: list[float] = []
        self.consecutive_anomalies: int = 0
        self.last_incident_time: datetime | None = None

    def update(self, value: float) -> tuple[float, float, float]:
        """
        Ingest next value, update online EWMA/EWMSD, and return (mean, std, z_score).
        """
        self.count += 1
        self.recent_values.append(value)
        if len(self.recent_values) > self.window_size:
            self.recent_values.pop(0)

        if self.count == 1:
            self.mean = value
            self.variance = 1.0
            return self.mean, 1.0, 0.0

        diff = value - self.mean
        self.mean += self.alpha * diff
        # Online Exponentially Weighted Moving Standard Deviation update
        self.variance = (1.0 - self.alpha) * (self.variance + self.alpha * (diff ** 2))
        std = max(self.min_std, math.sqrt(max(0.0001, self.variance)))

        # Relative change check: if absolute difference is tiny relative to mean, not an anomaly
        if abs(diff) < 0.10 * max(1.0, abs(self.mean)):
            z_score = 0.0
        elif len(self.recent_values) >= 10:
            median_val = self._median(self.recent_values)
            deviations = [abs(x - median_val) for x in self.recent_values]
            mad = max(self.min_std, self._median(deviations))
            z_score = 0.6745 * (value - median_val) / mad
        else:
            z_score = diff / std

        return self.mean, std, z_score

    @staticmethod
    def _median(vals: list[float]) -> float:
        s = sorted(vals)
        n = len(s)
        if n == 0:
            return 0.0
        if n % 2 == 1:
            return s[n // 2]
        return (s[n // 2 - 1] + s[n // 2]) / 2.0


class TelemetryAnomalyDetector:
    """
    Tenant-partitioned streaming anomaly detection engine.
    """

    def __init__(self) -> None:
        # {(tenant_id, metric_name): StreamingMetricBaseline}
        self._baselines: dict[tuple[str, str], StreamingMetricBaseline] = {}
        # {tenant_id: [AnomalyIncident, ...]}
        self._incidents: dict[str, list[AnomalyIncident]] = {}

    def get_baseline(
        self,
        tenant_id: str,
        metric_name: str,
    ) -> StreamingMetricBaseline:
        key = (tenant_id, metric_name)
        if key not in self._baselines:
            # Use smaller min_std for rate/percentage metrics
            min_std = 0.05 if ("rate" in metric_name or "ratio" in metric_name) else 2.0
            self._baselines[key] = StreamingMetricBaseline(tenant_id, metric_name, min_std=min_std)
        return self._baselines[key]

    def evaluate_point(
        self,
        tenant_id: str,
        metric_name: str,
        value: float,
        cooldown_seconds: float = 60.0,
    ) -> AnomalyIncident | None:
        """
        Evaluate a single telemetry metric observation for anomalous variance.
        Returns AnomalyIncident if an anomaly exceeds thresholds, else None.
        """
        baseline = self.get_baseline(tenant_id, metric_name)
        mean, std, z_score = baseline.update(value)

        abs_z = abs(z_score)
        severity = AnomalySeverity.NORMAL

        if abs_z >= baseline.critical_z:
            severity = AnomalySeverity.CRITICAL
        elif abs_z >= baseline.warning_z:
            severity = AnomalySeverity.WARNING

        if severity == AnomalySeverity.NORMAL:
            baseline.consecutive_anomalies = 0
            return None

        baseline.consecutive_anomalies += 1
        now = _utcnow()

        # Cooldown check: if already triggered recently, only re-fire if sustained critical violations
        if baseline.last_incident_time and cooldown_seconds > 0:
            elapsed = (now - baseline.last_incident_time).total_seconds()
            if elapsed < cooldown_seconds and baseline.consecutive_anomalies < baseline.consecutive_threshold:
                return None

        # Build Incident
        incident_id = f"inc-{tenant_id[:4]}-{int(now.timestamp())}-{len(self._incidents.get(tenant_id, [])) + 1}"
        recommendation = self._derive_recommendation(metric_name, severity, z_score)

        incident = AnomalyIncident(
            incident_id=incident_id,
            tenant_id=tenant_id,
            metric_name=metric_name,
            observed_value=value,
            baseline_mean=round(mean, 4),
            baseline_std=round(std, 4),
            z_score=round(z_score, 4),
            severity=severity,
            consecutive_violations=baseline.consecutive_anomalies,
            recommendation=recommendation,
            auto_remediation_triggered=(severity == AnomalySeverity.CRITICAL),
        )

        baseline.last_incident_time = now

        if tenant_id not in self._incidents:
            self._incidents[tenant_id] = []
        self._incidents[tenant_id].append(incident)
        return incident

    def list_incidents(
        self,
        tenant_id: str,
        severity: AnomalySeverity | None = None,
        limit: int = 50,
    ) -> list[AnomalyIncident]:
        """List historical anomaly incidents for a tenant."""
        all_incidents = self._incidents.get(tenant_id, [])
        filtered = [
            inc for inc in all_incidents
            if severity is None or inc.severity == severity
        ]
        return list(reversed(filtered))[:limit]

    def _derive_recommendation(self, metric: str, severity: AnomalySeverity, z: float) -> str:
        direction = "spike" if z > 0 else "drop"
        if "5xx" in metric or "error" in metric:
            return f"Execute 5xx circuit-breaker playbook immediately to isolate downstream failures ({direction})."
        if "latency" in metric:
            return f"Scale container worker threads to mitigate high latency ({direction})."
        if "dropoff" in metric or "funnel" in metric:
            return f"Inspect checkout UI and payment gateway errors for funnel dropoff ({direction})."
        return f"Investigate {metric} variance ({direction} with z-score {z:.2f})."


global_anomaly_detector = TelemetryAnomalyDetector()
