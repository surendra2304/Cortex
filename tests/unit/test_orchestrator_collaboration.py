"""The cognitive loop must actually let peers help — and stop when the knob says stop.

These tests drive the real ``Orchestrator.run_cognitive_loop`` (no mocks of the loop itself)
and assert on observable behaviour: who ran, what the transcript says, what evidence the lead
agent ended up with, and that turning the self-tunable knob off disables the peer work.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

import pytest

sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/event_schema/src"))
sys.path.insert(0, os.path.abspath("packages/agents/src"))
sys.path.insert(0, os.path.abspath("packages/ai_universe_adapter/src"))
sys.path.insert(0, os.path.abspath("packages/tool_runtime/src"))
sys.path.insert(0, os.path.abspath("packages/policy_engine/src"))
sys.path.insert(0, os.path.abspath("packages/workflow_engine/src"))

from cortex_agents import AgentInput, AgentOutput, AgentRegistry, HandoffRequest, SpecialistAgent
from cortex_core import Orchestrator
from cortex_event_schema import Actor, ActorType, EventSchema

from cortex_upgrade.runtime_knobs import global_runtime_knobs


class _LeadAgent(SpecialistAgent):
    def __init__(self, ask_for_help: bool = True):
        super().__init__(agent_id="agent_growth", domain="growth", capabilities=["experiment_mutate"])
        self.ask_for_help = ask_for_help
        self.calls = 0

    async def process(self, input_data: AgentInput) -> AgentOutput:
        self.calls += 1
        handoffs = [HandoffRequest(target_agent_id="agent_sales", reason="needs a commercial owner")]
        return AgentOutput(
            agent_id=self.agent_id,
            decision="OPTIMIZE_FUNNEL",
            reasoning_summary="high intent",
            confidence=0.9,
            handoffs=handoffs if self.ask_for_help else [],
        )


class _PeerAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(agent_id="agent_sales", domain="sales", capabilities=[])
        self.calls = 0
        self.saw_peer_findings: list[dict] = []

    async def process(self, input_data: AgentInput) -> AgentOutput:
        self.calls += 1
        self.saw_peer_findings = list(input_data.context.get("peer_findings", []))
        return AgentOutput(
            agent_id=self.agent_id,
            decision="ROUTE_ENTERPRISE_LEAD",
            reasoning_summary="enterprise buyer",
            confidence=0.8,
        )


def _event() -> EventSchema:
    return EventSchema(
        event_id="evt_collab_1",
        tenant_id="tenant_alpha",
        site_id="site_beta",
        type="pricing_view",
        occurred_at=datetime.now(UTC),
        actor=Actor(type=ActorType.VISITOR, id="vis_123"),
        source="web-sdk",
        data={"plan": "enterprise"},
    )


def _orchestrator(lead: _LeadAgent, peer: _PeerAgent) -> Orchestrator:
    """Real registry, real routing; only the two scripted agents replace the built-ins."""
    registry = AgentRegistry()
    registry.register(lead)  # keys by agent_id and by domain ("growth")
    registry.register(peer)  # keys by agent_id and by domain ("sales")
    return Orchestrator(agent_registry=registry)


@pytest.mark.asyncio
async def test_peers_run_inside_the_cognitive_loop_and_their_findings_reach_the_lead():
    lead, peer = _LeadAgent(), _PeerAgent()
    orchestrator = _orchestrator(lead, peer)

    result = await orchestrator.run_cognitive_loop(_event())

    assert result["status"] == "success"
    assert peer.calls == 1, "the requested peer must actually run"
    assert lead.calls == 1, "the lead agent must not be re-run just to seed the session"
    assert peer.saw_peer_findings and peer.saw_peer_findings[0]["decision"] == "OPTIMIZE_FUNNEL"

    phases = [entry["phase"] for entry in result["trace"]]
    assert "4a.Collaborate" in phases
    collaboration = next(entry for entry in result["trace"] if entry["phase"] == "4a.Collaborate")
    assert collaboration["participants"] == ["agent_growth", "agent_sales"]
    assert collaboration["dissent"] == ["agent_sales"] or collaboration["agreement"] >= 0.0

    # The peer's judgement is now part of the recorded evidence trail.
    assert any("peer:agent_sales" in item for item in collaboration["peer_evidence"]), collaboration


@pytest.mark.asyncio
async def test_no_handoff_means_no_peer_traffic():
    lead, peer = _LeadAgent(ask_for_help=False), _PeerAgent()
    result = await orchestrator_run(lead, peer)
    assert peer.calls == 0
    assert not any(entry["phase"] == "4a.Collaborate" for entry in result["trace"])


@pytest.mark.asyncio
async def test_disabling_the_knob_disables_collaboration_self_tuning():
    """The self-modification allow-list can switch peer work off; the loop must honour it."""
    lead, peer = _LeadAgent(), _PeerAgent()
    previous = global_runtime_knobs.get("max_collaboration_rounds", 3)
    global_runtime_knobs.set("max_collaboration_rounds", 0, rationale="test: disable collaboration")
    try:
        result = await orchestrator_run(lead, peer)
    finally:
        global_runtime_knobs.set("max_collaboration_rounds", previous, rationale="test cleanup")

    assert peer.calls == 0
    assert not any(entry["phase"] == "4a.Collaborate" for entry in result["trace"])


@pytest.mark.asyncio
async def test_a_peer_failure_does_not_take_down_the_loop():
    class _ExplodingPeer(_PeerAgent):
        async def process(self, input_data: AgentInput) -> AgentOutput:
            raise RuntimeError("peer down")

    lead, peer = _LeadAgent(), _ExplodingPeer()
    result = await orchestrator_run(lead, peer)

    assert result["status"] == "success", "the lead agent's decision must still stand"
    assert lead.calls == 1


async def orchestrator_run(lead: _LeadAgent, peer: _PeerAgent) -> dict:
    return await _orchestrator(lead, peer).run_cognitive_loop(_event())
