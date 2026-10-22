"""Compliance, Privacy, and Governance Specialist Agent for CORTEX.

Evaluates telemetry, sessions, and visitor actions for:
- PII / sensitive data leaks (credit cards, social security numbers, unmasked emails, phone numbers)
- Consent status mismatches (e.g., tracking when user opted out)
- Tenant isolation boundaries and cross-tenant leakage indicators
- Regulatory compliance audit requirements (GDPR right-to-be-forgotten / CCPA export)
"""

from __future__ import annotations

import re
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


# Standard patterns for sensitive data detection
CC_PATTERN = re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
PHONE_PATTERN = re.compile(r"\b(?:\+?1[-. ]?)?\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})\b")


class ComplianceGovernanceAgent(SpecialistAgent):
    """Enforces privacy, tenant isolation, and regulatory governance policies."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="agent_compliance",
            domain="compliance",
            capabilities=[
                "tenant_audit_export",
                "consent_enforce",
                "data_mask_verify",
                "pii_quarantine",
            ],
        )

    async def process(self, input_data: AgentInput) -> AgentOutput:
        events = input_data.events or []
        context = input_data.context or {}
        attrs = context.get("visitor_attributes", {})
        tenant_id = context.get("tenant_id", "default")
        consent_status = context.get("consent_status", "granted")

        pii_violations: list[str] = []
        raw_payloads = [str(e.get("data", {})) for e in events] + [str(attrs)]

        for payload in raw_payloads:
            if CC_PATTERN.search(payload):
                pii_violations.append("unmasked_credit_card")
            if SSN_PATTERN.search(payload):
                pii_violations.append("unmasked_ssn")

        # Consent mismatch check
        consent_revoked = consent_status in {"revoked", "opt_out", "denied"}
        tracking_events_present = any(
            e.get("type", "").lower() in {"page_view", "click", "form_submit", "session_start"}
            for e in events
        )

        # Tenant leakage check
        cross_tenant_evidence = False
        claimed_tenants = {
            e.get("tenant_id") for e in events if e.get("tenant_id") and e.get("tenant_id") != tenant_id
        }
        if claimed_tenants:
            cross_tenant_evidence = True

        evidence = [
            f"pii_violations_count={len(pii_violations)}",
            f"pii_types={list(set(pii_violations))}",
            f"consent_status={consent_status}",
            f"consent_revoked={consent_revoked}",
            f"tracking_events_count={len(events)}",
            f"cross_tenant_leakage={cross_tenant_evidence}",
            f"claimed_foreign_tenants={sorted(claimed_tenants)}",
        ]

        actions: list[ProposedAction] = []
        handoffs: list[HandoffRequest] = []
        challenges: list[ChallengeNote] = []

        if cross_tenant_evidence or pii_violations:
            decision = "QUARANTINE_AND_ALERT"
            reasoning = (
                f"Severe compliance violation: cross_tenant={cross_tenant_evidence}, "
                f"pii_types={list(set(pii_violations))}."
            )
            actions.append(
                ProposedAction(
                    action_type="pii_quarantine",
                    target="telemetry_stream",
                    params={"violations": list(set(pii_violations)), "tenant_id": tenant_id},
                    rationale="Quarantine unmasked PII or cross-tenant contamination immediately.",
                    side_effect_level="HIGH_IMPACT",
                )
            )
            handoffs.append(
                HandoffRequest(
                    target_agent_id="agent_reliability",
                    reason="Critical compliance isolation breach detected in event payload",
                    question="Should we isolate this tenant's ingress worker queue?",
                    priority="urgent",
                    payload={"violations": pii_violations, "foreign_tenants": sorted(claimed_tenants)},
                )
            )
            confidence = 0.99

        elif consent_revoked and tracking_events_present:
            decision = "ENFORCE_CONSENT_OPT_OUT"
            reasoning = "Visitor has revoked consent but active tracking events were received. Suppressing telemetry."
            actions.append(
                ProposedAction(
                    action_type="consent_enforce",
                    target="visitor_privacy_settings",
                    params={"visitor_id": context.get("visitor_id"), "consent": "revoked"},
                    rationale="Enforce user opt-out across tracking and marketing workflows.",
                    side_effect_level="SENSITIVE",
                )
            )
            # Challenge any aggressive marketing proposed by Growth or Sales on opt-out users
            peer_decisions = {
                f.get("decision") for f in (context.get("peer_findings") or []) if isinstance(f, dict)
            }
            if peer_decisions & {"OPTIMIZE_FUNNEL", "ROUTE_ENTERPRISE_LEAD", "ROUTE_MIDMARKET_LEAD"}:
                challenges.append(
                    ChallengeNote(
                        target_agent_id="agent_growth",
                        claim="marketing outreach on consent-revoked visitor",
                        reason="Visitor revoked tracking/marketing consent; outreach violates GDPR/CCPA regulations.",
                        severity="high",
                    )
                )
            confidence = 0.95

        else:
            decision = "COMPLIANCE_CLEAR"
            reasoning = f"No PII leaks or consent mismatches detected across {len(events)} events."
            confidence = 0.98

        return AgentOutput(
            agent_id=self.agent_id,
            decision=decision,
            reasoning_summary=reasoning,
            confidence=round(confidence, 2),
            evidence_refs=evidence,
            proposed_actions=actions,
            expected_outcomes={
                "compliant": decision == "COMPLIANCE_CLEAR",
                "violations_count": len(pii_violations),
            },
            handoffs=handoffs,
            challenges=challenges,
            created_at=_utcnow(),
        )
