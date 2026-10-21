"""Dynamic Canary Rollout & Automated Rollback Controller for CORTEX.

Governs progressive delivery stages (0% -> 5% -> 25% -> 50% -> 100%):
- Continuously monitors live traffic error rate, p95/p99 latency, and security signals
- Evaluates statistical thresholds before permitting stage advancement
- Triggers instant automated rollback to 0% if error rate > 1.0% or SLOs breach
- Maintains immutable transition audit trail for post-incident review
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger("cortex-core.canary-controller")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CanaryStage(str, Enum):
    BASELINE_0 = "0%"
    CANARY_5 = "5%"
    CANARY_25 = "25%"
    CANARY_50 = "50%"
    PRODUCTION_100 = "100%"

    @property
    def percentage(self) -> int:
        return int(self.value.replace("%", ""))

    def next_stage(self) -> CanaryStage | None:
        sequence = [
            CanaryStage.BASELINE_0,
            CanaryStage.CANARY_5,
            CanaryStage.CANARY_25,
            CanaryStage.CANARY_50,
            CanaryStage.PRODUCTION_100,
        ]
        idx = sequence.index(self)
        if idx < len(sequence) - 1:
            return sequence[idx + 1]
        return None


@dataclass
class CanaryPolicy:
    max_error_rate_pct: float = 1.0
    max_p99_latency_ms: float = 500.0
    max_security_alerts: int = 0
    min_sample_requests: int = 50
    observation_window_seconds: float = 60.0


@dataclass
class CanaryTransitionRecord:
    from_stage: CanaryStage
    to_stage: CanaryStage
    reason: str
    metrics: dict[str, Any]
    initiated_by: str
    timestamp: datetime = field(default_factory=_utcnow)

    def as_dict(self) -> dict[str, Any]:
        return {
            "from_stage": self.from_stage.value,
            "to_stage": self.to_stage.value,
            "reason": self.reason,
            "metrics": self.metrics,
            "initiated_by": self.initiated_by,
            "timestamp": self.timestamp.isoformat(),
        }


class CanaryRolloutController:
    """Manages progressive canary deployments with automated health gating and rollback."""

    def __init__(self, deployment_id: str, policy: CanaryPolicy | None = None) -> None:
        self.deployment_id = deployment_id
        self.policy = policy or CanaryPolicy()
        self.current_stage = CanaryStage.BASELINE_0
        self.is_rolled_back = False

        self._requests: int = 0
        self._errors: int = 0
        self._latencies: list[float] = []
        self._security_alerts: int = 0

        self._history: list[CanaryTransitionRecord] = []
        self._lock = asyncio.Lock()

    async def record_traffic_metric(
        self, is_error: bool, latency_ms: float, is_security_alert: bool = False
    ) -> None:
        """Record live incoming request metrics during canary observation window."""
        async with self._lock:
            self._requests += 1
            if is_error:
                self._errors += 1
            if latency_ms >= 0:
                self._latencies.append(latency_ms)
                # Cap latencies array to bounded size
                if len(self._latencies) > 5000:
                    self._latencies = self._latencies[-2500:]
            if is_security_alert:
                self._security_alerts += 1

    def _compute_metrics(self) -> dict[str, Any]:
        n = self._requests
        err_rate = (self._errors / n * 100.0) if n > 0 else 0.0

        if self._latencies:
            sorted_lat = sorted(self._latencies)
            idx95 = min(int(len(sorted_lat) * 0.95), len(sorted_lat) - 1)
            idx99 = min(int(len(sorted_lat) * 0.99), len(sorted_lat) - 1)
            p95 = sorted_lat[idx95]
            p99 = sorted_lat[idx99]
        else:
            p95 = 0.0
            p99 = 0.0

        return {
            "requests": n,
            "errors": self._errors,
            "error_rate_pct": round(err_rate, 3),
            "p95_latency_ms": round(p95, 2),
            "p99_latency_ms": round(p99, 2),
            "security_alerts": self._security_alerts,
        }

    async def evaluate_health(self) -> tuple[bool, str, dict[str, Any]]:
        """Evaluate current stage health against configured policy."""
        async with self._lock:
            metrics = self._compute_metrics()

        n = metrics["requests"]
        if n < self.policy.min_sample_requests:
            return (
                True,
                f"Sample size ({n}) below minimum threshold ({self.policy.min_sample_requests}); health held nominal.",
                metrics,
            )

        err_rate = metrics["error_rate_pct"]
        if err_rate > self.policy.max_error_rate_pct:
            return (
                False,
                f"Error rate {err_rate:.2f}% exceeds maximum allowed {self.policy.max_error_rate_pct}%.",
                metrics,
            )

        p99 = metrics["p99_latency_ms"]
        if p99 > self.policy.max_p99_latency_ms:
            return (
                False,
                f"p99 latency {p99:.1f}ms exceeds SLA limit {self.policy.max_p99_latency_ms}ms.",
                metrics,
            )

        alerts = metrics["security_alerts"]
        if alerts > self.policy.max_security_alerts:
            return (
                False,
                f"Security alerts ({alerts}) exceed zero-tolerance threshold ({self.policy.max_security_alerts}).",
                metrics,
            )

        return (
            True,
            f"All health indicators nominal (err_rate={err_rate:.2f}%, p99={p99:.1f}ms, alerts={alerts}).",
            metrics,
        )

    async def advance_stage(self, operator: str = "automated_controller") -> tuple[bool, str]:
        """Advance to next canary stage if health checks pass. Rollback if violated."""
        async with self._lock:
            if self.is_rolled_back:
                return False, f"Deployment '{self.deployment_id}' has been rolled back; advance disallowed."

            next_st = self.current_stage.next_stage()
            if not next_st:
                return True, f"Deployment '{self.deployment_id}' already at 100% production."

        healthy, reason, metrics = await self.evaluate_health()
        if not healthy:
            await self.rollback(f"Automated health check failed prior to advance: {reason}", operator=operator)
            return False, f"Health check failed! Automatically rolled back to 0%: {reason}"

        async with self._lock:
            prev = self.current_stage
            self.current_stage = next_st
            # Reset window metrics for the new stage observation period
            self._requests = 0
            self._errors = 0
            self._latencies.clear()
            self._security_alerts = 0

            rec = CanaryTransitionRecord(
                from_stage=prev,
                to_stage=next_st,
                reason=f"Health verified. Advanced to {next_st.value}.",
                metrics=metrics,
                initiated_by=operator,
            )
            self._history.append(rec)

        logger.info(
            f"Canary '{self.deployment_id}' advanced from {prev.value} to {next_st.value} by {operator}."
        )
        return True, f"Successfully advanced to {next_st.value}."

    async def rollback(self, reason: str, operator: str = "automated_controller") -> CanaryTransitionRecord:
        """Immediately abort canary and route 100% traffic back to baseline."""
        async with self._lock:
            metrics = self._compute_metrics()
            prev = self.current_stage
            self.current_stage = CanaryStage.BASELINE_0
            self.is_rolled_back = True

            rec = CanaryTransitionRecord(
                from_stage=prev,
                to_stage=CanaryStage.BASELINE_0,
                reason=reason,
                metrics=metrics,
                initiated_by=operator,
            )
            self._history.append(rec)

        logger.critical(
            f"Canary '{self.deployment_id}' EMERGENCY ROLLBACK from {prev.value} to 0% by {operator}: {reason}"
        )
        return rec

    async def get_state(self) -> dict[str, Any]:
        """Full state summary of the canary deployment."""
        async with self._lock:
            metrics = self._compute_metrics()
            return {
                "deployment_id": self.deployment_id,
                "current_stage": self.current_stage.value,
                "traffic_split_pct": self.current_stage.percentage,
                "is_rolled_back": self.is_rolled_back,
                "policy": {
                    "max_error_rate_pct": self.policy.max_error_rate_pct,
                    "max_p99_latency_ms": self.policy.max_p99_latency_ms,
                    "max_security_alerts": self.policy.max_security_alerts,
                    "min_sample_requests": self.policy.min_sample_requests,
                },
                "metrics": metrics,
                "history": [r.as_dict() for r in self._history],
            }


# Registry of active canary rollouts
class CanaryRegistry:
    def __init__(self) -> None:
        self._deployments: dict[str, CanaryRolloutController] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(
        self, deployment_id: str, policy: CanaryPolicy | None = None
    ) -> CanaryRolloutController:
        async with self._lock:
            if deployment_id not in self._deployments:
                self._deployments[deployment_id] = CanaryRolloutController(deployment_id, policy)
            return self._deployments[deployment_id]

    async def get(self, deployment_id: str) -> CanaryRolloutController | None:
        async with self._lock:
            return self._deployments.get(deployment_id)


global_canary_registry = CanaryRegistry()
