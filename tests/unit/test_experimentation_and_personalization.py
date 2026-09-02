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

from cortex_analytics import (
    ExperimentationEngine,
    ExperimentDefinition,
    ExperimentVariant,
    ExperimentStatus
)


def test_deterministic_sticky_variant_assignment():
    engine = ExperimentationEngine()
    exp = ExperimentDefinition(
        id="exp_test_1",
        name="Test Exp",
        hypothesis="Testing sticky hashing",
        variants=[
            ExperimentVariant(id="var_a", name="Control", weight=0.5),
            ExperimentVariant(id="var_b", name="Variant B", weight=0.5),
        ]
    )

    # Assert deterministic repeatability for same visitor ID
    var1 = engine.assign_variant("visitor_alpha_999", exp)
    var2 = engine.assign_variant("visitor_alpha_999", exp)
    assert var1.id == var2.id


def test_two_proportion_z_test_statistical_significance():
    engine = ExperimentationEngine()

    control = ExperimentVariant(id="c", name="Control", visitors_count=1000, conversions_count=50)      # 5.0% CR
    treatment = ExperimentVariant(id="t", name="Treatment", visitors_count=1000, conversions_count=100) # 10.0% CR

    res = engine.calculate_significance(control, treatment)
    assert res["statistically_significant"] is True
    assert res["p_value"] < 0.05
    assert res["z_score"] > 1.96
    assert res["relative_lift_pct"] == 100.0


def test_personalization_rule_matching():
    engine = ExperimentationEngine()

    rules = [
        {"segment": "enterprise", "path": "/pricing", "experience_payload": {"annual_discount": 0.20}},
        {"device": "mobile", "path": "/home", "experience_payload": {"sticky_cta": True}}
    ]

    match_ent = engine.evaluate_personalization_rules({"segment": "enterprise"}, "/pricing", rules)
    assert match_ent == {"annual_discount": 0.20}

    match_none = engine.evaluate_personalization_rules({"segment": "smb"}, "/pricing", rules)
    assert match_none is None
