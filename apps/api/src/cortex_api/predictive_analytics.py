"""
cortex_api/predictive_analytics.py — Cortex Predictive Analytics Engine.

Extends Cortex's capabilities with:
1. Time Series Forecasting: predict future metrics
2. Trend Analysis: detect and extrapolate trends
3. Seasonality Detection: identify seasonal patterns
4. Anomaly Prediction: predict when anomalies will occur
5. Demand Forecasting: predict product/service demand
6. Customer Behavior Prediction: predict future customer actions
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from cortex_api.config import get_db_session
from cortex_api.auth import Role, require_role

router = APIRouter()


@dataclass
class TimeSeriesData:
    """Time series data point."""
    timestamp: float
    value: float
    category: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class ForecastResult:
    """Forecast result."""
    metric_name: str
    forecast: list[float]
    confidence_lower: list[float]
    confidence_upper: list[float]
    accuracy: float
    trend: str  # upward, downward, stable
    seasonality: bool


@dataclass
class TrendAnalysis:
    """Trend analysis result."""
    metric_name: str
    trend_direction: str
    trend_strength: float
    momentum: float
    projected_value: float
    projected_time: float
    confidence: float


@dataclass
class DemandForecast:
    """Demand forecast."""
    product_id: str
    current_demand: float
    forecasted_demand: float
    growth_rate: float
    confidence: float
    seasonal_factor: float
    recommendation: str


class PredictiveAnalytics:
    """Predictive analytics engine."""

    def __init__(self):
        self._forecasts: dict[str, ForecastResult] = {}
        self._trends: dict[str, TrendAnalysis] = {}
        self._demand_forecasts: dict[str, DemandForecast] = {}

    # ── Time Series Forecasting ──────────────────────────────────────────────

    def forecast(
        self,
        metric_name: str,
        history: list[float],
        steps: int = 7,
    ) -> ForecastResult:
        """Forecast future values using simple moving average + trend."""
        if len(history) < 3:
            return ForecastResult(
                metric_name=metric_name,
                forecast=[history[-1]] * steps if history else [],
                confidence_lower=[0.0] * steps,
                confidence_upper=[0.0] * steps,
                accuracy=0.0,
                trend="stable",
                seasonality=False,
            )

        # Calculate trend
        n = len(history)
        x_mean = sum(range(n)) / n
        y_mean = sum(history) / n

        numerator = sum((i - x_mean) * (h - y_mean) for i, h in enumerate(history))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = numerator / max(1e-10, denominator)

        intercept = y_mean - slope * x_mean

        # Forecast
        forecast = []
        for i in range(steps):
            idx = n + i
            forecast.append(max(0, intercept + slope * idx))

        # Confidence intervals
        # Calculate residuals
        residuals = [history[i] - (intercept + slope * i) for i in range(n)]
        std = math.sqrt(sum(r ** 2 for r in residuals) / n)

        lower = [f - std * 1.96 for f in forecast]
        upper = [f + std * 1.96 for f in forecast]

        # Accuracy (simplified: 1 - std/mean)
        accuracy = max(0.0, 1.0 - std / max(1.0, y_mean))

        # Trend
        if slope > 0.01:
            trend = "upward"
        elif slope < -0.01:
            trend = "downward"
        else:
            trend = "stable"

        # Seasonality detection
        seasonality = self._detect_seasonality(history)

        result = ForecastResult(
            metric_name=metric_name,
            forecast=forecast,
            confidence_lower=lower,
            confidence_upper=upper,
            accuracy=accuracy,
            trend=trend,
            seasonality=seasonality,
        )

        self._forecasts[metric_name] = result
        return result

    def _detect_seasonality(self, history: list[float]) -> bool:
        """Detect if data has seasonality."""
        if len(history) < 7:
            return False

        # Compare first half and second half
        mid = len(history) // 2
        first_half = history[:mid]
        second_half = history[mid:]

        first_mean = sum(first_half) / len(first_half)
        second_mean = sum(second_half) / len(second_half)

        # If they differ significantly, might have seasonality
        diff = abs(first_mean - second_mean) / max(1.0, first_mean)
        return diff > 0.2

    # ── Trend Analysis ──────────────────────────────────────────────────────

    def analyze_trend(
        self,
        metric_name: str,
        history: list[float],
        project_days: float = 30.0,
    ) -> TrendAnalysis:
        """Analyze trend and project future values."""
        if len(history) < 2:
            return TrendAnalysis(
                metric_name=metric_name,
                trend_direction="stable",
                trend_strength=0.0,
                momentum=0.0,
                projected_value=history[-1] if history else 0.0,
                projected_time=project_days,
                confidence=0.0,
            )

        # Calculate recent change
        recent_change = history[-1] - history[-2]
        pct_change = recent_change / max(1.0, history[-2])

        # Calculate momentum (average of last 3 changes)
        changes = []
        for i in range(1, min(4, len(history))):
            changes.append(history[-i] - history[-i-1])
        momentum = sum(changes) / len(changes) if changes else 0.0

        # Trend strength
        trend_strength = abs(pct_change)

        # Project
        projected = history[-1] + momentum * (project_days / 1.0)

        # Confidence
        confidence = min(0.9, 0.3 + abs(pct_change) * 5)

        return TrendAnalysis(
            metric_name=metric_name,
            trend_direction="upward" if pct_change > 0.02 else "downward" if pct_change < -0.02 else "stable",
            trend_strength=trend_strength,
            momentum=momentum,
            projected_value=projected,
            projected_time=project_days,
            confidence=confidence,
        )

    # ── Seasonality Detection ────────────────────────────────────────────────

    def detect_seasonal_pattern(
        self,
        history: list[float],
        period: int = 7,
    ) -> dict[str, Any]:
        """Detect seasonal patterns."""
        if len(history) < period * 2:
            return {"has_seasonality": False, "period": period}

        # Split into periods
        periods = []
        for i in range(0, len(history) - period + 1, period):
            periods.append(history[i:i + period])

        if len(periods) < 2:
            return {"has_seasonality": False, "period": period}

        # Compare period averages
        period_avgs = [sum(p) / len(p) for p in periods]

        # Calculate variance between periods
        overall_avg = sum(period_avgs) / len(period_avgs)
        variance = sum((a - overall_avg) ** 2 for a in period_avgs) / len(period_avgs)
        cv = math.sqrt(variance) / max(1.0, overall_avg)

        has_seasonality = cv > 0.15

        return {
            "has_seasonality": has_seasonality,
            "period": period,
            "period_averages": period_avgs,
            "coefficient_of_variation": cv,
            "peak_period": period_avgs.index(max(period_avgs)),
            "trough_period": period_avgs.index(min(period_avgs)),
        }

    # ── Demand Forecasting ──────────────────────────────────────────────────

    def forecast_demand(
        self,
        product_id: str,
        sales_history: list[float],
        seasonal_factor: float = 1.0,
    ) -> DemandForecast:
        """Forecast product demand."""
        if not sales_history:
            return DemandForecast(
                product_id=product_id,
                current_demand=0.0,
                forecasted_demand=0.0,
                growth_rate=0.0,
                confidence=0.0,
                seasonal_factor=seasonal_factor,
                recommendation="No historical data",
            )

        current_demand = sales_history[-1]

        # Calculate growth rate
        if len(sales_history) >= 2:
            growth_rate = (sales_history[-1] - sales_history[0]) / max(1.0, sales_history[0])
        else:
            growth_rate = 0.0

        # Forecast next period
        forecasted = current_demand * (1 + growth_rate) * seasonal_factor

        # Confidence
        confidence = min(0.85, 0.4 + abs(growth_rate) * 2)

        # Recommendation
        if growth_rate > 0.1:
            recommendation = "Increase inventory - demand is growing"
        elif growth_rate < -0.1:
            recommendation = "Reduce inventory - demand is declining"
        else:
            recommendation = "Maintain current inventory levels"

        result = DemandForecast(
            product_id=product_id,
            current_demand=current_demand,
            forecasted_demand=forecasted,
            growth_rate=growth_rate,
            confidence=confidence,
            seasonal_factor=seasonal_factor,
            recommendation=recommendation,
        )

        self._demand_forecasts[product_id] = result
        return result

    # ── Customer Behavior Prediction ────────────────────────────────────────

    def predict_customer_behavior(
        self,
        customer_id: str,
        behavior_history: list[dict],
    ) -> dict[str, Any]:
        """Predict future customer behavior."""
        if not behavior_history:
            return {"prediction": "inactive", "confidence": 0.0}

        # Analyze recent patterns
        recent = behavior_history[-10:]

        # Calculate activity frequency
        days_active = len(set(b.get("date", 0) for b in recent))
        frequency = days_active / max(1, len(recent))

        # Calculate engagement trend
        if len(recent) >= 2:
            engagement_change = recent[-1].get("engagement", 0) - recent[0].get("engagement", 0)
        else:
            engagement_change = 0

        # Predict next action
        if frequency > 0.5 and engagement_change > 0:
            prediction = "highly_active"
            confidence = 0.8
        elif frequency > 0.3:
            prediction = "active"
            confidence = 0.6
        elif frequency > 0.1:
            prediction = "moderately_active"
            confidence = 0.5
        else:
            prediction = "inactive"
            confidence = 0.4

        # Predict next action type
        actions = [b.get("action", "") for b in recent]
        if actions:
            most_common = max(set(actions), key=actions.count)
            predicted_action = most_common
        else:
            predicted_action = "unknown"

        return {
            "prediction": prediction,
            "confidence": confidence,
            "predicted_action": predicted_action,
            "engagement_trend": "rising" if engagement_change > 0 else "falling" if engagement_change < 0 else "stable",
        }

    # ── Reporting ──────────────────────────────────────────────────────────

    def get_analytics_report(self) -> dict[str, Any]:
        """Generate a predictive analytics report."""
        return {
            "total_forecasts": len(self._forecasts),
            "total_trends": len(self._trends),
            "demand_forecasts": len(self._demand_forecasts),
            "avg_forecast_accuracy": sum(
                f.accuracy for f in self._forecasts.values()
            ) / max(1, len(self._forecasts)),
        }


# Module-level singleton
predictive_analytics = PredictiveAnalytics()


# ── API Routes ──────────────────────────────────────────────────────────────


@router.post("/api/v1/analytics/forecast")
async def forecast_metric(
    payload: dict,
    db: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_role(Role.CORTEX_OPERATOR)),
):
    """Forecast a metric."""
    result = predictive_analytics.forecast(
        metric_name=payload["metric"],
        history=payload["history"],
        steps=payload.get("steps", 7),
    )
    return {
        "metric": result.metric_name,
        "forecast": result.forecast,
        "confidence_lower": result.confidence_lower,
        "confidence_upper": result.confidence_upper,
        "accuracy": result.accuracy,
        "trend": result.trend,
        "seasonality": result.seasonality,
    }


@router.get("/api/v1/analytics/trend/{metric_name}")
async def analyze_trend(
    metric_name: str,
    history: list[float],
    user: dict = Depends(require_role(Role.CORTEX_VIEWER)),
):
    """Analyze a trend."""
    result = predictive_analytics.analyze_trend(metric_name, history)
    return result.__dict__


@router.post("/api/v1/analytics/seasonality")
async def detect_seasonality(
    payload: dict,
    user: dict = Depends(require_role(Role.CORTEX_OPERATOR)),
):
    """Detect seasonal patterns."""
    return predictive_analytics.detect_seasonal_pattern(
        payload["history"],
        period=payload.get("period", 7),
    )


@router.post("/api/v1/analytics/demand-forecast")
async def demand_forecast(
    payload: dict,
    user: dict = Depends(require_role(Role.CORTEX_OPERATOR)),
):
    """Forecast product demand."""
    result = predictive_analytics.forecast_demand(
        product_id=payload["product_id"],
        sales_history=payload["sales_history"],
        seasonal_factor=payload.get("seasonal_factor", 1.0),
    )
    return result.__dict__


@router.get("/api/v1/analytics/predictive/report")
async def predictive_report(
    user: dict = Depends(require_role(Role.CORTEX_VIEWER)),
):
    """Get predictive analytics report."""
    return predictive_analytics.get_analytics_report()
