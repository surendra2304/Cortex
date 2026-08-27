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
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(p))

from nexus_agents import (
    GrowthAgent, SalesAgent, SupportAgent, ReliabilityAgent, QualificationAgent, ChurnRiskAgent,
    AgentInput, AgentRegistry
)
from nexus_ai_universe_adapter import RequestClassifier, RequestClassification, AIMode


@pytest.mark.asyncio
async def test_growth_agent_dynamic_intent_reasoning():
    agent = GrowthAgent()

    # Case A: High Intent Events (Pricing + Demo + Enterprise)
    high_intent_input = AgentInput(
        goal="optimize conversion",
        events=[
            {"type": "page_view", "data": {"path": "/home"}},
            {"type": "pricing.viewed", "data": {"plan": "enterprise"}},
            {"type": "pricing.viewed", "data": {"plan": "enterprise"}},
            {"type": "demo.requested", "data": {"size": "500+"}},
            {"type": "enterprise.page_view", "data": {"page": "security"}},
        ]
    )
    high_output = await agent.process(high_intent_input)
    assert high_output.decision == "OPTIMIZE_FUNNEL"
    assert len(high_output.proposed_actions) == 1
    assert high_output.proposed_actions[0].params["variant"] == "aggressive_cta"
    assert any("pricing_views=2" in ref for ref in high_output.evidence_refs)
    assert any("demo_views=1" in ref for ref in high_output.evidence_refs)

    # Case B: Low Intent Events (Single blog visit)
    low_intent_input = AgentInput(
        goal="optimize conversion",
        events=[{"type": "page_view", "data": {"path": "/blog/post-1"}}]
    )
    low_output = await agent.process(low_intent_input)
    assert low_output.decision == "NO_ACTION"
    assert len(low_output.proposed_actions) == 0

    # Anti-Hardcode Invariant: Outputs MUST be strictly different for different inputs
    assert high_output.decision != low_output.decision
    assert high_output.proposed_actions != low_output.proposed_actions
    assert high_output.reasoning_summary != low_output.reasoning_summary


@pytest.mark.asyncio
async def test_sales_agent_firmographic_and_intent_routing():
    agent = SalesAgent()

    # Enterprise lead
    enterprise_input = AgentInput(
        goal="qualify lead",
        events=[
            {"type": "pricing.viewed"},
            {"type": "demo.requested"},
            {"type": "page_view"},
            {"type": "page_view"},
        ],
        context={
            "visitor_attributes": {"email": "director@bigcorp.com", "company": "BigCorp"},
            "event_data": {"source": "direct"}
        }
    )
    ent_output = await agent.process(enterprise_input)
    assert ent_output.decision == "ROUTE_ENTERPRISE_LEAD"
    assert ent_output.proposed_actions[0].params["tier"] == "enterprise_tier_1"

    # Consumer / low-intent lead
    consumer_input = AgentInput(
        goal="qualify lead",
        events=[{"type": "page_view"}],
        context={
            "visitor_attributes": {"email": "casual@gmail.com"},
            "event_data": {"source": "social"}
        }
    )
    cons_output = await agent.process(consumer_input)
    assert cons_output.decision == "NURTURE_LEAD"
    assert len(cons_output.proposed_actions) == 0

    # Verify dynamic computation
    assert ent_output.decision != cons_output.decision


@pytest.mark.asyncio
async def test_support_agent_no_hallucinations_when_healthy():
    agent = SupportAgent()

    # Healthy session -> NO_INTERVENTION
    healthy_input = AgentInput(
        goal="assist user",
        events=[{"type": "page_view"}, {"type": "scroll"}, {"type": "click"}]
    )
    healthy_output = await agent.process(healthy_input)
    assert healthy_output.decision == "NO_INTERVENTION"
    assert len(healthy_output.proposed_actions) == 0

    # Error-ridden checkout session -> HIGH_PRIORITY_INTERVENTION
    failing_input = AgentInput(
        goal="assist user",
        events=[
            {"type": "page_view", "data": {"path": "/checkout"}},
            {"type": "error.payment_declined", "data": {"error": "card_declined", "page": "checkout"}},
            {"type": "error.server_500", "data": {"error": "timeout", "page": "checkout"}},
            {"type": "error.network", "data": {"page": "checkout"}},
        ]
    )
    failing_output = await agent.process(failing_input)
    assert failing_output.decision == "HIGH_PRIORITY_INTERVENTION"
    assert len(failing_output.proposed_actions) == 2

    assert healthy_output.decision != failing_output.decision


@pytest.mark.asyncio
async def test_reliability_and_qualification_and_churn_agents():
    rel_agent = ReliabilityAgent()
    qual_agent = QualificationAgent()
    churn_agent = ChurnRiskAgent()

    # Reliability within SLO
    rel_ok = await rel_agent.process(AgentInput(
        goal="check slo",
        context={"metrics": {"latency_p99_ms": 120, "error_rate_pct": 0.1}}
    ))
    assert rel_ok.decision == "NO_ACTION"

    # Reliability SLO breach
    rel_breach = await rel_agent.process(AgentInput(
        goal="check slo",
        context={"metrics": {"latency_p99_ms": 850, "error_rate_pct": 8.0}}
    ))
    assert rel_breach.decision == "ESCALATE_RELIABILITY_INCIDENT"

    # Qualification Agent
    qual_res = await qual_agent.process(AgentInput(
        goal="score lead",
        events=[{"type": "pricing.viewed"}, {"type": "demo.viewed"}, {"type": "docs.viewed"}],
        context={"visitor_attributes": {"email": "vp@enterprise.com", "source": "direct"}}
    ))
    assert qual_res.decision == "QUALIFIED_LEAD"
    assert qual_res.expected_outcomes["qualification_passed"] is True

    # Churn Risk Agent
    churn_res = await churn_agent.process(AgentInput(
        goal="assess churn",
        context={"metrics": {"sessions_last_30d": 2, "sessions_prev_30d": 20, "support_tickets_recent": 4}}
    ))
    assert churn_res.decision == "RISK_HIGH"


def test_request_classifier_modes_and_logic():
    classifier = RequestClassifier()

    # Trivial -> No AI
    t_class, t_mode = classifier.classify("page_view", {})
    assert t_class == RequestClassification.TRIVIAL
    assert t_mode is None
    assert classifier.should_call_ai(t_class) is False

    # Strategic -> DEBATE mode
    s_class, s_mode = classifier.classify("high_intent.detected", {})
    assert s_class == RequestClassification.STRATEGIC
    assert s_mode == AIMode.DEBATE
    assert classifier.should_call_ai(s_class) is True

    # Ambiguous -> FAST mode
    a_class, a_mode = classifier.classify("pricing.viewed", {})
    assert a_class == RequestClassification.AMBIGUOUS
    assert a_mode == AIMode.FAST
    assert classifier.should_call_ai(a_class) is True


def test_agent_registry_routing():
    registry = AgentRegistry()
    assert registry.route_for_event("pricing.viewed").domain == "growth"
    assert registry.route_for_event("checkout.completed").domain == "sales"
    assert registry.route_for_event("error.500").domain == "support"
    assert registry.route_for_event("qualify.lead").domain == "qualification"
    assert registry.route_for_event("churn.risk_check").domain == "churn_risk"
