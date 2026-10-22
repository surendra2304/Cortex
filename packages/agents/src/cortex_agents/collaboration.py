"""Multi-agent collaboration: handoffs, shared blackboard, and consensus.

CORTEX already had six specialist agents, but they could only ever work alone: the
cognitive loop routed one event to one agent and stopped. There was no way for the growth
agent to pull in sales, for support to escalate to reliability, or for two agents to
disagree on the record.

This module adds the missing layer, deterministically (no LLM required, so it is fully
testable and reproducible):

* ``HandoffRequest`` — an agent asks a peer for help, with a reason and the evidence that
  motivated it. ``AgentOutput.handoffs`` carries them.
* ``CollaborationSession`` — runs the requesting agent, executes its handoffs breadth-first
  under hard bounds (max rounds, max agents, one visit per agent, cycle refusal), and gives
  every participant the accumulated peer findings so it can actually *use* the help.
* Consensus — the session closes with an agreement/dissent record weighted by confidence,
  so disagreement is visible rather than averaged away.

Invariants:
  * No handoff can grant a capability the target does not already declare.
  * A handoff never authorises execution: all proposed actions still flow through the
    policy engine and approval gates.
  * Bounded work: rounds and participants are capped, and revisits are refused, so a
    handoff cycle cannot spin forever.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from . import AgentInput, AgentOutput, AgentRegistry, HandoffRequest, SpecialistAgent

logger = logging.getLogger("cortex-agents.collaboration")


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class CollaborationStep:
    agent_id: str
    domain: str
    round: int
    requested_by: str | None
    reason: str
    decision: str
    confidence: float
    proposed_actions: int
    handoffs_to: list[str]
    latency_ms: float
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "domain": self.domain,
            "round": self.round,
            "requested_by": self.requested_by,
            "reason": self.reason,
            "decision": self.decision,
            "confidence": self.confidence,
            "proposed_actions": self.proposed_actions,
            "handoffs_to": list(self.handoffs_to),
            "latency_ms": round(self.latency_ms, 3),
            "error": self.error,
        }


@dataclass
class Consensus:
    """Confidence-weighted agreement across participating agents."""

    decision: str
    agreement: float
    confidence: float
    agreeing: list[str] = field(default_factory=list)
    dissenting: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "agreement": round(self.agreement, 4),
            "confidence": round(self.confidence, 4),
            "agreeing": list(self.agreeing),
            "dissenting": list(self.dissenting),
            "unresolved_disagreements": list(self.unresolved),
        }


@dataclass
class Verification:
    """Outcome of asking an uninvolved peer to arbitrate a high-severity challenge."""

    challenged_agent_id: str
    challenger_agent_id: str
    verifier_agent_id: str
    verifier_decision: str
    upheld_leading_decision: bool
    claim: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "challenged_agent_id": self.challenged_agent_id,
            "challenger_agent_id": self.challenger_agent_id,
            "verifier_agent_id": self.verifier_agent_id,
            "verifier_decision": self.verifier_decision,
            "upheld_leading_decision": self.upheld_leading_decision,
            "claim": self.claim,
        }


@dataclass
class CollaborationResult:
    session_id: str
    root_agent_id: str
    goal: str
    transcript: list[CollaborationStep]
    consensus: Consensus
    outputs: dict[str, dict[str, Any]]
    rounds_used: int
    handoffs_executed: int
    handoffs_refused: list[dict[str, str]]
    participants: list[str]
    started_at: datetime
    duration_ms: float
    challenges: list[dict[str, Any]] = field(default_factory=list)
    challenges_refused: list[dict[str, str]] = field(default_factory=list)
    verifications: list[Verification] = field(default_factory=list)
    verification_refusals: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self, include_outputs: bool = True) -> dict[str, Any]:
        body: dict[str, Any] = {
            "session_id": self.session_id,
            "root_agent_id": self.root_agent_id,
            "goal": self.goal,
            "participants": list(self.participants),
            "challenges": list(self.challenges),
            "challenges_refused": list(self.challenges_refused),
            "verifications": [v.as_dict() for v in self.verifications],
            "verification_refusals": list(self.verification_refusals),
            "rounds_used": self.rounds_used,
            "handoffs_executed": self.handoffs_executed,
            "handoffs_refused": list(self.handoffs_refused),
            "consensus": self.consensus.as_dict(),
            "transcript": [step.as_dict() for step in self.transcript],
            "started_at": self.started_at.isoformat(),
            "duration_ms": round(self.duration_ms, 3),
        }
        if include_outputs:
            body["outputs"] = self.outputs
        return body


class CollaborationSession:
    """Runs one bounded multi-agent collaboration."""

    def __init__(
        self,
        registry: AgentRegistry,
        max_rounds: int = 3,
        max_agents: int = 5,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.registry = registry
        self.max_rounds = max(1, max_rounds)
        self.max_agents = max(1, max_agents)
        self.timeout_seconds = timeout_seconds

    # ── planning ────────────────────────────────────────────────────────────
    def _resolve(self, identifier: str) -> SpecialistAgent | None:
        return self.registry.get(identifier)

    def _authorise_handoff(
        self, requester: SpecialistAgent, request: HandoffRequest
    ) -> tuple[SpecialistAgent | None, str]:
        """Resolve the target and refuse unsafe or impossible handoffs."""
        target = self._resolve(request.target_agent_id)
        if target is None:
            return None, f"unknown agent '{request.target_agent_id}'"
        if target.agent_id == requester.agent_id:
            return None, "self-handoff"
        return target, ""

    @staticmethod
    def _consensus(outputs: list[tuple[SpecialistAgent, AgentOutput]]) -> Consensus:
        """Confidence-weighted vote over the participants' decisions."""
        if not outputs:
            return Consensus(decision="NO_CONSENSUS", agreement=0.0, confidence=0.0)

        weights: dict[str, float] = {}
        by_decision: dict[str, list[str]] = {}
        for agent, output in outputs:
            weights[output.decision] = weights.get(output.decision, 0.0) + max(0.0, output.confidence)
            by_decision.setdefault(output.decision, []).append(agent.agent_id)

        decision = max(weights, key=lambda key: (weights[key], key))
        total = sum(weights.values()) or 1.0
        agreeing = by_decision[decision]
        dissenting = [agent_id for ids in by_decision.values() for agent_id in ids if agent_id not in agreeing]
        confidence = sum(o.confidence for a, o in outputs if o.decision == decision) / len(agreeing)

        unresolved = [f"{a.agent_id}:{o.decision}" for a, o in outputs if o.decision != decision]
        return Consensus(
            decision=decision,
            agreement=weights[decision] / total,
            confidence=confidence,
            agreeing=agreeing,
            dissenting=dissenting,
            unresolved=unresolved,
        )

    def _pick_verifier(self, visited: set[str], excluded: set[str]) -> SpecialistAgent | None:
        """An agent that has not spoken yet and is not one of the two parties."""
        agents = {agent.agent_id: agent for agent in self.registry._agents.values()}  # noqa: SLF001 - registry contract
        for agent_id in sorted(agents):
            if agent_id in visited or agent_id in excluded:
                continue
            return agents[agent_id]
        return None

    # ── execution ───────────────────────────────────────────────────────────
    async def run(
        self,
        root_agent_id: str,
        goal: str,
        context: dict[str, Any] | None = None,
        events: list[dict[str, Any]] | None = None,
        identity_scope: dict[str, Any] | None = None,
        root_output: AgentOutput | None = None,
    ) -> CollaborationResult:
        """Run a bounded session.

        ``root_output`` lets a caller that has already asked the lead agent (the orchestrator
        does, in its Understand/Plan phase) hand that result in instead of paying for a second
        call: the session then only executes the handoffs the lead actually requested.
        """
        started_at = _utcnow()
        started = time.perf_counter()
        session_id = f"collab_{uuid.uuid4().hex[:10]}"

        root = self._resolve(root_agent_id)
        if root is None:
            raise KeyError(f"Agent '{root_agent_id}' not found in registry")

        transcript: list[CollaborationStep] = []
        outputs_by_agent: dict[str, tuple[SpecialistAgent, AgentOutput]] = {}
        peer_findings: list[dict[str, Any]] = []
        refused: list[dict[str, str]] = []
        visited: set[str] = {root.agent_id}
        handoffs_executed = 0
        challenges: list[dict[str, Any]] = []
        challenges_refused: list[dict[str, str]] = []
        verifications: list[Verification] = []
        verification_refusals: list[dict[str, str]] = []
        pending_verifications: list[dict[str, str]] = []
        open_challenges: list[dict[str, Any]] = []

        # frontier of (agent, requested_by, reason, round)
        frontier: list[tuple[SpecialistAgent, str | None, str, int]] = [(root, None, "root request", 1)]
        rounds_used = 0

        while frontier:
            if time.perf_counter() - started > self.timeout_seconds:
                refused.append({"target": "*", "reason": "collaboration timeout"})
                break
            if len(visited) >= self.max_agents:
                refused.append({"target": "*", "reason": f"max_agents={self.max_agents} reached"})
                break

            agent, requested_by, reason, round_number = frontier.pop(0)
            rounds_used = max(rounds_used, round_number)

            context_for_agent = dict(context or {})
            # Agents actually receive peer help: earlier findings are handed over.
            context_for_agent["peer_findings"] = list(peer_findings)
            context_for_agent["collaboration_session_id"] = session_id
            if open_challenges:
                context_for_agent["open_challenges"] = list(open_challenges)

            agent_input = AgentInput(
                goal=goal,
                context=context_for_agent,
                events=list(events or []),
                identity_scope=dict(identity_scope or {}),
                allowed_capabilities=list(agent.capabilities),
            )

            step_started = time.perf_counter()
            error: str | None = None
            precomputed = root_output if (requested_by is None and root_output is not None) else None
            try:
                output = precomputed if precomputed is not None else await agent.process(agent_input)
            except Exception as exc:  # one failing agent must not sink the session
                logger.warning("Agent %s failed during collaboration: %s", agent.agent_id, exc)
                error = f"{type(exc).__name__}: {exc}"
                output = AgentOutput(
                    agent_id=agent.agent_id,
                    decision="AGENT_ERROR",
                    reasoning_summary=f"{agent.agent_id} failed: {error}",
                    confidence=0.0,
                    evidence_refs=[f"error={error}"],
                )

            outputs_by_agent[agent.agent_id] = (agent, output)
            peer_findings.append(
                {
                    "agent_id": agent.agent_id,
                    "domain": agent.domain,
                    "decision": output.decision,
                    "confidence": output.confidence,
                    "reasoning": output.reasoning_summary,
                    "evidence_refs": output.evidence_refs,
                    "dissent": output.dissent,
                }
            )

            next_round = round_number + 1
            # A peer may contest another participant's claim. Challenges against an
            # already-recorded decision by a high-severity reason are arbitrated by an
            # uninvolved peer (bounded exactly like handoffs: one visit, capped rounds).
            for challenge in list(getattr(output, "challenges", []) or []):
                target_id = getattr(challenge, "target_agent_id", "")
                claim = getattr(challenge, "claim", "")
                severity = getattr(challenge, "severity", "medium")
                if target_id == agent.agent_id:
                    challenges_refused.append({"target": target_id, "reason": "self-challenge"})
                    continue
                if target_id not in {step.agent_id for step in transcript} and target_id != root.agent_id:
                    challenges_refused.append({"target": target_id, "reason": "target has not participated"})
                    continue
                challenges.append(
                    {
                        "challenger": agent.agent_id,
                        "target": target_id,
                        "claim": claim,
                        "reason": getattr(challenge, "reason", ""),
                        "severity": severity,
                    }
                )
                peer_findings.append(
                    {
                        "agent_id": agent.agent_id,
                        "domain": agent.domain,
                        "decision": f"CHALLENGE:{target_id}",
                        "confidence": output.confidence,
                        "reasoning": getattr(challenge, "reason", ""),
                        "evidence_refs": [claim] if claim else [],
                        "dissent": None,
                    }
                )
                if severity != "high":
                    continue
                verifier = self._pick_verifier(visited, {target_id, agent.agent_id})
                if verifier is None:
                    verification_refusals.append(
                        {"target": target_id, "reason": "no uninvolved agent available to arbitrate"}
                    )
                    continue
                if next_round > self.max_rounds:
                    verification_refusals.append({"target": target_id, "reason": "max_rounds reached"})
                    continue
                if len(visited) >= self.max_agents:
                    verification_refusals.append(
                        {"target": target_id, "reason": f"max_agents={self.max_agents} reached"}
                    )
                    continue
                visited.add(verifier.agent_id)
                pending_verifications.append(
                    {
                        "challenged": target_id,
                        "challenger": agent.agent_id,
                        "verifier": verifier.agent_id,
                        "claim": claim,
                    }
                )
                open_challenges.append(
                    {
                        "challenger": agent.agent_id,
                        "target": target_id,
                        "claim": claim,
                        "reason": getattr(challenge, "reason", ""),
                        "severity": severity,
                    }
                )
                frontier.append((verifier, agent.agent_id, f"verify challenge by {agent.agent_id}", next_round))

            handoffs = list(getattr(output, "handoffs", []) or [])
            targets: list[str] = []
            for request in handoffs:
                if next_round > self.max_rounds:
                    refused.append({"target": request.target_agent_id, "reason": "max_rounds reached"})
                    continue
                target, refusal = self._authorise_handoff(agent, request)
                if target is None:
                    refused.append({"target": request.target_agent_id, "reason": refusal})
                    continue
                if target.agent_id in visited:
                    refused.append({"target": request.target_agent_id, "reason": "already participated"})
                    continue
                visited.add(target.agent_id)
                handoffs_executed += 1
                targets.append(target.agent_id)
                frontier.append(
                    (target, agent.agent_id, request.reason or request.question or "peer request", next_round)
                )

            if requested_by is not None:
                for pending in [p for p in pending_verifications if p["verifier"] == agent.agent_id]:
                    verifications.append(
                        Verification(
                            challenged_agent_id=pending["challenged"],
                            challenger_agent_id=pending["challenger"],
                            verifier_agent_id=agent.agent_id,
                            verifier_decision=output.decision,
                            upheld_leading_decision=output.decision != "CHALLENGE_UPHELD",
                            claim=pending["claim"],
                        )
                    )
                    pending_verifications = [p for p in pending_verifications if p["verifier"] != agent.agent_id]

            transcript.append(
                CollaborationStep(
                    agent_id=agent.agent_id,
                    domain=agent.domain,
                    round=round_number,
                    requested_by=requested_by,
                    reason=reason,
                    decision=output.decision,
                    confidence=output.confidence,
                    proposed_actions=len(output.proposed_actions),
                    handoffs_to=targets,
                    latency_ms=(time.perf_counter() - step_started) * 1000,
                    error=error,
                )
            )

        ordered_outputs = [outputs_by_agent[step.agent_id] for step in transcript]
        consensus = self._consensus(ordered_outputs)

        return CollaborationResult(
            session_id=session_id,
            root_agent_id=root.agent_id,
            goal=goal,
            transcript=transcript,
            consensus=consensus,
            outputs={agent_id: output.model_dump(mode="json") for agent_id, (_, output) in outputs_by_agent.items()},
            rounds_used=rounds_used,
            handoffs_executed=handoffs_executed,
            handoffs_refused=refused,
            participants=list(dict.fromkeys(step.agent_id for step in transcript)),
            started_at=started_at,
            duration_ms=(time.perf_counter() - started) * 1000,
            challenges=challenges,
            challenges_refused=challenges_refused,
            verifications=verifications,
            verification_refusals=verification_refusals,
        )
