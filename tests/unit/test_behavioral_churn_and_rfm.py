"""
Unit tests for Behavioral Churn Prediction and RFM Segmentation.
"""

from datetime import UTC, datetime, timedelta
import pytest
from cortex_intelligence.behavioral_churn import (
    BehavioralChurnClassifier,
    CustomerRFMProfile,
    ChurnRiskAssessment,
    LeadIntentAcceleration,
)


def _dt(offset_days: float = 0.0) -> str:
    now = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)
    return (now - timedelta(days=offset_days)).isoformat()


def test_rfm_empty():
    classifier = BehavioralChurnClassifier()
    profiles = classifier.compute_rfm_scores([])
    assert profiles == []


def test_rfm_tier_classification():
    classifier = BehavioralChurnClassifier()
    now = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)

    actors_data = [
        # Champion: seen 1 day ago, 60 events, $6000 spend
        {
            "actor_id": "champ",
            "last_seen_at": _dt(1.0),
            "frequency": 60,
            "monetary_value": 6000.0,
        },
        # At Risk: seen 20 days ago, 30 events, $1500 spend
        {
            "actor_id": "at_risk",
            "last_seen_at": _dt(20.0),
            "frequency": 30,
            "monetary_value": 1500.0,
        },
        # Lost: seen 45 days ago, 1 event, $0 spend
        {
            "actor_id": "lost",
            "last_seen_at": _dt(45.0),
            "frequency": 1,
            "monetary_value": 0.0,
        },
    ]

    profiles = classifier.compute_rfm_scores(actors_data, reference_now=now)
    assert len(profiles) == 3

    p_champ = next(p for p in profiles if p.actor_id == "champ")
    assert p_champ.tier == "CHAMPION"
    assert p_champ.r_score == 5
    assert p_champ.f_score == 5
    assert p_champ.m_score == 5

    p_risk = next(p for p in profiles if p.actor_id == "at_risk")
    assert p_risk.tier in ("AT_RISK", "HIBERNATING")
    assert p_risk.r_score <= 2

    p_lost = next(p for p in profiles if p.actor_id == "lost")
    assert p_lost.tier in ("LOST", "HIBERNATING")
    assert p_lost.r_score == 1


def test_predict_churn_empty_events():
    classifier = BehavioralChurnClassifier()
    assessment = classifier.predict_churn("u_empty", [])
    assert assessment.churn_probability >= 0.80
    assert assessment.risk_level in ("HIGH", "CRITICAL")
    assert "zero_events_recorded_in_history" in assessment.risk_factors


def test_predict_churn_active_healthy_user():
    classifier = BehavioralChurnClassifier()
    now = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)
    events = [
        {"type": "page_view", "occurred_at": (now - timedelta(hours=2)).isoformat()},
        {"type": "dashboard.view", "occurred_at": (now - timedelta(hours=1)).isoformat()},
    ] * 25
    assessment = classifier.predict_churn("u_active", events, profile_traits={"total_spend": 2500.0}, reference_now=now)
    assert assessment.churn_probability < 0.25
    assert assessment.risk_level == "LOW"
    assert "deep_historical_usage_buffer" in assessment.risk_factors


def test_predict_churn_high_risk_signals():
    classifier = BehavioralChurnClassifier()
    now = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)
    # User was last active 25 days ago, experienced rage clicks and downgrade intent
    events = [
        {"type": "rage_click", "occurred_at": (now - timedelta(days=25)).isoformat()},
        {"type": "error", "data": {"error": "checkout_failed"}, "occurred_at": (now - timedelta(days=25)).isoformat()},
        {"type": "account.downgrade", "occurred_at": (now - timedelta(days=25)).isoformat()},
    ]
    assessment = classifier.predict_churn("u_risk", events, reference_now=now)
    assert assessment.churn_probability >= 0.70
    assert assessment.risk_level in ("HIGH", "CRITICAL")
    assert any("rage_clicks" in f for f in assessment.risk_factors)
    assert any("downgrade" in f for f in assessment.risk_factors)


def test_lead_intent_acceleration():
    classifier = BehavioralChurnClassifier()
    now = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)
    # 4 pricing/demo touches within the last 12 hours
    events = [
        {"actor_id": "lead_fast", "type": "page_view", "data": {"path": "/pricing"}, "occurred_at": (now - timedelta(hours=10)).isoformat()},
        {"actor_id": "lead_fast", "type": "page_view", "data": {"path": "/enterprise"}, "occurred_at": (now - timedelta(hours=8)).isoformat()},
        {"actor_id": "lead_fast", "type": "form_submit", "data": {"path": "/contact_sales"}, "occurred_at": (now - timedelta(hours=4)).isoformat()},
        {"actor_id": "lead_fast", "type": "page_view", "data": {"path": "/security"}, "occurred_at": (now - timedelta(hours=1)).isoformat()},
    ]
    acc = classifier.classify_lead_intent_acceleration(events, window_hours=24.0, reference_now=now)
    assert acc.actor_id == "lead_fast"
    assert acc.total_intent_touches == 4
    assert acc.priority_routing == "P0_ENTERPRISE_FAST_TRACK"
    assert "AE Slack alert" in acc.recommended_play
