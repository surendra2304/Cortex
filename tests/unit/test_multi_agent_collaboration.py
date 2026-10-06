"""Multi-agent collaboration: handoffs, shared board, consensus and hard bounds.

Live verification lives in ``scripts/self_healing_live_test.py`` (real Redis outage) and in
the pressure run; these tests pin the protocol itself so a refactor cannot silently break
the handoff contract.
"""

from __future__ import annotations

import asyncio

import pytest
from cortex_agents import (
    AgentInput,
    AgentOutput,
    AgentRegistry,
    ChallengeNote,
    CollaborationSession,
    HandoffRequest,
    SalesAgent,
    SpecialistAgent,
)
from cortex_agents.collaboration import CollaborationSession as SessionFromModule


def _run(coro):
    return asyncio.run(coro)


class _Recorder(SpecialistAgent):
    """Agent that emits pre-scripted handoffs and records what it received."""

    def __init__(self, agent_id: str, handoffs: list[HandoffRequest] | None = None, decision: str = "OK", conf=0.9):
        super().__init__(agent_id=agent_id, domain=agent_id.replace("agent_", ""), capabilities=["read"])
        self._handoffs = handoffs or []
        self.decision = decision
        self.conf = conf
        self.received_peer_findings: list[list[dict]] = []
        self.calls = 0

    async def process(self, input_data: AgentInput) -> AgentOutput:
        self.calls += 1
        self.received_peer_findings.append(list(input_data.context.get("peer_findings", [])))
        return AgentOutput(
            agent_id=self.agent_id,
            decision=self.decision,
            reasoning_summary="scripted",
            confidence=self.conf,
            handoffs=list(self._handoffs),
        )


def _registry(*agents: SpecialistAgent) -> AgentRegistry:
    registry = AgentRegistry.__new__(AgentRegistry)  # bypass the built-in registrations
    registry._agents = {}
    for agent in agents:
        registry.register(agent)
    return registry


def test_handoff_target_receives_peer_findings():
    """The peer must actually get the requester's findings, not just be called."""
    root = _Recorder(
        "agent_growth",
        handoffs=[HandoffRequest(target_agent_id="agent_sales", reason="needs a commercial owner")],
        decision="OPTIMIZE_FUNNEL",
    )
    peer = _Recorder("agent_sales", decision="ROUTE_ENTERPRISE_LEAD", conf=0.8)
    session = CollaborationSession(_registry(root, peer))

    result = _run(session.run("agent_growth", "grow revenue"))

    assert result.participants == ["agent_growth", "agent_sales"]
    assert result.handoffs_executed == 1
    assert result.rounds_used == 2
    # The peer saw the requester's decision + evidence on the shared board.
    assert peer.received_peer_findings[0][0]["agent_id"] == "agent_growth"
    assert peer.received_peer_findings[0][0]["decision"] == "OPTIMIZE_FUNNEL"
    # Consensus is recorded with the disagreement named, not averaged away.
    assert result.consensus.decision == "OPTIMIZE_FUNNEL"
    assert result.consensus.dissenting == ["agent_sales"]
    assert "agent_sales:ROUTE_ENTERPRISE_LEAD" in result.consensus.unresolved


def test_self_handoff_and_unknown_target_are_refused():
    root = _Recorder(
        "agent_growth",
        handoffs=[
            HandoffRequest(target_agent_id="agent_growth", reason="talking to myself"),
            HandoffRequest(target_agent_id="agent_nonexistent", reason="ghost"),
            HandoffRequest(target_agent_id="agent_sales", reason="legitimate"),
        ],
    )
    peer = _Recorder("agent_sales")
    result = _run(CollaborationSession(_registry(root, peer)).run("agent_growth", "goal"))

    reasons = {entry["target"]: entry["reason"] for entry in result.handoffs_refused}
    assert reasons["agent_growth"] == "self-handoff"
    assert reasons["agent_nonexistent"] == "unknown agent 'agent_nonexistent'"
    assert result.handoffs_executed == 1


def test_cycles_are_bounded_and_every_agent_participates_once():
    """A→B→A must not loop: the revisit is refused and the session terminates."""
    a = _Recorder("agent_a", handoffs=[HandoffRequest(target_agent_id="agent_b", reason="need b")])
    b = _Recorder("agent_b", handoffs=[HandoffRequest(target_agent_id="agent_a", reason="need a back")])
    result = _run(CollaborationSession(_registry(a, b)).run("agent_a", "goal"))

    assert result.participants == ["agent_a", "agent_b"]
    assert a.calls == 1 and b.calls == 1
    assert {"target": "agent_a", "reason": "already participated"} in result.handoffs_refused
    assert result.rounds_used == 2


def test_max_rounds_and_max_agents_are_enforced():
    agents = [
        _Recorder(f"agent_{index}", handoffs=[HandoffRequest(target_agent_id=f"agent_{index + 1}", reason="chain")])
        for index in range(6)
    ]
    session = CollaborationSession(_registry(*agents), max_rounds=2, max_agents=3)
    result = _run(session.run("agent_0", "goal"))

    assert len(result.participants) <= 3
    assert result.rounds_used <= 2
    assert result.handoffs_refused, "bounds must be reported when they cut a handoff"


class _Exploding(SpecialistAgent):
    def __init__(self):
        super().__init__(agent_id="agent_broken", domain="broken", capabilities=[])

    async def process(self, input_data: AgentInput) -> AgentOutput:
        raise RuntimeError("boom")


def test_a_failing_agent_is_recorded_not_fatal():
    """One agent blowing up must not sink the session or hide the failure."""
    root = _Recorder("agent_growth", handoffs=[HandoffRequest(target_agent_id="agent_broken", reason="help")])
    result = _run(CollaborationSession(_registry(root, _Exploding())).run("agent_growth", "goal"))

    broken = [step for step in result.transcript if step.agent_id == "agent_broken"]
    assert len(broken) == 1
    assert broken[0].error and "boom" in broken[0].error
    assert broken[0].decision == "AGENT_ERROR"
    assert result.consensus.decision == "OK"  # the healthy agent still carries the session


class _Challenger(SpecialistAgent):
    """Peer that contests the lead's decision with a configurable severity."""

    def __init__(self, agent_id: str = "agent_sales", severity: str = "high", target: str = "agent_growth"):
        super().__init__(agent_id=agent_id, domain=agent_id.replace("agent_", ""), capabilities=[])
        self.severity = severity
        self.target = target
        self.calls = 0
        self.saw_open_challenges: list[list[dict]] = []

    async def process(self, input_data: AgentInput) -> AgentOutput:
        self.calls += 1
        self.saw_open_challenges.append(list(input_data.context.get("open_challenges", [])))
        return AgentOutput(
            agent_id=self.agent_id,
            decision="NURTURE_LEAD",
            reasoning_summary="retention first",
            confidence=0.7,
            challenges=[
                ChallengeNote(
                    target_agent_id=self.target,
                    claim="aggressive conversion play on a retention-risk session",
                    reason="churn_risk=0.82",
                    severity=self.severity,
                )
            ],
        )


class _Verifier(_Recorder):
    """An uninvolved peer asked to arbitrate; records the challenge it was shown."""

    def __init__(self, agent_id: str = "agent_qualification"):
        super().__init__(agent_id, decision="VERIFIER_UPHOLDS", conf=0.6)
        self.saw_open_challenges: list[list[dict]] = []

    async def process(self, input_data: AgentInput) -> AgentOutput:
        self.saw_open_challenges.append(list(input_data.context.get("open_challenges", [])))
        return await super().process(input_data)


def _verifier(agent_id: str = "agent_qualification") -> _Verifier:
    return _Verifier(agent_id)


def test_high_severity_challenge_triggers_a_verification_pass():
    """A contested claim is arbitrated by an uninvolved peer, and that peer sees the dispute."""
    root = _Recorder("agent_growth", handoffs=[HandoffRequest(target_agent_id="agent_sales", reason="help")])
    challenger = _Challenger()
    arbiter = _verifier()
    result = _run(CollaborationSession(_registry(root, challenger, arbiter)).run("agent_growth", "goal"))

    assert [c["challenger"] for c in result.challenges] == ["agent_sales"]
    assert result.verifications, "a high-severity challenge must be arbitrated"
    verification = result.verifications[0]
    assert verification.verifier_agent_id == "agent_qualification"
    assert verification.challenged_agent_id == "agent_growth"
    assert "agent_qualification" in result.participants
    assert arbiter.saw_open_challenges[0], "the arbiter must receive the open challenge"
    assert arbiter.saw_open_challenges[0][0]["claim"].startswith("aggressive conversion")


def test_low_severity_challenge_is_recorded_without_arbitration():
    root = _Recorder("agent_growth", handoffs=[HandoffRequest(target_agent_id="agent_sales", reason="help")])
    challenger = _Challenger(severity="low")
    arbiter = _verifier()
    result = _run(CollaborationSession(_registry(root, challenger, arbiter)).run("agent_growth", "goal"))

    assert [c["severity"] for c in result.challenges] == ["low"]
    assert result.verifications == []
    assert arbiter.calls == 0, "low-severity doubt must not spend an agent"


def test_verification_is_refused_when_no_uninvolved_agent_exists():
    root = _Recorder("agent_growth", handoffs=[HandoffRequest(target_agent_id="agent_sales", reason="help")])
    challenger = _Challenger(severity="high")
    result = _run(CollaborationSession(_registry(root, challenger)).run("agent_growth", "goal"))

    assert result.verifications == []
    assert result.verification_refusals
    assert "no uninvolved agent available" in result.verification_refusals[0]["reason"]


def test_challenges_against_non_participants_and_self_are_refused():
    root = _Recorder("agent_growth", handoffs=[HandoffRequest(target_agent_id="agent_sales", reason="help")])
    ghost = _Challenger(target="agent_nowhere", severity="medium")
    itself = _Challenger(agent_id="agent_sales", target="agent_sales", severity="medium")
    result = _run(CollaborationSession(_registry(root, ghost)).run("agent_growth", "goal"))
    assert [r["reason"] for r in result.challenges_refused] == ["target has not participated"]

    result2 = _run(CollaborationSession(_registry(root, itself)).run("agent_growth", "goal"))
    assert "self-challenge" in [r["reason"] for r in result2.challenges_refused]


def test_sales_agent_contests_an_aggressive_play_on_an_at_risk_session():
    """The domain rule itself: retention risk + aggressive funnel = a recorded challenge."""
    sales = SalesAgent()
    output = _run(
        sales.process(
            AgentInput(
                goal="qualify",
                context={
                    "churn_risk": 0.82,
                    "peer_findings": [{"agent_id": "agent_growth", "decision": "OPTIMIZE_FUNNEL"}],
                },
                events=[],
            )
        )
    )
    assert output.challenges, "sales must contest pushing conversion on an at-risk session"
    assert output.challenges[0].target_agent_id == "agent_growth"
    assert output.challenges[0].severity == "high"


def test_challenge_rule_sees_churn_risk_nested_under_event_data():
    """FRIDAY promotes its context into event_data; the rule must look there too."""
    sales = SalesAgent()
    output = _run(
        sales.process(
            AgentInput(
                goal="qualify",
                context={
                    "event_data": {"churn_risk": 0.82},
                    "peer_findings": [{"agent_id": "agent_growth", "decision": "OPTIMIZE_FUNNEL"}],
                },
                events=[],
            )
        )
    )
    assert output.challenges and output.challenges[0].severity == "high"


def test_unknown_root_agent_raises_keyerror():
    with pytest.raises(KeyError):
        _run(CollaborationSession(_registry(_Recorder("agent_growth"))).run("agent_missing", "goal"))


def test_collaboration_is_reexported_from_the_package():
    assert SessionFromModule is CollaborationSession
