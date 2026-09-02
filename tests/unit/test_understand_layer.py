import pytest
import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

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

from cortex_identity import IdentityResolver
from cortex_analytics import ScoringEngine, FunnelEngine, CohortEngine
from cortex_intelligence import ContextBuilder
from cortex_memory import MemoryStore, MemoryScope, TrustLabel
from cortex_api.db_models import VisitorModel, ProfileModel, LeadModel, IdentityLinkModel, MemoryEntryModel


@pytest.mark.asyncio
async def test_identity_resolution_chain_and_consent_policy():
    resolver = IdentityResolver()
    mock_db = AsyncMock()

    # Mock DB returns no existing visitor or profile
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    # Case A: Anonymous Visitor without Consent -> Pseudonymous tracking only
    res_no_consent = await resolver.resolve_identity(
        db=mock_db,
        visitor_id="vis_anon_99",
        email="lead@company.com",
        consent_granted=False
    )
    assert res_no_consent["is_identified"] is False
    assert res_no_consent["lifecycle_stage"] == "anonymous"

    # Case B: Visitor with Consent & Email -> Promoted to Lead
    res_identified = await resolver.resolve_identity(
        db=mock_db,
        visitor_id="vis_anon_99",
        email="lead@enterprise.com",
        consent_granted=True,
        traits={"company": "Enterprise Corp"}
    )
    assert res_identified["is_identified"] is True
    assert res_identified["primary_email"] == "lead@enterprise.com"
    assert res_identified["lifecycle_stage"] == "lead"


def test_scoring_engine_explainable_breakdown():
    scoring = ScoringEngine()

    # Synthetic qualifying events
    events = [
        {"type": "page_view", "data": {"path": "/home"}},
        {"type": "pricing.viewed", "data": {"plan": "enterprise"}},
        {"type": "pricing.viewed", "data": {"plan": "enterprise"}},
        {"type": "demo.requested", "data": {"size": "500+"}},
        {"type": "email.opened", "data": {}},
    ]
    traits = {
        "email": "director@bigcorp.com",
        "company": "BigCorp",
        "source": "linkedin"
    }

    score_res = scoring.compute_score(events, traits, session_summary={"pricing_view_count": 2, "demo_view_count": 1})

    # Exact mathematical weights
    assert score_res.total > 0.60
    assert score_res.behavior > 0.20
    assert score_res.firmographic == 0.30  # Corporate domain max firmographic
    assert score_res.source == 0.10        # LinkedIn max source
    assert score_res.details["is_corp_domain"] is True
    assert score_res.details["pricing_views"] == 2


def test_funnel_engine_conversion_and_anomaly_detection():
    funnel = FunnelEngine()

    # Synthetic session sequence with a drop-off
    events = [
        {"session_id": "s1", "type": "page_view", "data": {"path": "/pricing"}},
        {"session_id": "s1", "type": "demo.viewed", "data": {"path": "/demo"}},
        {"session_id": "s1", "type": "checkout.completed", "data": {"path": "/checkout"}},

        {"session_id": "s2", "type": "page_view", "data": {"path": "/pricing"}},
        {"session_id": "s2", "type": "demo.viewed", "data": {"path": "/demo"}},

        {"session_id": "s3", "type": "page_view", "data": {"path": "/pricing"}},
    ]

    steps = ["pricing", "demo", "checkout"]
    analysis = funnel.analyze_funnel(events, steps)

    assert analysis["total_visitors"] == 3
    assert len(analysis["funnel_steps"]) == 3
    assert analysis["funnel_steps"][0]["visitors_count"] == 3
    assert analysis["funnel_steps"][1]["visitors_count"] == 2
    assert analysis["funnel_steps"][2]["visitors_count"] == 1
    assert analysis["overall_conversion_pct"] == 33.3


def test_context_builder_intent_levels_and_anomaly_flags():
    builder = ContextBuilder()

    # High Intent Session with Error Anomaly
    high_intent_event = {"type": "enterprise.page_view", "data": {}}
    session_events = [
        {"type": "pricing.viewed"},
        {"type": "demo.viewed"},
        {"type": "error.payment_declined"},
        {"type": "error.500"},
        {"type": "error.network"},
        {"type": "rage_click"},
        {"type": "rage_click"},
    ]

    ctx = builder.build_context(
        event=high_intent_event,
        session_events=session_events,
        actor_events=[],
        visitor_attributes={"country": "US"},
        profile_traits={"email": "lead@corp.com"}
    )

    assert ctx.intent_level == "HIGH_INTENT"
    assert ctx.intent_score >= 0.70
    assert "high_session_error_count" in ctx.anomaly_flags
    assert "rage_clicks_detected" in ctx.anomaly_flags


@pytest.mark.asyncio
async def test_memory_store_put_get_and_strategy_learnings():
    memory = MemoryStore()

    # Record strategy outcome learning
    recorded = await memory.record_strategy_outcome(
        db=None,
        strategy_name="agent_growth:banner_injection",
        context_features={"intent_score": 0.85, "pricing_views": 3},
        action_taken="banner_injection",
        outcome_lift_pct=14.5,
        sample_size=50
    )
    assert recorded.scope == MemoryScope.STRATEGY.value
    assert recorded.trust_label == TrustLabel.VERIFIED_TELEMETRY.value

    # Retrieve from memory store
    entries = await memory.get(db=None, scope=MemoryScope.STRATEGY.value, scope_id="agent_growth:banner_injection")
    assert len(entries) == 1
    assert entries[0].content["measured_lift_pct"] == 14.5
    assert entries[0].content["sample_size"] == 50
