"""
Behavioral Churn Prediction & RFM Segmentation Engine for Cortex.

Provides production-grade RFM (Recency, Frequency, Monetary) customer segmentation,
non-parametric and parametric churn hazard rate estimation, anomaly-weighted risk scoring,
and dynamic lead intent acceleration detection for autonomous agent routing.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any
from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_datetime(dt_val: Any) -> datetime:
    if isinstance(dt_val, datetime):
        return dt_val if dt_val.tzinfo else dt_val.replace(tzinfo=UTC)
    if isinstance(dt_val, str):
        try:
            cleaned = dt_val.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(cleaned)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except Exception:
            return _utcnow()
    return _utcnow()


class CustomerRFMProfile(BaseModel):
    actor_id: str
    recency_days: float
    frequency_events: int
    monetary_value: float
    r_score: int = Field(ge=1, le=5)
    f_score: int = Field(ge=1, le=5)
    m_score: int = Field(ge=1, le=5)
    composite_rfm: float
    tier: str  # CHAMPION, LOYAL_CUSTOMER, POTENTIAL_LOYALIST, AT_RISK, CANT_LOSE_THEM, HIBERNATING, LOST
    traits: dict[str, Any] = Field(default_factory=dict)


class ChurnRiskAssessment(BaseModel):
    actor_id: str
    churn_probability: float = Field(ge=0.0, le=1.0)
    risk_level: str  # LOW, MODERATE, HIGH, CRITICAL
    hazard_score: float
    risk_factors: list[str]
    mitigation_recommendation: str
    assessed_at: str = Field(default_factory=lambda: _utcnow().isoformat())


class LeadIntentAcceleration(BaseModel):
    actor_id: str
    acceleration_factor: float
    velocity_events_per_hour: float
    total_intent_touches: int
    priority_routing: str  # P0_ENTERPRISE_FAST_TRACK, P1_AE_HANDOFF, P2_AUTOMATED_NURTURE
    recommended_play: str


class BehavioralChurnClassifier:
    """
    Analyzes event stream behavior to segment customer cohorts and predict churn probability.
    """

    def compute_rfm_scores(
        self,
        actors_data: list[dict[str, Any]],
        reference_now: datetime | None = None,
    ) -> list[CustomerRFMProfile]:
        now = reference_now or _utcnow()
        if not actors_data:
            return []

        # Parse raw metrics per actor
        parsed_records: list[dict[str, Any]] = []
        for a in actors_data:
            aid = str(a.get("actor_id") or a.get("id") or "anon")
            last_seen = _parse_datetime(a.get("last_seen_at") or a.get("last_event_at") or now)
            recency = max(0.0, (now - last_seen).total_seconds() / 86400.0)
            frequency = int(a.get("frequency") or a.get("event_count") or 1)
            monetary = float(a.get("monetary_value") or a.get("total_spend") or 0.0)
            traits = dict(a.get("traits") or {})

            parsed_records.append(
                {
                    "actor_id": aid,
                    "recency": recency,
                    "frequency": frequency,
                    "monetary": monetary,
                    "traits": traits,
                }
            )

        # Compute Quintiles or Thresholds for R, F, M
        # Recency (lower is better: 1 = ancient, 5 = fresh)
        # Frequency (higher is better: 1 = single touch, 5 = highly active)
        # Monetary (higher is better: 1 = zero/low, 5 = top spender)
        results: list[CustomerRFMProfile] = []
        for r in parsed_records:
            rec = r["recency"]
            freq = r["frequency"]
            mon = r["monetary"]

            # R Score
            if rec <= 2.0:
                r_score = 5
            elif rec <= 7.0:
                r_score = 4
            elif rec <= 14.0:
                r_score = 3
            elif rec <= 30.0:
                r_score = 2
            else:
                r_score = 1

            # F Score
            if freq >= 50:
                f_score = 5
            elif freq >= 20:
                f_score = 4
            elif freq >= 8:
                f_score = 3
            elif freq >= 2:
                f_score = 2
            else:
                f_score = 1

            # M Score
            if mon >= 5000.0:
                m_score = 5
            elif mon >= 1000.0:
                m_score = 4
            elif mon >= 250.0:
                m_score = 3
            elif mon > 0.0:
                m_score = 2
            else:
                m_score = 1

            composite = round((r_score * 0.40) + (f_score * 0.30) + (m_score * 0.30), 2)

            # Segment Tier Classification
            if r_score >= 4 and f_score >= 4 and m_score >= 4:
                tier = "CHAMPION"
            elif r_score >= 3 and f_score >= 3:
                tier = "LOYAL_CUSTOMER"
            elif r_score >= 4 and f_score <= 2:
                tier = "POTENTIAL_LOYALIST"
            elif r_score <= 2 and (f_score >= 3 or m_score >= 3):
                tier = "AT_RISK"
            elif r_score == 1 and m_score >= 4:
                tier = "CANT_LOSE_THEM"
            elif r_score <= 2 and f_score <= 2:
                tier = "HIBERNATING"
            elif r_score == 1:
                tier = "LOST"
            else:
                tier = "PROMISES"

            results.append(
                CustomerRFMProfile(
                    actor_id=r["actor_id"],
                    recency_days=round(rec, 1),
                    frequency_events=freq,
                    monetary_value=round(mon, 2),
                    r_score=r_score,
                    f_score=f_score,
                    m_score=m_score,
                    composite_rfm=composite,
                    tier=tier,
                    traits=r["traits"],
                )
            )

        return results

    def predict_churn(
        self,
        actor_id: str,
        events: list[dict[str, Any]],
        profile_traits: dict[str, Any] | None = None,
        reference_now: datetime | None = None,
    ) -> ChurnRiskAssessment:
        now = reference_now or _utcnow()
        profile_traits = profile_traits or {}

        if not events:
            return ChurnRiskAssessment(
                actor_id=actor_id,
                churn_probability=0.85,
                risk_level="HIGH",
                hazard_score=0.85,
                risk_factors=["zero_events_recorded_in_history"],
                mitigation_recommendation="Send re-engagement email campaign with special incentive.",
            )

        # 1. Calculate Inactivity Gap
        timestamps = [_parse_datetime(e.get("occurred_at")) for e in events]
        last_event_time = max(timestamps)
        days_inactive = max(0.0, (now - last_event_time).total_seconds() / 86400.0)

        # Base exponential decay hazard: 1 - exp(-lambda * days) with lambda = 0.065
        base_hazard = 1.0 - math.exp(-0.065 * days_inactive)

        # 2. Extract Behavioral Negative Signals
        risk_factors: list[str] = []
        hazard_modifier = 0.0

        if days_inactive > 30:
            risk_factors.append(f"prolonged_inactivity_{round(days_inactive)}_days")
            hazard_modifier += 0.35
        elif days_inactive > 14:
            risk_factors.append(f"inactivity_{round(days_inactive)}_days")
            hazard_modifier += 0.20

        # Rage clicks
        rage_clicks = sum(1 for e in events if "rage" in str(e.get("type", "")).lower())
        if rage_clicks > 0:
            risk_factors.append(f"rage_clicks_detected_count_{rage_clicks}")
            hazard_modifier += min(rage_clicks * 0.12, 0.30)

        # Error events
        error_events = sum(1 for e in events if "error" in str(e.get("type", "")).lower() or e.get("data", {}).get("error"))
        if error_events >= 2:
            risk_factors.append(f"encountered_{error_events}_friction_errors")
            hazard_modifier += min(error_events * 0.08, 0.24)

        # Abandoned checkout or cancel intentions
        checkout_cancels = sum(
            1
            for e in events
            if any(
                term in str(e.get("type", "")).lower()
                for term in ["cancel", "unsubscribe", "downgrade", "checkout.abort", "payment_failed"]
            )
        )
        if checkout_cancels > 0:
            risk_factors.append(f"cancellation_or_downgrade_intent_{checkout_cancels}")
            hazard_modifier += 0.30

        # Positive Buffers (mitigating factors)
        monetary_value = float(profile_traits.get("total_spend", 0.0) or profile_traits.get("monetary_value", 0.0))
        if monetary_value >= 1000.0:
            hazard_modifier -= 0.15
            risk_factors.append("high_value_customer_buffer")

        if len(events) >= 40:
            hazard_modifier -= 0.10
            risk_factors.append("deep_historical_usage_buffer")

        # Total Churn Probability
        raw_prob = base_hazard + hazard_modifier
        churn_prob = round(max(0.01, min(0.99, raw_prob)), 3)

        if churn_prob >= 0.75:
            risk_level = "CRITICAL"
            mitigation = "Immediate CSM executive outreach; offer concierge troubleshooting and retention incentive."
        elif churn_prob >= 0.50:
            risk_level = "HIGH"
            mitigation = "Trigger automated retention playbook: send customized survey and product usage tips."
        elif churn_prob >= 0.25:
            risk_level = "MODERATE"
            mitigation = "Monitor engagement velocity; present relevant feature discovery banners in-app."
        else:
            risk_level = "LOW"
            mitigation = "Customer is in good standing. Continue standard product communication."

        return ChurnRiskAssessment(
            actor_id=actor_id,
            churn_probability=churn_prob,
            risk_level=risk_level,
            hazard_score=round(raw_prob, 3),
            risk_factors=risk_factors,
            mitigation_recommendation=mitigation,
        )

    def classify_lead_intent_acceleration(
        self,
        events: list[dict[str, Any]],
        window_hours: float = 48.0,
        reference_now: datetime | None = None,
    ) -> LeadIntentAcceleration:
        now = reference_now or _utcnow()
        if not events:
            return LeadIntentAcceleration(
                actor_id="anonymous",
                acceleration_factor=0.0,
                velocity_events_per_hour=0.0,
                total_intent_touches=0,
                priority_routing="P2_AUTOMATED_NURTURE",
                recommended_play="Enroll in top-of-funnel educational drip sequence.",
            )

        actor_id = str(events[0].get("actor_id") or "anonymous")
        high_intent_terms = ["pricing", "demo", "enterprise", "security", "contact_sales", "contract", "quote"]

        # Filter events in the acceleration window
        window_events = []
        for e in events:
            dt = _parse_datetime(e.get("occurred_at"))
            diff_hours = (now - dt).total_seconds() / 3600.0
            if diff_hours <= window_hours:
                window_events.append((e, diff_hours))

        # Count intent touches
        intent_touches = 0
        for e, _ in window_events:
            etype = str(e.get("type", "")).lower()
            path = str(e.get("data", {}).get("path", "")).lower()
            if any(term in etype or term in path for term in high_intent_terms):
                intent_touches += 1

        velocity_per_hour = round(len(window_events) / max(window_hours, 1.0), 3)
        acceleration = round((intent_touches * 2.5) + (velocity_per_hour * 5.0), 2)

        if acceleration >= 10.0 or intent_touches >= 3:
            routing = "P0_ENTERPRISE_FAST_TRACK"
            play = "Instant AE Slack alert; fast-track calendar invite with pre-filled company dossier."
        elif acceleration >= 4.0 or intent_touches >= 1:
            routing = "P1_AE_HANDOFF"
            play = "Route lead to SDR for personalized email outreach within 2 business hours."
        else:
            routing = "P2_AUTOMATED_NURTURE"
            play = "Enroll in behavioral nurture track with customer case studies."

        return LeadIntentAcceleration(
            actor_id=actor_id,
            acceleration_factor=acceleration,
            velocity_events_per_hour=velocity_per_hour,
            total_intent_touches=intent_touches,
            priority_routing=routing,
            recommended_play=play,
        )
