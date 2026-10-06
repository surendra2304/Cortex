import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from .peer_transport import PeerTransport


def _utcnow() -> datetime:
    """Timezone-aware UTC now (never a naive timestamp)."""
    return datetime.now(UTC)


logger = logging.getLogger("cortex-futuris-client")


class ForecastHorizon(BaseModel):
    timestamp: datetime
    predicted_value: float
    confidence_lower: float
    confidence_upper: float


class TrafficForecast(BaseModel):
    forecast_id: str
    target_site_id: str
    horizon_hours: int = 24
    current_rps: float
    peak_predicted_rps: float
    capacity_threshold_rps: float = 500.0
    exceeds_capacity: bool = False
    data_points: list[ForecastHorizon] = Field(default_factory=list)
    is_advisory: bool = True
    prediction_is_not_authorization: bool = True
    # Provenance: "futuris" when calibrated by the real service, "fallback" otherwise.
    source: str = "fallback"
    degraded: bool = False
    degraded_reason: str | None = None
    forecast_id_remote: str | None = None
    confidence_label: str | None = None


class ConversionTrendForecast(BaseModel):
    segment_id: str
    current_cvr_pct: float
    predicted_cvr_pct: float
    trajectory: str  # upward, stable, dropping
    drop_probability: float  # 0.0 to 1.0
    bottleneck_step: str | None = None
    confidence: float = 0.88
    is_advisory: bool = True
    prediction_is_not_authorization: bool = True
    source: str = "fallback"
    degraded: bool = False
    degraded_reason: str | None = None


class ChurnSegmentForecast(BaseModel):
    segment_name: str
    predicted_churn_rate_pct: float
    at_risk_account_count: int
    primary_churn_driver: str
    urgency: str  # low, medium, high, critical
    is_advisory: bool = True
    prediction_is_not_authorization: bool = True
    source: str = "fallback"
    degraded: bool = False
    degraded_reason: str | None = None


class FuturisClient:
    """
    Futuris Predictive Forecasting Client:
    - TRAFFIC_FORECAST: Visitor volume next 24h/7d for auto-scaling and capacity planning
    - CONVERSION_TREND: Conversion rate trajectories with 95% confidence intervals
    - CHURN_RISK: High-risk customer segment forecasts
    - FUNNEL_BOTTLENECK_PREDICTION: Predictive funnel drop-off detection
    - CAMPAIGN_IMPACT: Predicted uplift and surge effects from marketing campaigns
    """

    def __init__(
        self,
        api_key: str | None = None,
        mock_mode: bool | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ):
        self.api_key = api_key or os.getenv("FUTURIS_API_KEY", "mock_futuris_key")
        self.transport = PeerTransport("futuris", base_url=base_url, api_key=api_key, timeout_seconds=timeout_seconds)
        if mock_mode is True:
            self.transport.base_url = None
        self.mock_mode = mock_mode if mock_mode is not None else not self.transport.configured

    @property
    def live(self) -> bool:
        """True when this client will ask a real Futuris deployment for calibrated forecasts."""
        return self.transport.configured and not self.mock_mode

    async def _forecast(
        self,
        target: str,
        horizon: str = "24h",
        telemetry: list[dict[str, Any]] | None = None,
        confidence_level: float = 0.90,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Call the Futuris FRIDAY delegation contract. Returns (result, error).

        Cortex never asks Futuris to act: the envelope is a forecast request only, and Futuris
        independently rejects execution requests with 403 (prediction is not authorization).
        """
        payload = {
            "task_id": f"cortex_{uuid.uuid4().hex[:12]}",
            "source_agent": "cortex",
            "target_agent": "futuris",
            "action": "forecast",
            "priority": "normal",
            "payload": {
                "target": target,
                "horizon": horizon,
                "confidence_level": confidence_level,
                "context": context or {},
                "telemetry_data": telemetry or [],
            },
        }
        response = await self.transport.post("/v1/friday/delegate", payload)
        if not response.ok:
            return None, response.detail
        result = response.body.get("result")
        if not isinstance(result, dict):
            return None, f"peer returned no forecast result payload: {response.body}"
        return result, None

    @staticmethod
    def _extract_prediction(result: dict[str, Any]) -> tuple[float, float, float] | None:
        prediction = result.get("prediction") or {}
        try:
            point = float(prediction.get("point_estimate"))
            lower = float(prediction.get("lower_bound"))
            upper = float(prediction.get("upper_bound"))
        except (TypeError, ValueError):
            return None
        return point, lower, upper

    async def predict_traffic(
        self,
        site_id: str,
        horizon_hours: int = 24,
        telemetry: list[dict[str, Any]] | None = None,
    ) -> TrafficForecast:
        """Peak traffic prediction: real Futuris when deployed, deterministic baseline otherwise."""
        if self.live:
            horizon = "1h" if horizon_hours <= 1 else "24h" if horizon_hours <= 24 else "7d"
            result, error = await self._forecast(
                target=f"site:{site_id}:traffic_peak_rps",
                horizon=horizon,
                telemetry=telemetry,
                context={"site_id": site_id, "horizon_hours": horizon_hours},
            )
            if result is None:
                logger.warning("Futuris traffic forecast failed (%s); using the deterministic baseline", error)
                return self._offline_traffic(site_id, horizon_hours, reason=f"futuris forecast failed: {error}")

            prediction = self._extract_prediction(result)
            confidence_label = str(result.get("confidence", ""))
            status = str(result.get("status", "")).upper()
            if prediction is None or status == "INSUFFICIENT_DATA" or confidence_label == "INSUFFICIENT_DATA":
                return self._offline_traffic(
                    site_id,
                    horizon_hours,
                    reason=(
                        f"futuris reported {confidence_label or status or 'no usable prediction'} "
                        "(no calibrated history for this target yet)"
                    ),
                )

            point, lower, upper = prediction
            calibration = float(result.get("calibration_score") or 0.0)
            # Adversarial-but-real check: on thin data Futuris returns a MEDIUM-confidence
            # forecast whose interval spans a negative rate (observed: point 1527, bounds
            # [-5860, +10886]) because it falls back to broad domain priors. Negative requests
            # per second is not a forecast, so this is reported as degraded and the
            # deterministic baseline is used instead of laundering the number as capacity data.
            unusable = (
                point <= 0 or upper <= 0 or lower < -abs(point) or (upper > max(point, 1.0) * 50) or calibration > 0.25
            )
            if unusable:
                return self._offline_traffic(
                    site_id,
                    horizon_hours,
                    reason=(
                        f"futuris forecast not actionable (point={point}, bounds=[{lower}, {upper}], "
                        f"calibration={calibration:.3f})"
                    ),
                )

            # Multi-step intervals make a far better capacity plan than a single point estimate.
            intervals = result.get("intervals") or []
            data_points = [
                ForecastHorizon(
                    timestamp=_utcnow() + timedelta(hours=float(step.get("step", index + 1))),
                    predicted_value=round(float(step.get("central", point)), 2),
                    confidence_lower=round(float(step.get("lower", lower)), 2),
                    confidence_upper=round(float(step.get("upper", upper)), 2),
                )
                for index, step in enumerate(intervals)
                if isinstance(step, dict)
            ]
            peak = max(
                [upper, point, *[p.predicted_value for p in data_points], *[p.confidence_upper for p in data_points]]
            )
            confidence_ok = str(confidence_label).upper() in ("HIGH", "MEDIUM", "COMPLETED")
            return TrafficForecast(
                forecast_id=f"frc_trf_{uuid.uuid4().hex[:8]}",
                target_site_id=site_id,
                horizon_hours=horizon_hours,
                current_rps=round(point, 2),
                peak_predicted_rps=round(peak, 2),
                capacity_threshold_rps=400.0,
                exceeds_capacity=peak > 400.0,
                data_points=data_points
                or [
                    ForecastHorizon(
                        timestamp=_utcnow() + timedelta(hours=horizon_hours),
                        predicted_value=round(point, 2),
                        confidence_lower=round(lower, 2),
                        confidence_upper=round(upper, 2),
                    )
                ],
                source="futuris",
                degraded=not confidence_ok,
                degraded_reason=None if confidence_ok else f"confidence={confidence_label}",
                forecast_id_remote=str(result.get("futuris_forecast_id") or ""),
                confidence_label=confidence_label or None,
            )

        return self._offline_traffic(site_id, horizon_hours)

    def _offline_traffic(self, site_id: str, horizon_hours: int, reason: str | None = None) -> TrafficForecast:
        """Deterministic, documented baseline (unchanged behaviour when Futuris is absent)."""
        now = _utcnow()
        points = []
        base_rps = 180.0
        for i in range(1, min(horizon_hours + 1, 25)):
            t = now + timedelta(hours=i)
            # Simulate afternoon traffic spike
            multiplier = 2.8 if 14 <= t.hour <= 18 else 1.0
            predicted = base_rps * multiplier
            points.append(
                ForecastHorizon(
                    timestamp=t,
                    predicted_value=round(predicted, 1),
                    confidence_lower=round(predicted * 0.9, 1),
                    confidence_upper=round(predicted * 1.15, 1),
                )
            )

        peak = max(p.predicted_value for p in points)
        return TrafficForecast(
            forecast_id=f"frc_trf_{uuid.uuid4().hex[:8]}",
            target_site_id=site_id,
            horizon_hours=horizon_hours,
            current_rps=base_rps,
            peak_predicted_rps=peak,
            capacity_threshold_rps=400.0,
            exceeds_capacity=peak > 400.0,
            data_points=points,
            degraded=reason is not None,
            degraded_reason=reason,
        )

    async def predict_conversion_trends(self, segment_id: str = "enterprise_leads") -> ConversionTrendForecast:
        """Forecasts conversion rate trajectory and bottleneck steps."""
        if "checkout" in segment_id.lower() or "mobile" in segment_id.lower():
            return ConversionTrendForecast(
                segment_id=segment_id,
                current_cvr_pct=3.8,
                predicted_cvr_pct=2.1,
                trajectory="dropping",
                drop_probability=0.78,
                bottleneck_step="/checkout/payment_processing",
                confidence=0.91,
            )
        return ConversionTrendForecast(
            segment_id=segment_id,
            current_cvr_pct=4.5,
            predicted_cvr_pct=5.2,
            trajectory="upward",
            drop_probability=0.15,
            bottleneck_step=None,
            confidence=0.89,
        )

    async def predict_churn_risk(self, tenant_id: str = "default") -> list[ChurnSegmentForecast]:
        """Identifies at-risk customer segments based on behavioral decline signals."""
        return [
            ChurnSegmentForecast(
                segment_name="Mid-Market Free Trial Expiring (Low Activity)",
                predicted_churn_rate_pct=42.5,
                at_risk_account_count=18,
                primary_churn_driver="Incomplete SDK telemetry integration & low team invites",
                urgency="high",
            ),
            ChurnSegmentForecast(
                segment_name="Enterprise Tier 2 (Declining Daily Active Users)",
                predicted_churn_rate_pct=28.0,
                at_risk_account_count=5,
                primary_churn_driver="Recent support tickets on webhook latency",
                urgency="medium",
            ),
        ]

    async def health_check(self) -> dict[str, Any]:
        """Probe the real advisory service when configured; report the mode honestly otherwise."""
        base = {
            "service": "futuris",
            "advisory_only": True,
            "invariant": "prediction_is_not_authorization",
            "timestamp": _utcnow().isoformat(),
        }
        if self.transport.configured:
            response = await self.transport.health()
            return {
                **base,
                "status": "UP" if response.ok else "DOWN",
                # ``mode`` reports what Cortex actually uses for forecasts right now.
                "mode": "live" if response.ok else "deterministic_fallback",
                "peer_reachable": response.ok,
                "base_url": self.transport.base_url,
                "detail": response.detail,
            }
        return {
            **base,
            # Not "UP": no deployment was configured, so nothing was probed.
            "status": "NOT_CONFIGURED",
            "mode": "deterministic_fallback",
            "peer_reachable": False,
            "detail": "FUTURIS_BASE_URL is not configured; answers come from documented baselines",
        }
