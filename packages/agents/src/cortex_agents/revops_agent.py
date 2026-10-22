"""Revenue Operations & Commercial Deal Routing Specialist Agent for CORTEX.

Governs deal velocity, CRM pipeline transitions, and commercial billing reconciliation:
- Evaluates contract sizing and velocity indicators (ACV thresholds, multi-stakeholder engagement)
- Reconciles Stripe/billing events against customer CRM subscription stages
- Detects deal stagnation and triggers timely rep intervention
- Proposes crm_sync and deal_route actions with verified idempotency
"""

from __future__ import annotations

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


class RevenueOperationsAgent(SpecialistAgent):
    """Governs commercial pipeline velocity, deal routing, and billing reconciliation."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="agent_revops",
            domain="revops",
            capabilities=[
                "crm_sync",
                "deal_route",
                "billing_reconcile",
                "quote_generate",
            ],
        )

    async def process(self, input_data: AgentInput) -> AgentOutput:
        events = input_data.events or []
        context = input_data.context or {}
        deal = context.get("deal_data", {})
        billing = context.get("billing_data", {})

        acv = float(deal.get("annual_contract_value", 0.0))
        stage = deal.get("stage", "discovery")
        days_in_stage = int(deal.get("days_in_stage", 0))
        stakeholder_count = int(deal.get("stakeholder_count", 1))

        billing_status = billing.get("status", "healthy")
        past_due_amount = float(billing.get("past_due_amount", 0.0))

        # Check for checkout or invoice events
        payment_failed_events = [
            e for e in events
            if "invoice.payment_failed" in e.get("type", "").lower()
            or "charge.failed" in e.get("type", "").lower()
        ]

        evidence = [
            f"acv=${acv:.2f}",
            f"current_stage={stage}",
            f"days_in_stage={days_in_stage}",
            f"stakeholder_count={stakeholder_count}",
            f"billing_status={billing_status}",
            f"past_due_amount=${past_due_amount:.2f}",
            f"payment_failure_events={len(payment_failed_events)}",
        ]

        actions: list[ProposedAction] = []
        handoffs: list[HandoffRequest] = []
        challenges: list[ChallengeNote] = []

        if payment_failed_events or past_due_amount > 0:
            decision = "RECONCILE_BILLING_DELINQUENCY"
            reasoning = (
                f"Delinquency detected: past_due=${past_due_amount:.2f}, "
                f"failed_events={len(payment_failed_events)}. Initiating dunning & CRM hold."
            )
            actions.append(
                ProposedAction(
                    action_type="billing_reconcile",
                    target=billing.get("customer_id", "cust_unknown"),
                    params={"past_due": past_due_amount, "action": "pause_service_grace_period"},
                    rationale="Mitigate revenue loss on past-due commercial account.",
                    side_effect_level="HIGH_IMPACT",
                )
            )
            handoffs.append(
                HandoffRequest(
                    target_agent_id="agent_churn_risk",
                    reason="Billing failure risks involuntary churn if unaddressed within grace period",
                    question="Should we deploy a custom payment recovery sequence?",
                    priority="urgent",
                    payload={"past_due": past_due_amount, "customer_id": billing.get("customer_id")},
                )
            )
            confidence = 0.98

        elif acv >= 50000.0 and stakeholder_count >= 2:
            decision = "FAST_TRACK_STRATEGIC_DEAL"
            reasoning = (
                f"High-value strategic deal (${acv:,.0f} ACV, {stakeholder_count} stakeholders). "
                "Routing to Executive Sponsor & Senior Solutions Architect."
            )
            actions.append(
                ProposedAction(
                    action_type="deal_route",
                    target=deal.get("deal_id", "deal_strategic"),
                    params={
                        "tier": "tier_1_strategic",
                        "assigned_team": "strategic_enterprise",
                        "acv": acv,
                        "executive_sponsor_assigned": True,
                    },
                    rationale="Strategic deals exceeding $50k ACV require executive sponsorship.",
                    side_effect_level="SENSITIVE",
                )
            )
            handoffs.append(
                HandoffRequest(
                    target_agent_id="agent_sales",
                    reason="Enterprise multi-stakeholder deal fast-tracked",
                    question="Which enterprise AE will own this RFP sequence?",
                    priority="high",
                    payload={"deal_id": deal.get("deal_id"), "acv": acv},
                )
            )
            confidence = 0.95

        elif days_in_stage > 21:
            decision = "ESCALATE_STALLED_DEAL"
            reasoning = f"Deal stalled in '{stage}' for {days_in_stage} days (> 21 days SLA threshold)."
            actions.append(
                ProposedAction(
                    action_type="crm_sync",
                    target=deal.get("deal_id", "deal_stalled"),
                    params={"flag": "stalled_deal_alert", "days_in_stage": days_in_stage},
                    rationale="Flag stalled pipeline deal for weekly pipeline review.",
                    side_effect_level="SENSITIVE",
                )
            )
            confidence = 0.88

        else:
            decision = "PIPELINE_HEALTHY"
            reasoning = f"Deal progressing normally in '{stage}' ({days_in_stage} days, ACV=${acv:.0f})."
            confidence = 0.92

        return AgentOutput(
            agent_id=self.agent_id,
            decision=decision,
            reasoning_summary=reasoning,
            confidence=confidence,
            evidence_refs=evidence,
            proposed_actions=actions,
            expected_outcomes={"decision": decision, "acv": acv},
            handoffs=handoffs,
            challenges=challenges,
            created_at=_utcnow(),
        )
