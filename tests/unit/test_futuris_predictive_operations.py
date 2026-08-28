import pytest
import os
import sys
from fastapi.testclient import TestClient

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

from nexus_api.main import app
from nexus_integrations import FuturisClient
from nexus_intelligence import PredictionInformedPersonalization
from nexus_workflow_engine import CapacityPlanningWorkflow


@pytest.mark.asyncio
async def test_futuris_client_forecasting():
    client = FuturisClient()

    # 1. Traffic Forecast
    traffic = await client.predict_traffic("site_main", horizon_hours=24)
    assert traffic.target_site_id == "site_main"
    assert traffic.peak_predicted_rps > 0
    assert len(traffic.data_points) == 24

    # 2. Conversion Trend Forecast
    trend_drop = await client.predict_conversion_trends("checkout_drop_segment")
    assert trend_drop.trajectory == "dropping"
    assert trend_drop.drop_probability > 0.70
    assert trend_drop.bottleneck_step is not None

    trend_up = await client.predict_conversion_trends("standard_leads")
    assert trend_up.trajectory == "upward"

    # 3. Churn Risk Forecast
    churn_segs = await client.predict_churn_risk("default")
    assert len(churn_segs) >= 2
    assert churn_segs[0].predicted_churn_rate_pct > 0


@pytest.mark.asyncio
async def test_predictive_personalization_action_generation():
    engine = PredictionInformedPersonalization()

    # Case 1: High drop probability triggers VIP offer adjustment
    action_drop = await engine.evaluate_segment_personalization("checkout_segment")
    assert action_drop is not None
    assert action_drop.action_type == "offer_adjustment"
    assert "Guided Architecture Review" in action_drop.variant_details["cta_text"]

    # Case 2: Upward momentum triggers high-intent accelerator
    action_up = await engine.evaluate_segment_personalization("standard_leads")
    assert action_up is not None
    assert action_up.action_type == "landing_page_variant"
    assert action_up.variant_details["variant"] == "high_intent_accelerator"


@pytest.mark.asyncio
async def test_capacity_planning_workflow_auto_scaling():
    workflow = CapacityPlanningWorkflow()
    plan = await workflow.evaluate_capacity("site_main")

    assert plan.site_id == "site_main"
    if plan.exceeds_capacity:
        assert plan.auto_scaling_replica_target == 7
        assert len(plan.cache_warming_targets) > 0
        assert plan.friday_notification_dispatched is True


def test_futuris_predictive_api_endpoints():
    client = TestClient(app)

    # 1. GET /v1/predictive/traffic-forecast
    res_trf = client.get("/v1/predictive/traffic-forecast?site_id=site_main")
    assert res_trf.status_code == 200
    assert "peak_predicted_rps" in res_trf.json()

    # 2. GET /v1/predictive/capacity-plan
    res_cap = client.get("/v1/predictive/capacity-plan?site_id=site_main")
    assert res_cap.status_code == 200
    assert "auto_scaling_replica_target" in res_cap.json()

    # 3. GET /v1/predictive/conversion-trends
    res_cvr = client.get("/v1/predictive/conversion-trends?segment_id=checkout_segment")
    assert res_cvr.status_code == 200
    assert "drop_probability" in res_cvr.json()

    # 4. GET /v1/predictive/churn-risk
    res_chn = client.get("/v1/predictive/churn-risk?tenant_id=default")
    assert res_chn.status_code == 200
    assert len(res_chn.json()) >= 2
