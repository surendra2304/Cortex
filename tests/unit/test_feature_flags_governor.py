"""
Unit tests for Feature Flags Governor and Deterministic Percentage Rollouts.
"""

import pytest
from cortex_core.feature_flags import (
    FeatureFlag,
    FeatureFlagEngine,
    TargetRule,
)


def test_flag_crud():
    engine = FeatureFlagEngine()
    flag = FeatureFlag(
        key="new_checkout_flow",
        tenant_id="tenant_acme",
        enabled=True,
        rollout_percentage=100.0,
        description="V2 Checkout",
    )
    engine.set_flag(flag)

    fetched = engine.get_flag("new_checkout_flow", tenant_id="tenant_acme")
    assert fetched is not None
    assert fetched.key == "new_checkout_flow"
    assert fetched.enabled is True

    # List
    flags = engine.list_flags("tenant_acme")
    assert len(flags) == 1

    # Delete
    deleted = engine.delete_flag("new_checkout_flow", tenant_id="tenant_acme")
    assert deleted is True
    assert engine.get_flag("new_checkout_flow", tenant_id="tenant_acme") is None


def test_flag_allow_and_block_lists():
    engine = FeatureFlagEngine()
    flag = FeatureFlag(
        key="beta_feature",
        tenant_id="tenant_acme",
        enabled=True,
        rollout_percentage=0.0,  # 0% rollout
        allowed_actors=["vip_user"],
        blocked_actors=["banned_user"],
    )
    engine.set_flag(flag)

    # Allowed actor gets True despite 0% rollout
    assert engine.evaluate("beta_feature", "vip_user", tenant_id="tenant_acme") is True

    # Blocked actor gets False
    assert engine.evaluate("beta_feature", "banned_user", tenant_id="tenant_acme") is False

    # Standard actor gets False due to 0% rollout
    assert engine.evaluate("beta_feature", "regular_user", tenant_id="tenant_acme") is False


def test_flag_rule_targeting():
    engine = FeatureFlagEngine()
    flag = FeatureFlag(
        key="enterprise_portal",
        tenant_id="tenant_acme",
        enabled=True,
        rollout_percentage=100.0,
        target_rules=[
            TargetRule(property="tier", operator="in", values=["CHAMPION", "LOYAL_CUSTOMER"]),
            TargetRule(property="country", operator="eq", values=["US"]),
            TargetRule(property="spend", operator="gte", values=[1000.0]),
        ],
    )
    engine.set_flag(flag)

    # Matching context
    matching_ctx = {"tier": "CHAMPION", "country": "US", "spend": 1500.0}
    assert engine.evaluate("enterprise_portal", "user_1", context=matching_ctx, tenant_id="tenant_acme") is True

    # Non-matching tier
    bad_tier_ctx = {"tier": "LOST", "country": "US", "spend": 1500.0}
    assert engine.evaluate("enterprise_portal", "user_1", context=bad_tier_ctx, tenant_id="tenant_acme") is False

    # Low spend
    low_spend_ctx = {"tier": "CHAMPION", "country": "US", "spend": 200.0}
    assert engine.evaluate("enterprise_portal", "user_1", context=low_spend_ctx, tenant_id="tenant_acme") is False


def test_flag_deterministic_percentage_rollout():
    engine = FeatureFlagEngine()
    flag = FeatureFlag(
        key="experiment_dark_mode",
        tenant_id="tenant_acme",
        enabled=True,
        rollout_percentage=50.0,
    )
    engine.set_flag(flag)

    # Evaluation for the same actor must be 100% deterministic
    res_1 = engine.evaluate("experiment_dark_mode", "actor_alpha", tenant_id="tenant_acme")
    for _ in range(10):
        assert engine.evaluate("experiment_dark_mode", "actor_alpha", tenant_id="tenant_acme") == res_1

    # Over 200 actors, ~50% should be enabled
    actors = [f"actor_{i}" for i in range(200)]
    enabled_count = sum(1 for a in actors if engine.evaluate("experiment_dark_mode", a, tenant_id="tenant_acme"))

    # Between 35% and 65% for 50% rollout with 200 samples
    assert 70 <= enabled_count <= 130


def test_flag_tenant_isolation():
    engine = FeatureFlagEngine()
    flag = FeatureFlag(
        key="exclusive_flag",
        tenant_id="tenant_alpha",
        enabled=True,
        rollout_percentage=100.0,
    )
    engine.set_flag(flag)

    # Enabled for tenant_alpha
    assert engine.evaluate("exclusive_flag", "user_1", tenant_id="tenant_alpha") is True

    # Missing for tenant_beta
    assert engine.evaluate("exclusive_flag", "user_1", tenant_id="tenant_beta") is False
