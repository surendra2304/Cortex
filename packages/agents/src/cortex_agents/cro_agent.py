"""Conversion Rate Optimization (CRO) & Experimentation Specialist Agent for CORTEX.

Performs statistical analysis on active A/B and multivariate tests:
- Computes conversion rates, standard errors, z-scores, and p-values
- Identifies statistically significant winners and underperforming variants
- Proposes traffic reallocation and winner promotion through closed-loop approval
- Challenges hasty funnel alterations when experiment data is inconclusive
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from . import (
    AgentInput,
    AgentOutput,
    ChallengeNote,
    HandoffRequest,
    ProposedAction,
    SpecialistAgent,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _calculate_ab_significance(
    control_views: int,
    control_convs: int,
    variant_views: int,
    variant_convs: int,
) -> dict[str, float]:
    """Calculate z-score, p-value, and relative uplift between control and variant."""
    if control_views < 10 or variant_views < 10:
        return {"cr_control": 0.0, "cr_variant": 0.0, "z_score": 0.0, "p_value": 1.0, "uplift": 0.0}

    p1 = control_convs / control_views
    p2 = variant_convs / variant_views

    pooled_p = (control_convs + variant_convs) / (control_views + variant_views)
    se = math.sqrt(pooled_p * (1.0 - pooled_p) * ((1.0 / control_views) + (1.0 / variant_views)))

    if se == 0:
        return {"cr_control": p1, "cr_variant": p2, "z_score": 0.0, "p_value": 1.0, "uplift": 0.0}

    z = (p2 - p1) / se
    # Two-tailed p-value using complementary error function approximation
    p_value = math.erfc(abs(z) / math.sqrt(2.0))
    uplift = ((p2 - p1) / p1) if p1 > 0 else 0.0

    return {
        "cr_control": round(p1, 4),
        "cr_variant": round(p2, 4),
        "z_score": round(z, 3),
        "p_value": round(p_value, 4),
        "uplift": round(uplift, 4),
    }


class CROExperimentAgent(SpecialistAgent):
    """Governs experiment evaluation, statistical rigor, and variant promotion."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="agent_cro",
            domain="cro",
            capabilities=[
                "experiment_mutate",
                "experiment_promote_variant",
                "traffic_reallocate",
            ],
        )

    async def process(self, input_data: AgentInput) -> AgentOutput:
        context = input_data.context or {}
        exp_data = context.get("experiment_data", {})
        experiment_id = exp_data.get("experiment_id", "exp_default")

        c_views = int(exp_data.get("control_impressions", 0))
        c_convs = int(exp_data.get("control_conversions", 0))
        v_views = int(exp_data.get("variant_impressions", 0))
        v_convs = int(exp_data.get("variant_conversions", 0))
        variant_name = exp_data.get("variant_name", "variant_b")

        stats = _calculate_ab_significance(c_views, c_convs, v_views, v_convs)
        total_samples = c_views + v_views
        p_val = stats["p_value"]
        z_score = stats["z_score"]
        uplift_pct = round(stats["uplift"] * 100, 2)

        evidence = [
            f"experiment_id={experiment_id}",
            f"total_samples={total_samples}",
            f"control_rate={stats['cr_control']}",
            f"variant_rate={stats['cr_variant']}",
            f"z_score={z_score}",
            f"p_value={p_val}",
            f"uplift_pct={uplift_pct}%",
        ]

        actions: list[ProposedAction] = []
        handoffs: list[HandoffRequest] = []
        challenges: list[ChallengeNote] = []

        if total_samples >= 100 and p_val < 0.05 and z_score > 1.96:
            decision = "PROMOTE_WINNING_VARIANT"
            reasoning = (
                f"Statistically significant winner ({variant_name}): {uplift_pct}% uplift, "
                f"p={p_val:.4f} < 0.05 over {total_samples} samples. Proposing 100% rollout."
            )
            actions.append(
                ProposedAction(
                    action_type="experiment_promote_variant",
                    target=experiment_id,
                    params={
                        "winning_variant": variant_name,
                        "uplift_pct": uplift_pct,
                        "confidence_level": round(1.0 - p_val, 4),
                    },
                    rationale=f"Winner {variant_name} confirmed at 95%+ confidence.",
                    side_effect_level="HIGH_IMPACT",
                )
            )
            handoffs.append(
                HandoffRequest(
                    target_agent_id="agent_growth",
                    reason=f"Winning variant {variant_name} ready for global funnel adoption",
                    question="Should we update default onboarding templates with this winning layout?",
                    priority="high",
                    payload={"experiment_id": experiment_id, "winning_variant": variant_name, "uplift": uplift_pct},
                )
            )
            confidence = 0.98

        elif total_samples >= 100 and p_val < 0.05 and z_score < -1.96:
            decision = "HALT_LOSING_VARIANT"
            reasoning = (
                f"Statistically significant underperformance ({variant_name}): {uplift_pct}% decline, "
                f"p={p_val:.4f}. Reallocating 100% traffic back to control."
            )
            actions.append(
                ProposedAction(
                    action_type="traffic_reallocate",
                    target=experiment_id,
                    params={"control_split": 100, "variant_split": 0},
                    rationale=f"Prevent conversion loss from defective variant {variant_name}.",
                    side_effect_level="HIGH_IMPACT",
                )
            )
            confidence = 0.95

        else:
            decision = "COLLECT_MORE_DATA"
            reasoning = (
                f"Inconclusive data (samples={total_samples}, p={p_val:.4f}). "
                "Maintaining current split until statistical power is reached."
            )
            confidence = 0.85

            # If Growth proposes an aggressive permanent rollout while data is still inconclusive:
            peer_decisions = {
                f.get("decision") for f in (context.get("peer_findings") or []) if isinstance(f, dict)
            }
            if "PROMOTE_VARIANT" in peer_decisions or "AGGRESSIVE_BANNER" in peer_decisions:
                challenges.append(
                    ChallengeNote(
                        target_agent_id="agent_growth",
                        claim="premature variant rollout",
                        reason=f"Experiment {experiment_id} has not reached significance (p={p_val:.4f} >= 0.05); early rollout risks false discovery.",
                        severity="medium",
                    )
                )

        return AgentOutput(
            agent_id=self.agent_id,
            decision=decision,
            reasoning_summary=reasoning,
            confidence=confidence,
            evidence_refs=evidence,
            proposed_actions=actions,
            expected_outcomes={
                "statistically_significant": p_val < 0.05 and total_samples >= 100,
                "uplift_pct": uplift_pct,
            },
            handoffs=handoffs,
            challenges=challenges,
            created_at=_utcnow(),
        )
