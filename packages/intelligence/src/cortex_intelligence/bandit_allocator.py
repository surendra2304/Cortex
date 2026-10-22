"""
Multi-Armed Bandit (MAB) & Contextual Thompson Sampling Engine for Cortex.

Provides production-grade multi-armed bandit allocation:
- Thompson Sampling with Beta-Bernoulli conjugate priors and non-stationary decay
- Upper Confidence Bound (UCB1) exploration-exploitation scoring
- Contextual segment filtering (device, geo, channel targeting)
- Bayesian posterior win-probability estimation via Monte Carlo draws
- Automated dominant-arm early stopping detection and cumulative regret tracking
"""

from __future__ import annotations

import hashlib
import math
import random
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class BanditAlgorithm(str, Enum):
    THOMPSON_SAMPLING = "thompson_sampling"
    UCB1 = "ucb1"
    EPSILON_GREEDY = "epsilon_greedy"


class ArmMetrics(BaseModel):
    arm_id: str
    label: str
    trials: int = 0
    conversions: int = 0
    alpha: float = 1.0  # Beta prior success
    beta: float = 1.0   # Beta prior failure
    conversion_rate: float = 0.0
    ucb_score: float = 0.0
    win_probability: float = 0.0  # Bayesian P(arm is optimal)
    context_rules: dict[str, list[str]] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: str = Field(default_factory=lambda: _utcnow().isoformat())


class BanditExperiment(BaseModel):
    tenant_id: str
    experiment_id: str
    name: str
    algorithm: BanditAlgorithm = BanditAlgorithm.THOMPSON_SAMPLING
    arms: dict[str, ArmMetrics] = Field(default_factory=dict)
    decay_factor: float = Field(default=0.999, ge=0.5, le=1.0)  # Non-stationary sliding discount
    exploration_constant: float = Field(default=1.0, ge=0.01, le=10.0)  # UCB1 c factor
    epsilon: float = Field(default=0.1, ge=0.0, le=1.0)
    min_samples_for_decision: int = 50
    confidence_threshold: float = 0.95
    status: str = "RUNNING"  # RUNNING, PROMOTED, PAUSED
    winning_arm: str | None = None
    created_at: str = Field(default_factory=lambda: _utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: _utcnow().isoformat())


class AllocationDecision(BaseModel):
    tenant_id: str
    experiment_id: str
    arm_id: str
    label: str
    algorithm_used: BanditAlgorithm
    context_matched: bool = True
    exploration: bool = False
    decision_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    allocated_at: str = Field(default_factory=lambda: _utcnow().isoformat())


class MultiArmedBanditEngine:
    """
    Tenant-isolated Multi-Armed Bandit allocator for continuous optimization.
    """

    def __init__(self) -> None:
        self._experiments: dict[str, dict[str, BanditExperiment]] = {}  # {tenant_id: {experiment_id: BanditExperiment}}

    def create_experiment(
        self,
        tenant_id: str,
        experiment_id: str,
        name: str,
        arm_configs: list[dict[str, Any]],
        algorithm: BanditAlgorithm = BanditAlgorithm.THOMPSON_SAMPLING,
        decay_factor: float = 0.999,
        exploration_constant: float = 1.0,
        epsilon: float = 0.1,
        min_samples_for_decision: int = 50,
        confidence_threshold: float = 0.95,
    ) -> BanditExperiment:
        """Register or reset a bandit experiment for a tenant."""
        if not arm_configs:
            raise ValueError("Bandit experiment must have at least one arm configuration")

        arms: dict[str, ArmMetrics] = {}
        for cfg in arm_configs:
            arm_id = cfg["arm_id"]
            arms[arm_id] = ArmMetrics(
                arm_id=arm_id,
                label=cfg.get("label", arm_id),
                alpha=float(cfg.get("alpha", 1.0)),
                beta=float(cfg.get("beta", 1.0)),
                context_rules=cfg.get("context_rules", {}),
                metadata=cfg.get("metadata", {}),
            )

        exp = BanditExperiment(
            tenant_id=tenant_id,
            experiment_id=experiment_id,
            name=name,
            algorithm=algorithm,
            arms=arms,
            decay_factor=decay_factor,
            exploration_constant=exploration_constant,
            epsilon=epsilon,
            min_samples_for_decision=min_samples_for_decision,
            confidence_threshold=confidence_threshold,
        )

        if tenant_id not in self._experiments:
            self._experiments[tenant_id] = {}
        self._experiments[tenant_id][experiment_id] = exp
        self._recompute_stats(exp)
        return exp

    def get_experiment(self, tenant_id: str, experiment_id: str) -> BanditExperiment | None:
        return self._experiments.get(tenant_id, {}).get(experiment_id)

    def list_experiments(self, tenant_id: str) -> list[BanditExperiment]:
        return list(self._experiments.get(tenant_id, {}).values())

    def select_arm(
        self,
        tenant_id: str,
        experiment_id: str,
        context: dict[str, Any] | None = None,
        sticky_actor_id: str | None = None,
    ) -> AllocationDecision:
        """
        Select the optimal arm using the configured bandit algorithm.
        Supports contextual qualification and sticky deterministic fallback.
        """
        exp = self.get_experiment(tenant_id, experiment_id)
        if not exp:
            raise KeyError(f"Bandit experiment '{experiment_id}' not found for tenant '{tenant_id}'")

        if exp.status == "PROMOTED" and exp.winning_arm and exp.winning_arm in exp.arms:
            winner = exp.arms[exp.winning_arm]
            return AllocationDecision(
                tenant_id=tenant_id,
                experiment_id=experiment_id,
                arm_id=winner.arm_id,
                label=winner.label,
                algorithm_used=exp.algorithm,
                decision_id=self._generate_decision_id(experiment_id, winner.arm_id, sticky_actor_id),
                metadata={"status": "PROMOTED_WINNER"},
            )

        # Filter arms matching context rules
        eligible_arms = [
            arm for arm in exp.arms.values()
            if self._matches_context(arm.context_rules, context or {})
        ]
        if not eligible_arms:
            # Fallback to all arms if none strictly match context
            eligible_arms = list(exp.arms.values())

        is_exploration = False
        selected_arm: ArmMetrics

        if sticky_actor_id and exp.algorithm == BanditAlgorithm.EPSILON_GREEDY:
            # Deterministic hash assignment for sticky sessions when specified
            hash_val = int(hashlib.sha256(f"{tenant_id}:{experiment_id}:{sticky_actor_id}".encode()).hexdigest(), 16)
            selected_arm = eligible_arms[hash_val % len(eligible_arms)]
        elif exp.algorithm == BanditAlgorithm.THOMPSON_SAMPLING:
            # Draw sample from Beta(alpha, beta) for each eligible arm
            sampled_scores: dict[str, float] = {}
            for arm in eligible_arms:
                # random.betavariate requires alpha > 0 and beta > 0
                a = max(0.01, arm.alpha)
                b = max(0.01, arm.beta)
                sampled_scores[arm.arm_id] = random.betavariate(a, b)

            best_arm_id = max(sampled_scores.items(), key=lambda kv: kv[1])[0]
            selected_arm = exp.arms[best_arm_id]
        elif exp.algorithm == BanditAlgorithm.UCB1:
            total_n = sum(arm.trials for arm in eligible_arms)
            if total_n == 0:
                selected_arm = random.choice(eligible_arms)
            else:
                scores: dict[str, float] = {}
                for arm in eligible_arms:
                    if arm.trials == 0:
                        scores[arm.arm_id] = float("inf")
                    else:
                        mean_reward = arm.conversions / arm.trials
                        bonus = exp.exploration_constant * math.sqrt((2.0 * math.log(max(1, total_n))) / arm.trials)
                        scores[arm.arm_id] = mean_reward + bonus
                best_arm_id = max(scores.items(), key=lambda kv: kv[1])[0]
                selected_arm = exp.arms[best_arm_id]
        else:  # EPSILON_GREEDY
            if random.random() < exp.epsilon:
                is_exploration = True
                selected_arm = random.choice(eligible_arms)
            else:
                selected_arm = max(eligible_arms, key=lambda a: (a.conversion_rate, a.trials))

        decision_id = self._generate_decision_id(experiment_id, selected_arm.arm_id, sticky_actor_id)
        return AllocationDecision(
            tenant_id=tenant_id,
            experiment_id=experiment_id,
            arm_id=selected_arm.arm_id,
            label=selected_arm.label,
            algorithm_used=exp.algorithm,
            exploration=is_exploration,
            decision_id=decision_id,
        )

    def record_reward(
        self,
        tenant_id: str,
        experiment_id: str,
        arm_id: str,
        converted: bool,
        value: float = 1.0,
    ) -> BanditExperiment:
        """
        Update the posterior distribution for an arm upon observing an outcome.
        Applies non-stationary discount decay to previous priors.
        """
        exp = self.get_experiment(tenant_id, experiment_id)
        if not exp:
            raise KeyError(f"Bandit experiment '{experiment_id}' not found for tenant '{tenant_id}'")
        if arm_id not in exp.arms:
            raise KeyError(f"Arm '{arm_id}' not found in experiment '{experiment_id}'")

        arm = exp.arms[arm_id]
        arm.trials += 1
        if converted:
            arm.conversions += 1

        # Apply decay factor to prior observations to track non-stationary trends
        gamma = exp.decay_factor
        if gamma < 1.0:
            arm.alpha = 1.0 + gamma * (arm.alpha - 1.0)
            arm.beta = 1.0 + gamma * (arm.beta - 1.0)

        # Update Beta conjugate prior
        if converted:
            arm.alpha += max(0.1, value)
        else:
            arm.beta += 1.0

        arm.updated_at = _utcnow().isoformat()
        exp.updated_at = _utcnow().isoformat()

        self._recompute_stats(exp)
        self._check_early_stopping(exp)
        return exp

    def _matches_context(self, rules: dict[str, list[str]], context: dict[str, Any]) -> bool:
        if not rules:
            return True
        for key, allowed_vals in rules.items():
            ctx_val = str(context.get(key, "")).lower()
            allowed_lower = [str(v).lower() for v in allowed_vals]
            if ctx_val not in allowed_lower:
                return False
        return True

    def _recompute_stats(self, exp: BanditExperiment) -> None:
        total_trials = sum(arm.trials for arm in exp.arms.values())

        for arm in exp.arms.values():
            arm.conversion_rate = (arm.conversions / arm.trials) if arm.trials > 0 else 0.0
            if total_trials > 0 and arm.trials > 0:
                bonus = exp.exploration_constant * math.sqrt((2.0 * math.log(total_trials)) / arm.trials)
                arm.ucb_score = round(arm.conversion_rate + bonus, 4)
            else:
                arm.ucb_score = 0.0

        # Monte Carlo simulation to compute Bayesian P(arm is optimal)
        num_simulations = 1000
        win_counts = {arm_id: 0 for arm_id in exp.arms}
        arm_list = list(exp.arms.values())

        for _ in range(num_simulations):
            samples = {
                arm.arm_id: random.betavariate(max(0.01, arm.alpha), max(0.01, arm.beta))
                for arm in arm_list
            }
            winner = max(samples.items(), key=lambda kv: kv[1])[0]
            win_counts[winner] += 1

        for arm in arm_list:
            arm.win_probability = round(win_counts[arm.arm_id] / num_simulations, 4)

    def _check_early_stopping(self, exp: BanditExperiment) -> None:
        if exp.status != "RUNNING":
            return

        for arm in exp.arms.values():
            if (
                arm.trials >= exp.min_samples_for_decision
                and arm.win_probability >= exp.confidence_threshold
            ):
                exp.status = "PROMOTED"
                exp.winning_arm = arm.arm_id
                break

    def _generate_decision_id(self, exp_id: str, arm_id: str, actor_id: str | None) -> str:
        entropy = f"{exp_id}:{arm_id}:{actor_id or random.random()}:{_utcnow().timestamp()}"
        return hashlib.sha256(entropy.encode()).hexdigest()[:16]


global_bandit_engine = MultiArmedBanditEngine()
