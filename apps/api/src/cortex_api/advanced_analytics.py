"""
cortex_api/advanced_analytics.py — Cortex Advanced Analytics Engine.

Extends Cortex's capabilities with:
1. Cohort Analysis: analyze user behavior by cohort
2. Funnel Analytics: track conversion funnels
3. Predictive Churn: predict which customers will churn
4. Revenue Analytics: analyze revenue patterns and forecast
5. User Behavior Clustering: cluster users by behavior patterns
6. Anomaly Detection: detect anomalies in metrics
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
class CohortAnalysis:
    """Cohort analysis result."""
    cohort_id: str
    cohort_name: str
    size: int
    retention_rates: list[float]
    avg_revenue: float
    engagement_score: float
    churn_risk: float


@dataclass
class FunnelStep:
    """A funnel step."""
    step_id: str
    name: str
    users: int
    conversion_rate: float
    avg_time_seconds: float
    drop_off: int


@dataclass
class ChurnPrediction:
    """Churn prediction for a customer."""
    customer_id: str
    churn_probability: float
    risk_factors: list[str]
    recommended_action: str
    lifetime_value: float


@dataclass
class RevenueForecast:
    """Revenue forecast."""
    period: str
    forecasted_revenue: float
    confidence_low: float
    confidence_high: float
    growth_rate: float
    drivers: list[str]


@dataclass
class BehaviorCluster:
    """A user behavior cluster."""
    cluster_id: str
    name: str
    user_count: int
    characteristics: list[str]
    avg_value: float
    engagement: float


class AdvancedAnalytics:
    """Advanced analytics engine for Cortex."""

    def __init__(self):
        self._cohorts: dict[str, CohortAnalysis] = {}
        self._funnels: dict[str, list[FunnelStep]] = {}
        self._churn_predictions: dict[str, ChurnPrediction] = {}
        self._revenue_forecasts: list[RevenueForecast] = []
        self._behavior_clusters: dict[str, BehaviorCluster] = {}
        self._anomalies: list[dict] = []

    # ── Cohort Analysis ───────────────────────────────────────────────────

    def analyze_cohort(
        self,
        cohort_id: str,
        cohort_name: str,
        size: int,
        signup_dates: list[float],
        revenue: list[float],
        engagement_events: list[float],
    ) -> CohortAnalysis:
        """Analyze a user cohort."""
        # Calculate retention rates (simplified)
        retention_rates = []
        base_retention = 0.8 if size > 100 else 0.6

        for i in range(min(6, len(signup_dates))):
            retention = base_retention * (0.85 ** i)
            retention_rates.append(retention)

        # Average revenue
        avg_revenue = sum(revenue) / max(1, len(revenue))

        # Engagement score
        engagement_score = min(1.0, sum(engagement_events) / max(1, len(engagement_events) * 10))

        # Churn risk
        churn_risk = 1.0 - (engagement_score * 0.7 + (1.0 - base_retention) * 0.3)

        analysis = CohortAnalysis(
            cohort_id=cohort_id,
            cohort_name=cohort_name,
            size=size,
            retention_rates=retention_rates,
            avg_revenue=avg_revenue,
            engagement_score=engagement_score,
            churn_risk=churn_risk,
        )

        self._cohorts[cohort_id] = analysis
        return analysis

    # ── Funnel Analytics ────────────────────────────────────────────────────

    def build_funnel(
        self,
        funnel_id: str,
        steps: list[dict],
    ) -> list[FunnelStep]:
        """Build a conversion funnel."""
        funnel = []
        previous_users = None

        for i, step in enumerate(steps):
            users = step.get("users", 0)
            name = step.get("name", f"Step {i}")
            avg_time = step.get("avg_time_seconds", 0.0)

            if previous_users is not None and previous_users > 0:
                conversion_rate = users / previous_users
                drop_off = previous_users - users
            else:
                conversion_rate = 1.0
                drop_off = 0

            funnel.append(FunnelStep(
                step_id=f"{funnel_id}:{i}",
                name=name,
                users=users,
                conversion_rate=conversion_rate,
                avg_time_seconds=avg_time,
                drop_off=drop_off,
            ))

            previous_users = users

        self._funnels[funnel_id] = funnel
        return funnel

    def analyze_funnel_optimization(self, funnel_id: str) -> dict[str, Any]:
        """Analyze a funnel for optimization opportunities."""
        funnel = self._funnels.get(funnel_id, [])
        if not funnel:
            return {"status": "NOT_FOUND"}

        # Find biggest drop-off
        worst_step = None
        worst_drop = 0

        for step in funnel:
            if step.drop_off > worst_drop:
                worst_drop = step.drop_off
                worst_step = step

        recommendations = []
        if worst_step:
            recommendations.append(
                f"Biggest drop-off at '{worst_step.name}' with {worst_step.drop_off} users lost"
            )
            if worst_step.conversion_rate < 0.3:
                recommendations.append(
                    f"Conversion rate only {worst_step.conversion_rate:.1%}. Consider simplifying this step."
                )

        # Overall conversion
        if len(funnel) >= 2:
            overall_conversion = funnel[-1].users / max(1, funnel[0].users)
            recommendations.append(
                f"Overall funnel conversion: {overall_conversion:.1%}"
            )

        return {
            "funnel_id": funnel_id,
            "worst_step": worst_step.name if worst_step else "N/A",
            "overall_conversion": overall_conversion if len(funnel) >= 2 else 0,
            "recommendations": recommendations,
        }

    # ── Predictive Churn ───────────────────────────────────────────────────

    def predict_churn(
        self,
        customer_id: str,
        *,
        login_frequency: float = 0.0,
        last_activity_days: float = 0.0,
        support_tickets: int = 0,
        revenue: float = 0.0,
        tenure_months: float = 0.0,
        engagement_score: float = 0.0,
    ) -> ChurnPrediction:
        """Predict churn probability for a customer."""
        # Churn probability calculation
        churn_prob = 0.0

        # Login frequency (higher = lower churn)
        churn_prob += max(0, 0.3 - login_frequency / 10.0)

        # Last activity (more recent = lower churn)
        churn_prob += min(0.3, last_activity_days / 30.0)

        # Support tickets (more = higher churn)
        churn_prob += min(0.2, support_tickets / 10.0)

        # Engagement (higher = lower churn)
        churn_prob += max(0, 0.2 - engagement_score * 0.3)

        # Tenure (longer = lower churn)
        churn_prob += max(0, 0.15 - tenure_months / 60.0)

        churn_prob = min(1.0, churn_prob)

        # Risk factors
        risk_factors = []
        if login_frequency < 1.0:
            risk_factors.append("Low login frequency")
        if last_activity_days > 14:
            risk_factors.append("Inactive for >14 days")
        if support_tickets > 3:
            risk_factors.append("High support ticket count")
        if engagement_score < 0.2:
            risk_factors.append("Low engagement score")

        # Recommended action
        if churn_prob > 0.7:
            action = "Immediate intervention required - offer retention incentive"
        elif churn_prob > 0.4:
            action = "Proactive outreach - check-in and offer support"
        elif churn_prob > 0.2:
            action = "Monitor closely - engage with content"
        else:
            action = "No action needed - healthy customer"

        # Lifetime value (simplified)
        ltv = revenue * tenure_months * (1.0 - churn_prob)

        prediction = ChurnPrediction(
            customer_id=customer_id,
            churn_probability=churn_prob,
            risk_factors=risk_factors,
            recommended_action=action,
            lifetime_value=ltv,
        )

        self._churn_predictions[customer_id] = prediction
        return prediction

    # ── Revenue Analytics ───────────────────────────────────────────────────

    def forecast_revenue(
        self,
        historical_revenue: list[float],
        period: str = "next_month",
        growth_assumptions: dict[str, float] | None = None,
    ) -> RevenueForecast:
        """Forecast revenue based on historical data."""
        if not historical_revenue:
            return RevenueForecast(
                period=period,
                forecasted_revenue=0.0,
                confidence_low=0.0,
                confidence_high=0.0,
                growth_rate=0.0,
                drivers=["No historical data"],
            )

        # Simple linear trend + growth
        n = len(historical_revenue)
        avg_revenue = sum(historical_revenue) / n

        # Calculate growth rate
        if n >= 2:
            growth_rate = (historical_revenue[-1] - historical_revenue[0]) / max(1, historical_revenue[0])
        else:
            growth_rate = 0.0

        # Apply assumptions
        assumptions = growth_assumptions or {}
        seasonal_factor = assumptions.get("seasonal_factor", 1.0)
        marketing_boost = assumptions.get("marketing_boost", 0.0)
        risk_factor = assumptions.get("risk_factor", 1.0)

        forecasted = avg_revenue * (1.0 + growth_rate) * seasonal_factor * (1.0 + marketing_boost) * risk_factor

        # Confidence interval
        std = math.sqrt(
            sum((r - avg_revenue) ** 2 for r in historical_revenue) / n
        )
        confidence_low = forecasted - std * 1.0
        confidence_high = forecasted + std * 1.0

        # Drivers
        drivers = []
        if growth_rate > 0.1:
            drivers.append(f"Strong growth trend ({growth_rate:.1%})")
        if marketing_boost > 0:
            drivers.append(f"Marketing investment boosting revenue by {marketing_boost:.1%}")
        if seasonal_factor != 1.0:
            drivers.append(f"Seasonal factor: {seasonal_factor:.2f}")
        if not drivers:
            drivers.append("Stable revenue trajectory")

        forecast = RevenueForecast(
            period=period,
            forecasted_revenue=forecasted,
            confidence_low=confidence_low,
            confidence_high=confidence_high,
            growth_rate=growth_rate,
            drivers=drivers,
        )

        self._revenue_forecasts.append(forecast)
        return forecast

    # ── User Behavior Clustering ────────────────────────────────────────────

    def cluster_users(
        self,
        user_data: list[dict],
    ) -> list[BehaviorCluster]:
        """Cluster users by behavior patterns."""
        clusters = []

        # Simple clustering by activity level
        low_activity = []
        medium_activity = []
        high_activity = []

        for user in user_data:
            activity = user.get("activity_score", 0.0)
            revenue = user.get("revenue", 0.0)
            engagement = user.get("engagement", 0.0)

            if activity > 0.7 and revenue > 100:
                high_activity.append(user)
            elif activity > 0.3:
                medium_activity.append(user)
            else:
                low_activity.append(user)

        if high_activity:
            clusters.append(BehaviorCluster(
                cluster_id="high_value",
                name="High-Value Active Users",
                user_count=len(high_activity),
                characteristics=["High activity", "High revenue", "High engagement"],
                avg_value=sum(u.get("revenue", 0) for u in high_activity) / len(high_activity),
                engagement=sum(u.get("engagement", 0) for u in high_activity) / len(high_activity),
            ))

        if medium_activity:
            clusters.append(BehaviorCluster(
                cluster_id="medium_value",
                name="Medium-Value Users",
                user_count=len(medium_activity),
                characteristics=["Medium activity", "Moderate revenue"],
                avg_value=sum(u.get("revenue", 0) for u in medium_activity) / len(medium_activity),
                engagement=sum(u.get("engagement", 0) for u in medium_activity) / len(medium_activity),
            ))

        if low_activity:
            clusters.append(BehaviorCluster(
                cluster_id="low_value",
                name="Low-Value At-Risk Users",
                user_count=len(low_activity),
                characteristics=["Low activity", "Low revenue", "At risk of churn"],
                avg_value=sum(u.get("revenue", 0) for u in low_activity) / len(low_activity),
                engagement=sum(u.get("engagement", 0) for u in low_activity) / len(low_activity),
            ))

        for cluster in clusters:
            self._behavior_clusters[cluster.cluster_id] = cluster

        return clusters

    # ── Anomaly Detection ────────────────────────────────────────────────────

    def detect_anomalies(
        self,
        metric_name: str,
        values: list[float],
        window: int = 20,
    ) -> list[dict]:
        """Detect anomalies in a metric series."""
        anomalies = []

        if len(values) < window:
            return anomalies

        # Rolling average and std
        for i in range(window, len(values)):
            recent = values[i-window:i]
            avg = sum(recent) / window
            std = math.sqrt(sum((v - avg) ** 2 for v in recent) / window)

            current = values[i]
            z_score = abs(current - avg) / std if std > 0 else 0

            if z_score > 3.0:
                anomalies.append({
                    "metric": metric_name,
                    "timestamp": i,
                    "value": current,
                    "expected": avg,
                    "z_score": z_score,
                    "direction": "spike" if current > avg else "drop",
                })
                self._anomalies.append({
                    "metric": metric_name,
                    "value": current,
                    "z_score": z_score,
                })

        return anomalies

    # ── Reporting ──────────────────────────────────────────────────────────

    def get_analytics_report(self) -> dict[str, Any]:
        """Generate an analytics report."""
        return {
            "total_cohorts": len(self._cohorts),
            "total_funnels": len(self._funnels),
            "total_churn_predictions": len(self._churn_predictions),
            "total_revenue_forecasts": len(self._revenue_forecasts),
            "behavior_clusters": len(self._behavior_clusters),
            "total_anomalies": len(self._anomalies),
        }


# Module-level singleton
advanced_analytics = AdvancedAnalytics()


# ── API Routes ──────────────────────────────────────────────────────────────


@router.post("/api/v1/analytics/cohort")
async def analyze_cohort(
    payload: dict,
    db: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_role(Role.CORTEX_OPERATOR)),
):
    """Analyze a user cohort."""
    analysis = advanced_analytics.analyze_cohort(
        cohort_id=payload["cohort_id"],
        cohort_name=payload.get("cohort_name", ""),
        size=payload.get("size", 0),
        signup_dates=payload.get("signup_dates", []),
        revenue=payload.get("revenue", []),
        engagement_events=payload.get("engagement_events", []),
    )
    return analysis.__dict__


@router.post("/api/v1/analytics/funnel")
async def build_funnel(
    payload: dict,
    user: dict = Depends(require_role(Role.CORTEX_OPERATOR)),
):
    """Build a conversion funnel."""
    funnel = advanced_analytics.build_funnel(
        funnel_id=payload["funnel_id"],
        steps=payload["steps"],
    )
    return [step.__dict__ for step in funnel]


@router.get("/api/v1/analytics/funnel/{funnel_id}/optimize")
async def optimize_funnel(
    funnel_id: str,
    user: dict = Depends(require_role(Role.CORTEX_VIEWER)),
):
    """Analyze funnel for optimization."""
    return advanced_analytics.analyze_funnel_optimization(funnel_id)


@router.post("/api/v1/analytics/churn")
async def predict_churn(
    payload: dict,
    user: dict = Depends(require_role(Role.CORTEX_ADMIN)),
):
    """Predict churn for a customer."""
    prediction = advanced_analytics.predict_churn(
        customer_id=payload["customer_id"],
        login_frequency=payload.get("login_frequency", 0.0),
        last_activity_days=payload.get("last_activity_days", 0.0),
        support_tickets=payload.get("support_tickets", 0),
        revenue=payload.get("revenue", 0.0),
        tenure_months=payload.get("tenure_months", 0.0),
        engagement_score=payload.get("engagement_score", 0.0),
    )
    return prediction.__dict__


@router.post("/api/v1/analytics/revenue-forecast")
async def forecast_revenue(
    payload: dict,
    user: dict = Depends(require_role(Role.CORTEX_OPERATOR)),
):
    """Forecast revenue."""
    forecast = advanced_analytics.forecast_revenue(
        historical_revenue=payload["historical_revenue"],
        period=payload.get("period", "next_month"),
        growth_assumptions=payload.get("growth_assumptions"),
    )
    return forecast.__dict__


@router.post("/api/v1/analytics/cluster-users")
async def cluster_users(
    payload: dict,
    user: dict = Depends(require_role(Role.CORTEX_OPERATOR)),
):
    """Cluster users by behavior."""
    clusters = advanced_analytics.cluster_users(payload["user_data"])
    return [c.__dict__ for c in clusters]


@router.post("/api/v1/analytics/detect-anomalies")
async def detect_anomalies(
    payload: dict,
    user: dict = Depends(require_role(Role.CORTEX_ADMIN)),
):
    """Detect anomalies in metric data."""
    anomalies = advanced_analytics.detect_anomalies(
        metric_name=payload["metric"],
        values=payload["values"],
        window=payload.get("window", 20),
    )
    return anomalies


@router.get("/api/v1/analytics/report")
async def analytics_report(
    user: dict = Depends(require_role(Role.CORTEX_VIEWER)),
):
    """Get analytics report."""
    return advanced_analytics.get_analytics_report()
