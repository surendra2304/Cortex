import logging
import os
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

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
    data_points: List[ForecastHorizon] = Field(default_factory=list)


class ConversionTrendForecast(BaseModel):
    segment_id: str
    current_cvr_pct: float
    predicted_cvr_pct: float
    trajectory: str  # upward, stable, dropping
    drop_probability: float  # 0.0 to 1.0
    bottleneck_step: Optional[str] = None
    confidence: float = 0.88


class ChurnSegmentForecast(BaseModel):
    segment_name: str
    predicted_churn_rate_pct: float
    at_risk_account_count: int
    primary_churn_driver: str
    urgency: str  # low, medium, high, critical


class FuturisClient:
    """
    Futuris Predictive Forecasting Client:
    - TRAFFIC_FORECAST: Visitor volume next 24h/7d for auto-scaling and capacity planning
    - CONVERSION_TREND: Conversion rate trajectories with 95% confidence intervals
    - CHURN_RISK: High-risk customer segment forecasts
    - FUNNEL_BOTTLENECK_PREDICTION: Predictive funnel drop-off detection
    - CAMPAIGN_IMPACT: Predicted uplift and surge effects from marketing campaigns
    """

    def __init__(self, api_key: Optional[str] = None, mock_mode: bool = True):
        self.api_key = api_key or os.getenv("FUTURIS_API_KEY", "mock_futuris_key")
        self.mock_mode = mock_mode

    async def predict_traffic(self, site_id: str, horizon_hours: int = 24) -> TrafficForecast:
        """Predicts visitor traffic volume and peak requests per second."""
        now = datetime.utcnow()
        points = []
        base_rps = 180.0
        for i in range(1, min(horizon_hours + 1, 25)):
            t = now + timedelta(hours=i)
            # Simulate afternoon traffic spike
            multiplier = 2.8 if 14 <= t.hour <= 18 else 1.0
            predicted = base_rps * multiplier
            points.append(ForecastHorizon(
                timestamp=t,
                predicted_value=round(predicted, 1),
                confidence_lower=round(predicted * 0.9, 1),
                confidence_upper=round(predicted * 1.15, 1)
            ))

        peak = max(p.predicted_value for p in points)
        return TrafficForecast(
            forecast_id=f"frc_trf_{uuid.uuid4().hex[:8]}",
            target_site_id=site_id,
            horizon_hours=horizon_hours,
            current_rps=base_rps,
            peak_predicted_rps=peak,
            capacity_threshold_rps=400.0,
            exceeds_capacity=peak > 400.0,
            data_points=points
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
                confidence=0.91
            )
        return ConversionTrendForecast(
            segment_id=segment_id,
            current_cvr_pct=4.5,
            predicted_cvr_pct=5.2,
            trajectory="upward",
            drop_probability=0.15,
            bottleneck_step=None,
            confidence=0.89
        )

    async def predict_churn_risk(self, tenant_id: str = "default") -> List[ChurnSegmentForecast]:
        """Identifies at-risk customer segments based on behavioral decline signals."""
        return [
            ChurnSegmentForecast(
                segment_name="Mid-Market Free Trial Expiring (Low Activity)",
                predicted_churn_rate_pct=42.5,
                at_risk_account_count=18,
                primary_churn_driver="Incomplete SDK telemetry integration & low team invites",
                urgency="high"
            ),
            ChurnSegmentForecast(
                segment_name="Enterprise Tier 2 (Declining Daily Active Users)",
                predicted_churn_rate_pct=28.0,
                at_risk_account_count=5,
                primary_churn_driver="Recent support tickets on webhook latency",
                urgency="medium"
            )
        ]
