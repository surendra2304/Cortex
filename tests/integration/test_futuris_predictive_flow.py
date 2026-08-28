import pytest
import os
import sys

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

from nexus_integrations import FuturisClient
from nexus_workflow_engine import CapacityPlanningWorkflow
from nexus_intelligence import PredictionInformedPersonalization


@pytest.mark.asyncio
async def test_full_futuris_predictive_flow_e2e():
    """
    End-to-End Futuris Predictive Flow:
    Traffic forecast -> Capacity evaluation -> Auto-scale & cache warming -> Conversion prediction -> Personalization adjustment.
    """
    futuris = FuturisClient()
    capacity_wf = CapacityPlanningWorkflow(futuris_client=futuris)
    pred_pers = PredictionInformedPersonalization(futuris_client=futuris)

    # 1. Traffic Forecast & Capacity Auto-scale
    cap_plan = await capacity_wf.evaluate_capacity("site_main")
    assert cap_plan.site_id == "site_main"
    assert cap_plan.peak_predicted_rps > 0
    if cap_plan.exceeds_capacity:
        assert cap_plan.auto_scaling_replica_target == 7
        assert "/pricing" in cap_plan.cache_warming_targets

    # 2. Conversion Drop Forecast & VIP Personalization Adjustment
    pers_action = await pred_pers.evaluate_segment_personalization("checkout_segment")
    assert pers_action is not None
    assert pers_action.action_type == "offer_adjustment"
    assert "Guided Architecture Review" in pers_action.variant_details["cta_text"]
