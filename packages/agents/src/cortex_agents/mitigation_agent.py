"""Proactive Anomaly Mitigation & Resilient Self-Healing Agent for CORTEX.

Monitors runtime signals, Sentinel threat intelligence, and error rate surges:
- Triages DDoS, credential stuffing, and scraping anomalies
- Triggers upstream circuit breakers and automated traffic throttling during surges
- Adjusts dynamic rate-limit thresholds to shield database and worker pools
- Contests marketing campaign launches during active infrastructure degradation
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


class ProactiveMitigationAgent(SpecialistAgent):
    """Governs self-healing mitigation, circuit tripping, and adaptive rate limits."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="agent_mitigation",
            domain="mitigation",
            capabilities=[
                "circuit_trip",
                "traffic_throttle",
                "rate_limit_mutate",
                "cache_evict",
            ],
        )

    async def process(self, input_data: AgentInput) -> AgentOutput:
        events = input_data.events or []
        context = input_data.context or {}
        telemetry = context.get("telemetry", {})
        sentinel_signals = context.get("sentinel_signals", {})

        error_5xx_rate = float(telemetry.get("error_rate_5xx_pct", 0.0))
        qps = float(telemetry.get("requests_per_sec", 0.0))
        threat_level = str(sentinel_signals.get("threat_level", "nominal")).lower()
        brute_force_ips = sentinel_signals.get("brute_force_ips", [])

        # Count 5xx error events
        error_5xx_events = [
            e for e in events
            if "500" in str(e.get("data", {}))
            or "502" in str(e.get("data", {}))
            or "503" in str(e.get("data", {}))
            or "504" in str(e.get("data", {}))
            or e.get("type", "").lower() == "server_error"
        ]

        evidence = [
            f"error_rate_5xx_pct={error_5xx_rate}%",
            f"requests_per_sec={qps}",
            f"threat_level={threat_level}",
            f"brute_force_ips_count={len(brute_force_ips)}",
            f"recent_5xx_events={len(error_5xx_events)}",
        ]

        actions: list[ProposedAction] = []
        handoffs: list[HandoffRequest] = []
        challenges: list[ChallengeNote] = []

        if threat_level in {"critical", "high"} or error_5xx_rate >= 25.0:
            decision = "TRIGGER_EMERGENCY_THROTTLE"
            reasoning = (
                f"Severe degradation / threat detected: threat_level='{threat_level}', "
                f"error_5xx={error_5xx_rate}%. Tripping non-essential circuits and shedding traffic."
            )
            actions.append(
                ProposedAction(
                    action_type="traffic_throttle",
                    target="ingress_gateway",
                    params={"throttle_pct": 50, "shed_non_essential": True},
                    rationale="Shed non-essential load to protect core database and session telemetry.",
                    side_effect_level="HIGH_IMPACT",
                )
            )
            actions.append(
                ProposedAction(
                    action_type="circuit_trip",
                    target="external_integrations",
                    params={"circuit_name": "ai_universe_adapter", "duration_seconds": 60},
                    rationale="Trip failing upstream AI adapter to stop cascading timeouts.",
                    side_effect_level="HIGH_IMPACT",
                )
            )
            handoffs.append(
                HandoffRequest(
                    target_agent_id="agent_reliability",
                    reason="Emergency throttle applied due to severe degradation",
                    question="Which backend pods or connection pools are degrading?",
                    priority="urgent",
                    payload={"error_rate": error_5xx_rate, "threat_level": threat_level},
                )
            )
            # Challenge any growth promotions
            challenges.append(
                ChallengeNote(
                    target_agent_id="agent_growth",
                    claim="funnel traffic acceleration during degradation",
                    reason="System under active threat/degradation; marketing traffic acceleration must be held.",
                    severity="high",
                )
            )
            confidence = 0.99

        elif brute_force_ips or threat_level == "elevated":
            decision = "TIGHTEN_RATE_LIMITS"
            reasoning = (
                f"Elevated risk: {len(brute_force_ips)} abusive IPs flagged by Sentinel. "
                "Tightening per-IP request rate limits."
            )
            actions.append(
                ProposedAction(
                    action_type="rate_limit_mutate",
                    target="rate_limiter",
                    params={"ip_list": brute_force_ips, "burst_limit": 5, "rate_per_min": 10},
                    rationale="Quarantine abusive IP blocks and enforce strict rate caps.",
                    side_effect_level="HIGH_IMPACT",
                )
            )
            confidence = 0.94

        else:
            decision = "HEALTHY_STEADY_STATE"
            reasoning = f"Nominal operations: 5xx_error_rate={error_5xx_rate}%, threat='{threat_level}'."
            confidence = 0.98

        return AgentOutput(
            agent_id=self.agent_id,
            decision=decision,
            reasoning_summary=reasoning,
            confidence=confidence,
            evidence_refs=evidence,
            proposed_actions=actions,
            expected_outcomes={"decision": decision, "throttling_active": decision == "TRIGGER_EMERGENCY_THROTTLE"},
            handoffs=handoffs,
            challenges=challenges,
            created_at=_utcnow(),
        )
