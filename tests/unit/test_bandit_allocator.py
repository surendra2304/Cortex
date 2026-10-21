"""
Unit tests for Multi-Armed Bandit (MAB) & Contextual Thompson Sampling Engine.
"""

import pytest
from cortex_intelligence.bandit_allocator import (
    AllocationDecision,
    BanditAlgorithm,
    BanditExperiment,
    MultiArmedBanditEngine,
)


@pytest.fixture
def bandit_engine() -> MultiArmedBanditEngine:
    return MultiArmedBanditEngine()


def test_create_bandit_experiment(bandit_engine: MultiArmedBanditEngine) -> None:
    arm_configs = [
        {"arm_id": "arm_control", "label": "Control Button", "alpha": 1.0, "beta": 1.0},
        {"arm_id": "arm_variant_a", "label": "Variant A - Orange", "alpha": 1.0, "beta": 1.0},
        {"arm_id": "arm_variant_b", "label": "Variant B - Green", "alpha": 1.0, "beta": 1.0},
    ]
    exp = bandit_engine.create_experiment(
        tenant_id="tenant-alpha",
        experiment_id="cta-color-test",
        name="Homepage CTA Color Optimization",
        arm_configs=arm_configs,
        algorithm=BanditAlgorithm.THOMPSON_SAMPLING,
    )

    assert exp.tenant_id == "tenant-alpha"
    assert exp.experiment_id == "cta-color-test"
    assert len(exp.arms) == 3
    assert exp.status == "RUNNING"
    assert exp.arms["arm_control"].trials == 0
    assert exp.arms["arm_control"].win_probability > 0.0


def test_thompson_sampling_selection_and_rewards(bandit_engine: MultiArmedBanditEngine) -> None:
    arm_configs = [
        {"arm_id": "arm_1", "label": "Headline 1"},
        {"arm_id": "arm_2", "label": "Headline 2"},
    ]
    exp = bandit_engine.create_experiment(
        tenant_id="tenant-alpha",
        experiment_id="headline-opt",
        name="Headline Optimization",
        arm_configs=arm_configs,
        algorithm=BanditAlgorithm.THOMPSON_SAMPLING,
    )

    decision = bandit_engine.select_arm("tenant-alpha", "headline-opt")
    assert isinstance(decision, AllocationDecision)
    assert decision.arm_id in ["arm_1", "arm_2"]
    assert decision.algorithm_used == BanditAlgorithm.THOMPSON_SAMPLING

    # Record rewards for arm_2 repeatedly to simulate high conversion
    for _ in range(30):
        bandit_engine.record_reward("tenant-alpha", "headline-opt", "arm_2", converted=True)
    for _ in range(30):
        bandit_engine.record_reward("tenant-alpha", "headline-opt", "arm_1", converted=False)

    updated_exp = bandit_engine.get_experiment("tenant-alpha", "headline-opt")
    assert updated_exp is not None
    assert updated_exp.arms["arm_2"].conversions == 30
    assert updated_exp.arms["arm_1"].conversions == 0
    assert updated_exp.arms["arm_2"].win_probability > 0.90


def test_ucb1_selection_and_bonus(bandit_engine: MultiArmedBanditEngine) -> None:
    arm_configs = [
        {"arm_id": "v1", "label": "Version 1"},
        {"arm_id": "v2", "label": "Version 2"},
    ]
    bandit_engine.create_experiment(
        tenant_id="tenant-beta",
        experiment_id="pricing-tiers",
        name="Pricing Tier Test",
        arm_configs=arm_configs,
        algorithm=BanditAlgorithm.UCB1,
        exploration_constant=1.5,
    )

    # Initial selection visits unvisited arms
    dec1 = bandit_engine.select_arm("tenant-beta", "pricing-tiers")
    bandit_engine.record_reward("tenant-beta", "pricing-tiers", dec1.arm_id, converted=False)

    dec2 = bandit_engine.select_arm("tenant-beta", "pricing-tiers")
    assert dec2.arm_id != dec1.arm_id  # UCB explores unvisited arm with infinite score


def test_contextual_filtering_and_fallback(bandit_engine: MultiArmedBanditEngine) -> None:
    arm_configs = [
        {
            "arm_id": "mobile_arm",
            "label": "Mobile Hero Layout",
            "context_rules": {"device": ["mobile", "tablet"]},
        },
        {
            "arm_id": "desktop_arm",
            "label": "Desktop Hero Layout",
            "context_rules": {"device": ["desktop"]},
        },
    ]
    bandit_engine.create_experiment(
        tenant_id="tenant-gamma",
        experiment_id="hero-layout",
        name="Hero Layout by Device",
        arm_configs=arm_configs,
    )

    # Context: mobile
    dec_mob = bandit_engine.select_arm("tenant-gamma", "hero-layout", context={"device": "mobile"})
    assert dec_mob.arm_id == "mobile_arm"

    # Context: desktop
    dec_desk = bandit_engine.select_arm("tenant-gamma", "hero-layout", context={"device": "desktop"})
    assert dec_desk.arm_id == "desktop_arm"

    # Context: unknown (fallback to any arm)
    dec_other = bandit_engine.select_arm("tenant-gamma", "hero-layout", context={"device": "smart_tv"})
    assert dec_other.arm_id in ["mobile_arm", "desktop_arm"]


def test_automated_early_stopping_promotes_winner(bandit_engine: MultiArmedBanditEngine) -> None:
    arm_configs = [
        {"arm_id": "underperforming", "label": "Arm Bad"},
        {"arm_id": "winner_arm", "label": "Arm Great"},
    ]
    bandit_engine.create_experiment(
        tenant_id="tenant-delta",
        experiment_id="discount-offer",
        name="Discount Promo Test",
        arm_configs=arm_configs,
        min_samples_for_decision=50,
        confidence_threshold=0.95,
    )

    for _ in range(60):
        bandit_engine.record_reward("tenant-delta", "discount-offer", "winner_arm", converted=True)
    for _ in range(60):
        bandit_engine.record_reward("tenant-delta", "discount-offer", "underperforming", converted=False)

    exp = bandit_engine.get_experiment("tenant-delta", "discount-offer")
    assert exp is not None
    assert exp.status == "PROMOTED"
    assert exp.winning_arm == "winner_arm"

    # Once promoted, subsequent selections always return the winning arm
    dec = bandit_engine.select_arm("tenant-delta", "discount-offer")
    assert dec.arm_id == "winner_arm"
    assert dec.metadata.get("status") == "PROMOTED_WINNER"


def test_tenant_isolation_bandit(bandit_engine: MultiArmedBanditEngine) -> None:
    bandit_engine.create_experiment(
        tenant_id="tenant-1",
        experiment_id="exp-1",
        name="Exp 1",
        arm_configs=[{"arm_id": "a1", "label": "A1"}],
    )

    assert bandit_engine.get_experiment("tenant-1", "exp-1") is not None
    assert bandit_engine.get_experiment("tenant-2", "exp-1") is None

    with pytest.raises(KeyError):
        bandit_engine.select_arm("tenant-2", "exp-1")

    with pytest.raises(KeyError):
        bandit_engine.record_reward("tenant-2", "exp-1", "a1", converted=True)
