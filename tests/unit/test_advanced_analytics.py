import pytest
import os
import sys
from datetime import datetime, timedelta

for p in [
    "packages/core/src",
    "packages/event_schema/src",
    "packages/agents/src",
    "packages/ai_universe_adapter/src",
    "packages/tool_runtime/src",
    "packages/integrations/src",
    "packages/policy_engine/src",
    "packages/workflow_engine/src",
    "packages/identity/src",
    "packages/analytics/src",
    "packages/intelligence/src",
    "packages/memory/src",
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(p))

from nexus_analytics import AdvancedAnalyticsEngine


def test_natural_language_query_intent_parsing():
    engine = AdvancedAnalyticsEngine()

    res = engine.parse_natural_language_query("How many visitors from Google converted this week?")
    assert res.parsed_intent["metric"] == "conversion_rate"
    assert res.parsed_intent["dimension"] == "source"
    assert res.parsed_intent["time_range"] == "this_week"
    assert "SELECT" in res.sql_translation
    assert len(res.data) > 0


def test_multi_touch_revenue_attribution_models():
    engine = AdvancedAnalyticsEngine()

    touchpoints = [
        {"channel": "google_ads", "occurred_at": datetime.utcnow() - timedelta(days=14)},
        {"channel": "linkedin", "occurred_at": datetime.utcnow() - timedelta(days=7)},
        {"channel": "direct", "occurred_at": datetime.utcnow()}
    ]

    total_revenue = 1000.0

    # 1. First touch
    first_res = engine.calculate_revenue_attribution(touchpoints, total_revenue, model="first_touch")
    assert first_res["google_ads"] == 1000.0

    # 2. Last touch
    last_res = engine.calculate_revenue_attribution(touchpoints, total_revenue, model="last_touch")
    assert last_res["direct"] == 1000.0

    # 3. Linear
    linear_res = engine.calculate_revenue_attribution(touchpoints, total_revenue, model="linear")
    assert round(linear_res["google_ads"] + linear_res["linkedin"] + linear_res["direct"]) == 1000.0

    # 4. Time decay
    td_res = engine.calculate_revenue_attribution(touchpoints, total_revenue, model="time_decay")
    assert td_res["direct"] > td_res["google_ads"]  # Most recent gets highest weight
