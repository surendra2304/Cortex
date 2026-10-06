"""Self-model, self-diagnosis and bounded self-modification ("the brain").

The first version of this module reported a fabricated self-awareness: a hardcoded
``capabilities`` dict where every subsystem was ``status="operational"`` and a confidence
of 0.99 regardless of what was actually running, plus a "learning" counter that only ever
counted calls to itself. That is worse than no self-model — an operator reading
``/v1/friday/self_model`` would be told everything is fine while nothing had been checked.

This version builds the self-model from observed state only:

* registration facts (what exists in this process),
* health signals (circuit breakers / probes, see ``cortex_core.resilience``),
* real usage counters (events, workflows, approvals, collaborations) when a DB session is
  supplied,
* explicit ``gaps`` — including "health has never been observed" for anything unprobed.

``diagnose`` turns that state into ranked findings with concrete suggestions, and
``evaluate_change`` gates self-modifications: only allow-listed, reversible, low-blast-radius
settings may be proposed, each with a rollback, and every application is recorded in an
inspectable history. High-impact mutation is refused and routed to human approval.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cortex_upgrade.runtime_knobs import RuntimeKnobs

logger = logging.getLogger("cortex-core.self_model")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SelfModificationAlreadyApplied(RuntimeError):
    """Raised when a change-set is applied twice (self-modification must be explicit)."""


@dataclass
class ChangeProposal:
    """One allow-listed runtime knob change, with its rollback."""

    knob: str
    proposed: Any
    rationale: str
    rollback: Any
    impact: str = "low"
    applied: bool = False
    previous: Any = None
    applied_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "knob": self.knob,
            "proposed": self.proposed,
            "previous": self.previous,
            "rationale": self.rationale,
            "rollback_value": self.rollback,
            "impact": self.impact,
            "applied": self.applied,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
        }


class SelfModificationEngine:
    """Applies only allow-listed, reversible runtime changes; everything else is escalated."""

    ALLOW_LIST: dict[str, dict[str, Any]] = {
        "self_healing_enabled": {
            "type": bool,
            "impact": "low",
            "reason": "toggles the local self-healing supervisor loop",
        },
        "self_healing_interval_seconds": {
            "type": int,
            "impact": "low",
            "reason": "poll interval for the supervisor (bounded 1..3600)",
            "min": 1,
            "max": 3600,
        },
        "max_collaboration_rounds": {
            "type": int,
            "impact": "low",
            "reason": "bounds multi-agent collaboration breadth (bounded 1..5)",
            "min": 1,
            "max": 5,
        },
    }

    def __init__(self, knobs: RuntimeKnobs | None = None) -> None:
        self.knobs = knobs or RuntimeKnobs()
        self.history: list[dict[str, Any]] = []
        self._applied: set[tuple[str, str]] = set()

    def evaluate(self, proposals: list[dict[str, Any]]) -> tuple[list[ChangeProposal], list[dict[str, str]]]:
        """Split proposals into (accepted, refused) without changing anything."""
        accepted: list[ChangeProposal] = []
        refused: list[dict[str, str]] = []
        for proposal in proposals:
            knob = str(proposal.get("knob", ""))
            spec = self.ALLOW_LIST.get(knob)
            if spec is None:
                refused.append({"knob": knob, "reason": "not on the self-modification allow-list"})
                continue
            value = proposal.get("value")
            if not isinstance(value, spec["type"]) or isinstance(value, bool) != (spec["type"] is bool):
                refused.append({"knob": knob, "reason": f"expected {spec['type'].__name__}"})
                continue
            if "min" in spec and not (spec["min"] <= value <= spec["max"]):
                refused.append({"knob": knob, "reason": f"out of range {spec['min']}..{spec['max']}"})
                continue
            current = self.knobs.get(knob, self.knobs.defaults.get(knob))
            if current == value:
                refused.append({"knob": knob, "reason": "already at the requested value"})
                continue
            accepted.append(
                ChangeProposal(
                    knob=knob,
                    proposed=value,
                    previous=current,
                    rollback=current,
                    rationale=str(proposal.get("rationale", "supervised self-modification")),
                    impact=spec["impact"],
                )
            )
        return accepted, refused

    def apply(self, proposals: list[ChangeProposal], db: AsyncSession | None = None) -> list[ChangeProposal]:
        applied: list[ChangeProposal] = []
        for proposal in proposals:
            signature = (proposal.knob, repr(proposal.proposed))
            if signature in self._applied:
                raise SelfModificationAlreadyApplied(f"{proposal.knob}={proposal.proposed!r} already applied")
            self.knobs.set(proposal.knob, proposal.proposed, rationale=proposal.rationale)
            proposal.applied = True
            proposal.applied_at = _utcnow()
            self._applied.add(signature)
            applied.append(proposal)
            self.history.append(proposal.as_dict())
            logger.info("self-modification applied: %s=%r (%s)", proposal.knob, proposal.proposed, proposal.rationale)
        return applied

    def rollback(self, knob: str) -> dict[str, Any]:
        """Undo the most recent application of a knob using its recorded rollback value."""
        for entry in reversed(self.history):
            # History also contains rollback records (which carry "restored", not "applied"):
            # using entry["applied"] here raised KeyError and made a second rollback impossible.
            if entry.get("knob") == knob and entry.get("applied"):
                self.knobs.set(knob, entry["rollback_value"], rationale="rollback")
                self._applied.discard((knob, repr(entry["proposed"])))
                entry["applied"] = False
                record = {"knob": knob, "restored": entry["rollback_value"], "at": _utcnow().isoformat()}
                self.history.append({"event": "rollback", **record})
                return record
        raise KeyError(f"no applied change for knob '{knob}'")


class SelfModel:
    """Builds an honest picture of this process from observed state."""

    def __init__(
        self,
        registry: Any | None = None,
        health: Any | None = None,
        supervisor: Any | None = None,
        engine: SelfModificationEngine | None = None,
    ) -> None:
        self.registry = registry
        self.health = health
        self.supervisor = supervisor
        self.engine = engine or SelfModificationEngine()

    def _registered_capabilities(self) -> dict[str, list[str]]:
        if self.registry is None:
            return {}
        capabilities: dict[str, list[str]] = {}
        for agent in getattr(self.registry, "_agents", {}).values():
            capabilities.setdefault(agent.agent_id, list(agent.capabilities))
        return capabilities

    async def build(self, db: AsyncSession | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        agents = self._registered_capabilities()

        health_snapshot = self.health.snapshot() if self.health is not None else {}
        subsystems = health_snapshot.get("subsystems", {})

        def subsystem_state(*names: str) -> tuple[str, list[str]]:
            """Map subsystems onto a state; anything without observations is 'unverified'.

            A fresh breaker is CLOSED by construction, so the breaker state alone proves
            nothing — this reads ``samples`` (observed outcomes) to separate "healthy" from
            "never looked at". Treating a default-CLOSED circuit as operational would be the
            same fabrication the rest of this module exists to prevent.
            """
            observed = [name for name in names if (subsystems.get(name, {}).get("samples") or 0) > 0]
            if not observed:
                return "unverified", [f"no health observation for {', '.join(names)} (run a probe)"]
            open_circuits = [name for name in observed if subsystems[name].get("state") == "OPEN"]
            if open_circuits:
                return "degraded", [f"circuit OPEN for {name}" for name in open_circuits]
            unobserved = [name for name in names if name not in observed]
            notes = [f"partially unobserved: {', '.join(unobserved)}"] if unobserved else []
            return "operational", notes

        capabilities: dict[str, dict[str, Any]] = {}
        gaps: list[str] = []

        state, notes = subsystem_state("ingestion", "database")
        capabilities["event_ingestion"] = {"state": state, "notes": notes}
        state, notes = subsystem_state("agents")
        capabilities["multi_agent_collaboration"] = {
            "state": state,
            "registered_agents": sorted(agents),
            "handoff_protocol": "handoff-v1 (bounded rounds, refusal on cycles)",
            "notes": notes,
        }
        state, notes = subsystem_state("tools")
        capabilities["tool_execution"] = {"state": state, "notes": notes}
        state, notes = subsystem_state("database")
        capabilities["persistence"] = {"state": state, "notes": notes}
        state, notes = subsystem_state("redis")
        capabilities["realtime_streaming"] = {"state": state, "notes": notes}
        state, notes = subsystem_state("ai_universe")
        capabilities["ai_universe_deliberation"] = {
            "state": state,
            "deterministic_fallback": True,
            "notes": notes,
        }

        capabilities["self_healing"] = {
            "state": "operational" if self.supervisor is not None else "unverified",
            "repairs_available": sorted(getattr(self.supervisor, "_repair_fns", {}).keys()) if self.supervisor else [],
            "escalations": len(getattr(self.supervisor, "escalations", [])),
        }
        capabilities["self_modification"] = {
            "state": "operational",
            "allow_list": sorted(self.engine.ALLOW_LIST),
            "history_entries": len(self.engine.history),
            "policy": "allow-listed, reversible, low-impact only; anything else requires human approval",
        }

        for name, info in capabilities.items():
            if info["state"] == "unverified":
                gaps.append(f"{name}: health has never been observed")

        usage: dict[str, Any] = {"available": False}
        if db is not None:
            from cortex_api.db_models import ApprovalQueueModel, EventModel, WorkflowRunModel

            try:
                events = (await db.execute(select(func.count()).select_from(EventModel))).scalar_one()
                workflows = (await db.execute(select(func.count()).select_from(WorkflowRunModel))).scalar_one()
                pending = (
                    await db.execute(
                        select(func.count())
                        .select_from(ApprovalQueueModel)
                        .where(ApprovalQueueModel.status == "pending")
                    )
                ).scalar_one()
                usage = {
                    "available": True,
                    "events_persisted": events,
                    "workflow_runs": workflows,
                    "pending_approvals": pending,
                    "measurement": "counted from the database, not estimated",
                }
            except Exception as exc:  # a broken measurement is reported, never guessed
                usage = {"available": False, "error": type(exc).__name__}

        return {
            "identity": {
                "service": "CORTEX",
                "role": "autonomous operational intelligence substrate (FRIDAY is the general OS above it)",
                "evidence_basis": "registration + observed health + persisted usage only",
                "observed_at": _utcnow().isoformat(),
            },
            "capabilities": capabilities,
            "gaps": gaps,
            "usage": usage,
            "pending_escalations": list(getattr(self.supervisor, "escalations", [])),
            "build_ms": round((time.perf_counter() - started) * 1000, 3),
        }

    async def diagnose(self, db: AsyncSession | None = None) -> dict[str, Any]:
        """Turn the self-model into ranked findings plus bounded suggestions."""
        model = await self.build(db=db)
        findings: list[dict[str, Any]] = []

        for name, info in model["capabilities"].items():
            if info["state"] == "degraded":
                findings.append(
                    {
                        "severity": "HIGH",
                        "subject": name,
                        "observation": "; ".join(info.get("notes") or ["degraded"]),
                        "suggestion": "inspect the breaker transitions and run the self-healing cycle",
                    }
                )
            elif info["state"] == "unverified":
                findings.append(
                    {
                        "severity": "MEDIUM",
                        "subject": name,
                        "observation": "never observed",
                        "suggestion": "register a probe so the system can tell up from unknown",
                    }
                )

        pending = model.get("usage", {}).get("pending_approvals")
        if isinstance(pending, int) and pending > 0:
            findings.append(
                {
                    "severity": "MEDIUM",
                    "subject": "approval_queue",
                    "observation": f"{pending} approvals pending",
                    "suggestion": "review pending approvals; automated actions stay blocked until decided",
                }
            )

        escalations = model.get("pending_escalations") or []
        if escalations:
            findings.append(
                {
                    "severity": "HIGH",
                    "subject": "self_healing",
                    "observation": f"{len(escalations)} subsystem(s) escalated after failed repairs",
                    "suggestion": "a human must inspect the escalated subsystems",
                    "escalations": escalations,
                }
            )

        return {
            "findings": findings,
            "summary": (
                "healthy" if not any(f["severity"] in {"HIGH", "CRITICAL"} for f in findings) else "attention_required"
            ),
            "model": model,
            "diagnosed_at": _utcnow().isoformat(),
        }
