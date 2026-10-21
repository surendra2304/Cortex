"""Unit tests for newly expanded autonomous specialist agents:
- ComplianceGovernanceAgent (agent_compliance)
- CROExperimentAgent (agent_cro)
- RevenueOperationsAgent (agent_revops)
- ProactiveMitigationAgent (agent_mitigation)
- AgentRegistry routing integration
"""

from __future__ import annotations

import pytest
from cortex_agents import (
    AgentInput,
    AgentRegistry,
    ComplianceGovernanceAgent,
    CROExperimentAgent,
    ProactiveMitigationAgent,
    RevenueOperationsAgent,
)


@pytest.mark.asyncio
async def test_compliance_agent_detects_unmasked_pii_and_quarantines():
    agent = ComplianceGovernanceAgent()
    input_data = AgentInput(
        goal="Audit event batch for compliance",
        context={"tenant_id": "tenant_alpha"},
        events=[
            {"type": "form_submit", "data": {"card_number": "4111 2222 3333 4444", "name": "John Doe"}},
        ],
    )
    output = await agent.process(input_data)
    assert output.decision == "QUARANTINE_AND_ALERT"
    assert output.confidence >= 0.95
    assert any(a.action_type == "pii_quarantine" for a in output.proposed_actions)
    assert any(h.target_agent_id == "agent_reliability" for h in output.handoffs)


@pytest.mark.asyncio
async def test_compliance_agent_enforces_consent_revocation():
    agent = ComplianceGovernanceAgent()
    input_data = AgentInput(
        goal="Enforce GDPR consent compliance",
        context={
            "tenant_id": "tenant_alpha",
            "visitor_id": "vis_optout_123",
            "consent_status": "revoked",
            "peer_findings": [{"decision": "OPTIMIZE_FUNNEL"}],
        },
        events=[{"type": "page_view", "data": {"path": "/pricing"}}],
    )
    output = await agent.process(input_data)
    assert output.decision == "ENFORCE_CONSENT_OPT_OUT"
    assert any(a.action_type == "consent_enforce" for a in output.proposed_actions)
    assert any(c.target_agent_id == "agent_growth" for c in output.challenges)


@pytest.mark.asyncio
async def test_compliance_agent_reports_clean_on_safe_telemetry():
    agent = ComplianceGovernanceAgent()
    input_data = AgentInput(
        goal="Verify regular telemetry batch",
        context={"tenant_id": "tenant_safe", "consent_status": "granted"},
        events=[{"type": "click", "data": {"target_id": "btn_hero"}}],
    )
    output = await agent.process(input_data)
    assert output.decision == "COMPLIANCE_CLEAR"
    assert len(output.proposed_actions) == 0


@pytest.mark.asyncio
async def test_cro_agent_promotes_winning_variant():
    agent = CROExperimentAgent()
    input_data = AgentInput(
        goal="Analyze CTA test results",
        context={
            "experiment_data": {
                "experiment_id": "exp_pricing_v2",
                "variant_name": "variant_high_contrast",
                "control_impressions": 1000,
                "control_conversions": 50,  # 5%
                "variant_impressions": 1000,
                "variant_conversions": 90,  # 9% (statistically significant uplift)
            }
        },
    )
    output = await agent.process(input_data)
    assert output.decision == "PROMOTE_WINNING_VARIANT"
    assert output.confidence >= 0.95
    assert any(a.action_type == "experiment_promote_variant" for a in output.proposed_actions)
    assert any(h.target_agent_id == "agent_growth" for h in output.handoffs)


@pytest.mark.asyncio
async def test_cro_agent_halts_losing_variant():
    agent = CROExperimentAgent()
    input_data = AgentInput(
        goal="Analyze underperforming test",
        context={
            "experiment_data": {
                "experiment_id": "exp_checkout_flow",
                "variant_name": "variant_long_form",
                "control_impressions": 1000,
                "control_conversions": 100,  # 10%
                "variant_impressions": 1000,
                "variant_conversions": 40,  # 4% (significant decline)
            }
        },
    )
    output = await agent.process(input_data)
    assert output.decision == "HALT_LOSING_VARIANT"
    assert any(a.action_type == "traffic_reallocate" for a in output.proposed_actions)


@pytest.mark.asyncio
async def test_cro_agent_holds_when_data_inconclusive():
    agent = CROExperimentAgent()
    input_data = AgentInput(
        goal="Early test analysis",
        context={
            "experiment_data": {
                "experiment_id": "exp_early_stage",
                "variant_name": "variant_b",
                "control_impressions": 20,
                "control_conversions": 1,
                "variant_impressions": 20,
                "variant_conversions": 2,
            },
            "peer_findings": [{"decision": "PROMOTE_VARIANT"}],
        },
    )
    output = await agent.process(input_data)
    assert output.decision == "COLLECT_MORE_DATA"
    assert len(output.proposed_actions) == 0
    # Challenges premature rollout
    assert any(c.target_agent_id == "agent_growth" for c in output.challenges)


@pytest.mark.asyncio
async def test_revops_agent_reconciles_past_due_billing():
    agent = RevenueOperationsAgent()
    input_data = AgentInput(
        goal="Assess account standing",
        context={
            "billing_data": {
                "customer_id": "cust_enterprise_99",
                "past_due_amount": 12500.0,
                "status": "delinquent",
            }
        },
        events=[{"type": "invoice.payment_failed", "data": {"amount": 12500.0}}],
    )
    output = await agent.process(input_data)
    assert output.decision == "RECONCILE_BILLING_DELINQUENCY"
    assert any(a.action_type == "billing_reconcile" for a in output.proposed_actions)
    assert any(h.target_agent_id == "agent_churn_risk" for h in output.handoffs)


@pytest.mark.asyncio
async def test_revops_agent_fast_tracks_strategic_deal():
    agent = RevenueOperationsAgent()
    input_data = AgentInput(
        goal="Route inbound RFP",
        context={
            "deal_data": {
                "deal_id": "deal_fortune500",
                "annual_contract_value": 150000.0,
                "stage": "procurement",
                "stakeholder_count": 4,
            }
        },
    )
    output = await agent.process(input_data)
    assert output.decision == "FAST_TRACK_STRATEGIC_DEAL"
    assert any(a.action_type == "deal_route" for a in output.proposed_actions)
    assert any(h.target_agent_id == "agent_sales" for h in output.handoffs)


@pytest.mark.asyncio
async def test_mitigation_agent_triggers_emergency_throttle_on_threat():
    agent = ProactiveMitigationAgent()
    input_data = AgentInput(
        goal="Assess gateway health",
        context={
            "telemetry": {"error_rate_5xx_pct": 32.5, "requests_per_sec": 450.0},
            "sentinel_signals": {"threat_level": "critical"},
        },
        events=[{"type": "server_error", "data": {"status": 503}}],
    )
    output = await agent.process(input_data)
    assert output.decision == "TRIGGER_EMERGENCY_THROTTLE"
    assert any(a.action_type == "traffic_throttle" for a in output.proposed_actions)
    assert any(a.action_type == "circuit_trip" for a in output.proposed_actions)
    assert any(h.target_agent_id == "agent_reliability" for h in output.handoffs)
    assert any(c.target_agent_id == "agent_growth" for c in output.challenges)


@pytest.mark.asyncio
async def test_mitigation_agent_tightens_rate_limits_on_brute_force():
    agent = ProactiveMitigationAgent()
    input_data = AgentInput(
        goal="Inspect threat signals",
        context={
            "telemetry": {"error_rate_5xx_pct": 2.0},
            "sentinel_signals": {
                "threat_level": "elevated",
                "brute_force_ips": ["198.51.100.1", "198.51.100.2"],
            },
        },
    )
    output = await agent.process(input_data)
    assert output.decision == "TIGHTEN_RATE_LIMITS"
    assert any(a.action_type == "rate_limit_mutate" for a in output.proposed_actions)


def test_agent_registry_routes_new_specialist_domains():
    registry = AgentRegistry()
    assert registry.route_for_event("privacy_consent_update").domain == "compliance"
    assert registry.route_for_event("ab_test_variant_impression").domain == "cro"
    assert registry.route_for_event("deal_contract_negotiation").domain == "revops"
    assert registry.route_for_event("ddos_attack_signature").domain == "mitigation"
