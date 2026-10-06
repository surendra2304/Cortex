import abc
from datetime import UTC, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Timezone-aware UTC now (never a naive timestamp)."""
    return datetime.now(UTC)


class AgentInput(BaseModel):
    goal: str = Field(..., description="Primary objective or trigger purpose")
    context: dict[str, Any] = Field(default_factory=dict, description="Session, visitor, tenant state")
    events: list[dict[str, Any]] = Field(default_factory=list, description="Recent telemetry stream events")
    identity_scope: dict[str, Any] = Field(default_factory=dict, description="Visitor/User identity parameters")
    allowed_capabilities: list[str] = Field(default_factory=list, description="Permitted action types")
    policy_constraints: list[str] = Field(default_factory=list, description="Hard safety boundaries")
    evidence_requirements: list[str] = Field(default_factory=list, description="Required evidence keys")
    budget: dict[str, Any] = Field(default_factory=lambda: {"max_steps": 5, "timeout_seconds": 10})


class ProposedAction(BaseModel):
    action_type: str
    target: str
    params: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    side_effect_level: str = "READ"


class HandoffRequest(BaseModel):
    """A request for a peer agent's help (multi-agent collaboration protocol).

    Emitted on ``AgentOutput.handoffs``. It is a request, never an authorisation: the
    collaboration session still routes any resulting action through policy and approvals.
    """

    target_agent_id: str = Field(..., description="Registry id or domain of the peer")
    reason: str = Field(..., description="Why the peer's judgement is needed")
    question: str = Field(default="", description="The specific question for the peer")
    priority: str = Field(default="normal", description="normal | high | urgent")
    payload: dict[str, Any] = Field(default_factory=dict, description="Evidence handed over")


class ChallengeNote(BaseModel):
    """A peer contesting another agent's claim, with the reason it should not stand."""

    target_agent_id: str = Field(..., description="Agent whose claim is being contested")
    claim: str = Field(..., description="The specific claim under dispute")
    reason: str = Field(..., description="Why the claim is doubted (evidence, counter-signal)")
    severity: Literal["low", "medium", "high"] = Field(
        default="medium", description="high triggers an arbitration pass by an uninvolved agent"
    )


class AgentOutput(BaseModel):
    agent_id: str
    decision: str
    reasoning_summary: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)
    dissent: str | None = None
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    required_approvals: list[str] = Field(default_factory=list)
    expected_outcomes: dict[str, Any] = Field(default_factory=dict)
    handoffs: list[HandoffRequest] = Field(default_factory=list, description="Peers whose judgement this agent needs")
    challenges: list[ChallengeNote] = Field(
        default_factory=list, description="Peer claims this agent disputes, with the reason"
    )
    created_at: datetime = Field(default_factory=_utcnow)


class SpecialistAgent(abc.ABC):
    def __init__(self, agent_id: str, domain: str, capabilities: list[str]):
        self.agent_id = agent_id
        self.domain = domain
        self.capabilities = capabilities

    @abc.abstractmethod
    async def process(self, input_data: AgentInput) -> AgentOutput:
        pass


class GrowthAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(
            agent_id="agent_growth", domain="growth", capabilities=["experiment_mutate", "banner_injection"]
        )

    async def process(self, input_data: AgentInput) -> AgentOutput:
        events = input_data.events or []
        context = input_data.context or {}
        session = context.get("session_summary", {})

        # ContextBuilder publishes these as "pricing_views"/"demo_views"; older callers used
        # "_view_count" names. Accept both, otherwise the pre-aggregated session context was
        # silently ignored and intent was recomputed from the event window alone.
        pricing_views = session.get("pricing_views", session.get("pricing_view_count"))
        if pricing_views is None:
            pricing_views = sum(
                1
                for e in events
                if "pricing" in e.get("type", "").lower() or "pricing" in str(e.get("data", {})).lower()
            )

        demo_views = session.get("demo_views", session.get("demo_view_count"))
        if demo_views is None:
            demo_views = sum(
                1 for e in events if "demo" in e.get("type", "").lower() or "demo" in str(e.get("data", {})).lower()
            )

        enterprise_views = sum(
            1
            for e in events
            if any(
                k in e.get("type", "").lower() or k in str(e.get("data", {})).lower()
                for k in ["enterprise", "security", "compliance"]
            )
        )
        page_depth = session.get("pages_viewed", len([e for e in events if "page_view" in e.get("type", "").lower()]))
        exit_intent = any("exit" in e.get("type", "").lower() for e in events) or session.get(
            "exit_intent_detected", False
        )

        raw_score = (
            (pricing_views * 0.35) + (demo_views * 0.40) + (enterprise_views * 0.10) + min(page_depth * 0.02, 0.15)
        )
        intent_score = round(min(raw_score, 1.0), 2)

        evidence = [
            f"pricing_views={pricing_views}",
            f"demo_views={demo_views}",
            f"enterprise_views={enterprise_views}",
            f"page_depth={page_depth}",
            f"exit_intent={exit_intent}",
            f"intent_score={intent_score}",
        ]

        if intent_score > 0.7:
            decision = "OPTIMIZE_FUNNEL"
            reasoning = f"High intent detected ({intent_score=}, {pricing_views=}, {demo_views=}). Proposing high-impact conversion banner."
            actions = [
                ProposedAction(
                    action_type="banner_injection",
                    target="pricing_cta",
                    params={"variant": "aggressive_cta", "discount_pct": 20, "intent_score": intent_score},
                    rationale="High purchase intent visitor requires decisive CTA to close.",
                    side_effect_level="HIGH_IMPACT",
                )
            ]
            confidence = min(0.95, 0.7 + (intent_score * 0.25))
        elif intent_score >= 0.4:
            decision = "OPTIMIZE_FUNNEL"
            reasoning = (
                f"Moderate intent detected ({intent_score=}, {page_depth=}). Offering educational soft touchpoint."
            )
            actions = [
                ProposedAction(
                    action_type="banner_injection",
                    target="content_footer",
                    params={"variant": "soft_cta", "guide": "roi_calculator"},
                    rationale="Nurture moderate engagement visitor without aggressive sales friction.",
                    side_effect_level="HIGH_IMPACT",
                )
            ]
            confidence = 0.75
        else:
            decision = "NO_ACTION"
            reasoning = (
                f"Low intent detected ({intent_score=}, {page_depth=}). Suppressing banner to avoid user fatigue."
            )
            actions = []
            confidence = 0.90

        return AgentOutput(
            agent_id=self.agent_id,
            decision=decision,
            reasoning_summary=reasoning,
            confidence=round(confidence, 2),
            evidence_refs=evidence,
            proposed_actions=actions,
            expected_outcomes={"intent_score": intent_score, "actions_proposed": len(actions)},
            handoffs=(
                [
                    HandoffRequest(
                        target_agent_id="agent_sales",
                        reason=f"High purchase intent ({intent_score}) needs a commercial owner",
                        question="Is this visitor qualified for direct sales contact, and via which channel?",
                        priority="high" if intent_score > 0.85 else "normal",
                        payload={
                            "intent_score": intent_score,
                            "pricing_views": pricing_views,
                            "demo_views": demo_views,
                        },
                    )
                ]
                if intent_score > 0.7
                else (
                    [
                        HandoffRequest(
                            target_agent_id="agent_support",
                            reason="Exit-intent detected on a funnel page; possible journey friction",
                            question="Did this session hit errors or support-worthy friction?",
                            priority="normal",
                            payload={"exit_intent": exit_intent, "page_depth": page_depth},
                        )
                    ]
                    if exit_intent
                    else []
                )
            ),
        )


class SalesAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(
            agent_id="agent_sales", domain="sales", capabilities=["email_dispatch", "account_update", "crm_tool"]
        )

    async def process(self, input_data: AgentInput) -> AgentOutput:
        events = input_data.events or []
        context = input_data.context or {}
        attrs = context.get("visitor_attributes", {})
        session = context.get("session_summary", {})

        pricing_views = session.get(
            "pricing_views",
            session.get("pricing_view_count", sum(1 for e in events if "pricing" in e.get("type", "").lower())),
        )
        demo_views = session.get(
            "demo_views", session.get("demo_view_count", sum(1 for e in events if "demo" in e.get("type", "").lower()))
        )
        intent_score = min((pricing_views * 0.15 + demo_views * 0.25), 0.40)

        email = attrs.get("email", "") or context.get("profile_email", "") or ""
        company = attrs.get("company", "") or ""
        enterprise_domains = ["corp.com", "enterprise", "inc.com", "ltd.com", ".gov", ".edu", "tech.co"]

        is_enterprise_domain = any(d in email.lower() for d in enterprise_domains) or bool(company and len(company) > 3)
        if is_enterprise_domain:
            firmographic_score = 0.30
        elif (
            email
            and "@" in email
            and not any(free in email.lower() for free in ["gmail.com", "yahoo.com", "hotmail.com"])
        ):
            firmographic_score = 0.20
        elif email:
            firmographic_score = 0.10
        else:
            firmographic_score = 0.0

        event_count = len(events)
        recency_score = min(event_count * 0.04, 0.20)

        source = context.get("event_data", {}).get("source", "") or attrs.get("source", "")
        source_score = 0.10 if source.lower() in ("direct", "referral", "linkedin", "organic_search") else 0.05

        lead_score = round(intent_score + firmographic_score + recency_score + source_score, 2)

        # Retention-risk signals observed in the telemetry (churn handoff trigger).
        retention_terms = ("cancel", "refund", "downgrade", "unsubscribe", "churn", "billing_issue")
        churn_signal = bool(context.get("churn_risk")) or any(
            term in f"{e.get('type', '')} {e.get('data', '')}".lower() for e in events for term in retention_terms
        )

        evidence = [
            f"intent_component={round(intent_score, 2)}",
            f"firmographic_component={round(firmographic_score, 2)}",
            f"recency_component={round(recency_score, 2)}",
            f"source_component={round(source_score, 2)}",
            f"email_present={bool(email)}",
            f"lead_score={lead_score}",
            f"retention_risk_signal={churn_signal}",
        ]

        if lead_score > 0.8:
            decision = "ROUTE_ENTERPRISE_LEAD"
            reasoning = f"High value enterprise lead ({lead_score=}, email={email or 'anonymous'}). Routing to enterprise tier 1 queue."
            actions = [
                ProposedAction(
                    action_type="account_update",
                    target="lead_qualification",
                    params={"tier": "enterprise_tier_1", "assigned_rep": "enterprise_team", "lead_score": lead_score},
                    rationale="High lead score and strong enterprise signals qualify for tier 1 SLA.",
                    side_effect_level="SENSITIVE",
                )
            ]
        elif lead_score >= 0.5:
            decision = "ROUTE_MIDMARKET_LEAD"
            reasoning = f"Qualified mid-market lead ({lead_score=}). Assigning mid-market sequence."
            actions = [
                ProposedAction(
                    action_type="account_update",
                    target="lead_qualification",
                    params={"tier": "midmarket_tier_2", "assigned_rep": "inbound_sales", "lead_score": lead_score},
                    rationale="Moderate lead score qualifies for mid-market inbound workflow.",
                    side_effect_level="SENSITIVE",
                )
            ]
        else:
            decision = "NURTURE_LEAD"
            reasoning = f"Early stage visitor ({lead_score=}). Keeping in automated nurture loop."
            actions = []

        # Domain rule: pushing an aggressive conversion play on a session that is already
        # showing retention risk is a contradiction worth contesting on the record.
        # FRIDAY context arrives nested under event_data, while the collaboration board
        # arrives at the top level — look in both before concluding there is no signal.
        event_data = context.get("event_data") or {}
        churn_candidates = [
            context.get("churn_risk"),
            (context.get("signals") or {}).get("churn_risk"),
            event_data.get("churn_risk"),
            (event_data.get("signals") or {}).get("churn_risk"),
        ]
        churn_risk = float(next((value for value in churn_candidates if value is not None), 0.0) or 0.0)
        peer_decisions = {
            finding.get("decision") for finding in (context.get("peer_findings") or []) if isinstance(finding, dict)
        }
        aggressive_plays = {"OPTIMIZE_FUNNEL", "AGGRESSIVE_BANNER", "OFFER_DISCOUNT"}
        challenges = (
            [
                ChallengeNote(
                    target_agent_id="agent_growth",
                    claim="aggressive conversion play on a retention-risk session",
                    reason=(
                        f"churn_risk={churn_risk} with peer decision(s) {sorted(peer_decisions & aggressive_plays)}; "
                        "pushing conversion before retention is resolved risks losing the account"
                    ),
                    severity="high",
                )
            ]
            if churn_risk >= 0.7 and (peer_decisions & aggressive_plays)
            else []
        )

        return AgentOutput(
            agent_id=self.agent_id,
            decision=decision,
            reasoning_summary=reasoning,
            confidence=min(0.99, max(0.50, lead_score)),
            evidence_refs=evidence,
            proposed_actions=actions,
            expected_outcomes={"lead_score": lead_score, "assigned_tier": decision},
            handoffs=(
                [
                    HandoffRequest(
                        target_agent_id="agent_churn_risk",
                        reason="Lead shows retention risk signals; needs a churn assessment before outreach",
                        question="How at-risk is this account, and what is the least intrusive remedy?",
                        payload={"lead_score": lead_score, "assigned_tier": decision},
                    )
                ]
                if churn_signal
                else []
            ),
            challenges=challenges,
        )


class SupportAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(
            agent_id="agent_support",
            domain="support",
            capabilities=["session_inspect", "email_dispatch", "ticketing_tool"],
        )

    async def process(self, input_data: AgentInput) -> AgentOutput:
        events = input_data.events or []
        # Session context (plan tier, role, recent incidents) raises the severity
        # of otherwise-ambiguous friction; surfacing it here keeps the signal
        # available to the reasoning summary instead of being silently dropped.
        context = input_data.context or {}
        session_label = (
            context.get("session_label") or context.get("plan") or context.get("tier") or context.get("account_tier")
        )

        error_events = [
            e
            for e in events
            if "error" in e.get("type", "").lower()
            or "exception" in e.get("type", "").lower()
            or "fail" in e.get("type", "").lower()
        ]
        error_count = len(error_events)

        critical_keywords = ["checkout", "payment", "billing", "subscribe", "card", "order"]
        affected_critical = any(
            any(kw in str(e.get("data", {})).lower() or kw in e.get("type", "").lower() for kw in critical_keywords)
            for e in error_events
        )

        rage_clicks = sum(1 for e in events if "rage" in e.get("type", "").lower())
        rapid_navigation = sum(
            1 for e in events if "bounce" in e.get("type", "").lower() or "back" in e.get("type", "").lower()
        )

        evidence = [
            f"error_count={error_count}",
            f"critical_page_affected={affected_critical}",
            f"rage_clicks={rage_clicks}",
            f"rapid_navigation={rapid_navigation}",
        ]
        if session_label:
            evidence.append(f"session_segment={session_label}")

        if error_count >= 3 or (error_count >= 1 and affected_critical):
            decision = "HIGH_PRIORITY_INTERVENTION"
            reasoning = f"Critical errors observed in user journey ({error_count=}, {affected_critical=}). Initiating immediate inspection."
            actions = [
                ProposedAction(
                    action_type="session_inspect",
                    target="session_telemetry",
                    params={"inspect_depth": "full_replay", "error_count": error_count},
                    rationale="High error frequency or checkout disruption requires technical inspection.",
                    side_effect_level="READ",
                ),
                ProposedAction(
                    action_type="email_dispatch",
                    target="support_escalation",
                    params={"priority": "P1", "reason": "Checkout/payment failure detected"},
                    rationale="Alert support engineers to active customer degradation.",
                    side_effect_level="SENSITIVE",
                ),
            ]
            confidence = 0.95
        elif error_count >= 1 or rage_clicks >= 2:
            decision = "MEDIUM_PRIORITY_MONITORING"
            reasoning = (
                f"Minor session friction detected ({error_count=}, {rage_clicks=}). Scheduling proactive diagnostics."
            )
            actions = [
                ProposedAction(
                    action_type="session_inspect",
                    target="session_telemetry",
                    params={"inspect_depth": "summary", "error_count": error_count},
                    rationale="Diagnose potential UI friction before customer escalates.",
                    side_effect_level="READ",
                )
            ]
            confidence = 0.85
        else:
            decision = "NO_INTERVENTION"
            reasoning = f"Zero errors and healthy session metrics ({error_count=}). No support intervention required."
            actions = []
            confidence = 0.99

        return AgentOutput(
            agent_id=self.agent_id,
            decision=decision,
            reasoning_summary=reasoning,
            confidence=confidence,
            evidence_refs=evidence,
            proposed_actions=actions,
            expected_outcomes={"error_count": error_count, "intervention_level": decision},
            handoffs=(
                [
                    HandoffRequest(
                        target_agent_id="agent_reliability",
                        reason=f"{error_count} journey errors indicate a possible infrastructure fault",
                        question="Is there an SLO breach that requires an incident escalation?",
                        priority="urgent" if (error_count >= 3 or affected_critical) else "normal",
                        payload={"error_count": error_count, "affected_critical": affected_critical},
                    )
                ]
                if (error_count >= 3 or (error_count >= 1 and affected_critical))
                else []
            ),
        )


class ReliabilityAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(
            agent_id="agent_reliability", domain="reliability", capabilities=["session_inspect", "ticketing_tool"]
        )

    async def process(self, input_data: AgentInput) -> AgentOutput:
        events = input_data.events or []
        context = input_data.context or {}

        metrics = context.get("metrics", {})
        thresholds = context.get("thresholds", {})

        latency_p99 = metrics.get("latency_p99_ms", 0)
        error_rate = metrics.get("error_rate_pct", 0.0)
        latency_thresh = thresholds.get("latency_p99_ms", 500)
        error_thresh = thresholds.get("error_rate_pct", 5.0)

        error_events = [e for e in events if "error" in e.get("type", "").lower() or "50" in str(e.get("data", {}))]

        latency_breach = latency_p99 > latency_thresh
        error_breach = error_rate > error_thresh or len(error_events) >= 5

        evidence = [
            f"latency_p99_ms={latency_p99}",
            f"latency_threshold_ms={latency_thresh}",
            f"error_rate_pct={error_rate}",
            f"error_threshold_pct={error_thresh}",
            f"event_error_count={len(error_events)}",
            f"breach_detected={latency_breach or error_breach}",
        ]

        if latency_breach or error_breach:
            decision = "ESCALATE_RELIABILITY_INCIDENT"
            reasoning = f"SLO breach detected! (latency_p99={latency_p99}ms > {latency_thresh}ms or error_rate={error_rate}% > {error_thresh}%)."
            actions = [
                ProposedAction(
                    action_type="session_inspect",
                    target="infrastructure_metrics",
                    params={"p99": latency_p99, "error_rate": error_rate, "alert": "SLO_BREACH"},
                    rationale="Trigger automated infrastructure trace diagnostics.",
                    side_effect_level="READ",
                )
            ]
            confidence = 0.98
        else:
            decision = "NO_ACTION"
            reasoning = f"System performance healthy within SLO boundaries ({latency_p99=}ms <= {latency_thresh}ms)."
            actions = []
            confidence = 0.99

        return AgentOutput(
            agent_id=self.agent_id,
            decision=decision,
            reasoning_summary=reasoning,
            confidence=confidence,
            evidence_refs=evidence,
            proposed_actions=actions,
            expected_outcomes={"sla_healthy": not (latency_breach or error_breach)},
            handoffs=(
                [
                    HandoffRequest(
                        target_agent_id="agent_support",
                        reason="SLO breach detected; affected customers may need proactive communication",
                        question="Which active sessions were impacted and should we reach out?",
                        priority="urgent",
                        payload={"latency_p99_ms": latency_p99, "error_rate_pct": error_rate},
                    )
                ]
                if (latency_breach or error_breach)
                else []
            ),
        )


class QualificationAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(
            agent_id="agent_qualification", domain="qualification", capabilities=["account_update", "crm_tool"]
        )

    async def process(self, input_data: AgentInput) -> AgentOutput:
        events = input_data.events or []
        context = input_data.context or {}
        attrs = context.get("visitor_attributes", {})

        behavioral_events = [
            e
            for e in events
            if any(k in e.get("type", "").lower() for k in ["page_view", "pricing", "demo", "docs", "feature"])
        ]
        behavior_score = min(len(behavioral_events) * 0.08, 0.40)

        email = attrs.get("email", "") or context.get("profile_email", "") or ""
        company = attrs.get("company", "") or ""
        enterprise_domains = ["corp.com", "enterprise", "inc.com", "ltd.com", ".gov", ".edu"]
        if any(d in email.lower() for d in enterprise_domains) or len(company) > 3:
            firmographic_score = 0.30
        elif email and "@" in email:
            firmographic_score = 0.15
        else:
            firmographic_score = 0.0

        event_count = len(events)
        recency_score = min(event_count * 0.04, 0.20)

        source = context.get("event_data", {}).get("source", "") or attrs.get("source", "")
        source_score = 0.10 if source.lower() in ("direct", "referral", "linkedin", "organic") else 0.05

        total_score = round(behavior_score + firmographic_score + recency_score + source_score, 2)

        evidence = [
            f"behavior_score={round(behavior_score, 2)}",
            f"firmographic_score={round(firmographic_score, 2)}",
            f"recency_score={round(recency_score, 2)}",
            f"source_score={round(source_score, 2)}",
            f"total_qualification_score={total_score}",
        ]

        if total_score >= 0.60:
            decision = "QUALIFIED_LEAD"
            reasoning = f"Lead achieved threshold qualification score ({total_score=} >= 0.60)."
            actions = [
                ProposedAction(
                    action_type="account_update",
                    target="crm_qualification",
                    params={"qualified": True, "score": total_score},
                    rationale="Push qualified buyer profile to CRM.",
                    side_effect_level="SENSITIVE",
                )
            ]
        else:
            decision = "UNQUALIFIED_LEAD"
            reasoning = f"Lead score ({total_score=} < 0.60) below automated qualification threshold."
            actions = []

        return AgentOutput(
            agent_id=self.agent_id,
            decision=decision,
            reasoning_summary=reasoning,
            confidence=min(0.99, max(0.60, total_score)),
            evidence_refs=evidence,
            proposed_actions=actions,
            expected_outcomes={"qualification_passed": total_score >= 0.60, "total_score": total_score},
            handoffs=(
                [
                    HandoffRequest(
                        target_agent_id="agent_sales",
                        reason=f"Qualified lead (score={total_score}) needs commercial routing",
                        question="Which tier and channel should own this lead?",
                        priority="high" if decision == "QUALIFIED_LEAD" else "normal",
                        payload={"total_score": total_score},
                    )
                ]
                if total_score >= 0.60
                else []
            ),
        )


class ChurnRiskAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(
            agent_id="agent_churn_risk", domain="churn_risk", capabilities=["email_dispatch", "account_update"]
        )

    async def process(self, input_data: AgentInput) -> AgentOutput:
        events = input_data.events or []
        context = input_data.context or {}
        metrics = context.get("metrics", {})

        recent_sessions = metrics.get("sessions_last_30d", 0)
        previous_sessions = metrics.get("sessions_prev_30d", max(recent_sessions, 1))
        support_tickets = metrics.get("support_tickets_recent", 0)
        feature_usage_drop = metrics.get("feature_usage_drop_pct", 0.0)

        session_decline = (previous_sessions - recent_sessions) / max(previous_sessions, 1)

        negative_events = [
            e
            for e in events
            if any(
                k in e.get("type", "").lower()
                for k in ["cancel", "downgrade", "complaint", "refund", "unsubscribe", "error"]
            )
        ]

        evidence = [
            f"session_decline_pct={round(session_decline * 100, 1)}",
            f"support_tickets_count={support_tickets}",
            f"feature_usage_drop_pct={round(feature_usage_drop * 100, 1)}",
            f"negative_events_count={len(negative_events)}",
        ]

        if session_decline > 0.50 or support_tickets >= 3 or feature_usage_drop > 0.40 or len(negative_events) >= 2:
            decision = "RISK_HIGH"
            reasoning = f"Critical retention risk signals detected ({session_decline=:.2f}, tickets={support_tickets}, negative_events={len(negative_events)})."
            actions = [
                ProposedAction(
                    action_type="email_dispatch",
                    target="customer_success_lead",
                    params={"urgency": "critical", "risk_factor": "high_dropoff_or_errors"},
                    rationale="Alert customer success manager for immediate intervention.",
                    side_effect_level="SENSITIVE",
                )
            ]
            confidence = 0.92
        elif session_decline > 0.20 or support_tickets >= 1 or len(negative_events) >= 1:
            decision = "RISK_MEDIUM"
            reasoning = f"Moderate engagement drop detected ({session_decline=:.2f}). Triggering check-in campaign."
            actions = [
                ProposedAction(
                    action_type="email_dispatch",
                    target="automated_nurture",
                    params={"template": "account_health_checkin"},
                    rationale="Deliver automated health check-in to re-engage user.",
                    side_effect_level="SENSITIVE",
                )
            ]
            confidence = 0.80
        else:
            decision = "RISK_LOW"
            reasoning = f"Customer health healthy with active usage metrics ({session_decline=:.2f})."
            actions = []
            confidence = 0.95

        return AgentOutput(
            agent_id=self.agent_id,
            decision=decision,
            reasoning_summary=reasoning,
            confidence=confidence,
            evidence_refs=evidence,
            proposed_actions=actions,
            expected_outcomes={"risk_level": decision, "remedy_scheduled": len(actions) > 0},
            handoffs=(
                [
                    HandoffRequest(
                        target_agent_id="agent_sales",
                        reason="High churn risk needs an account owner for the retention motion",
                        question="Should we authorise a retention offer for this account?",
                        priority="urgent",
                        payload={"risk_level": decision},
                    )
                ]
                if decision == "RISK_HIGH"
                else []
            ),
        )


class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, SpecialistAgent] = {}
        # Pre-register default domain agents
        self.register(GrowthAgent())
        self.register(SalesAgent())
        self.register(SupportAgent())
        self.register(ReliabilityAgent())
        self.register(QualificationAgent())
        self.register(ChurnRiskAgent())
        try:
            from .competitive_agent import CompetitiveIntelligenceAgent

            self.register(CompetitiveIntelligenceAgent())
        except Exception:
            pass

    def register(self, agent: SpecialistAgent) -> None:
        self._agents[agent.agent_id] = agent
        if hasattr(agent, "domain") and agent.domain:
            self._agents[agent.domain] = agent

    def get(self, identifier: str) -> SpecialistAgent | None:
        return self._agents.get(identifier)

    def route_for_event(self, event_type: str) -> SpecialistAgent:
        e = event_type.lower()
        if "competitor" in e or "intelx" in e or "battlecard" in e or "vs_" in e:
            return self._agents.get("agent_competitive", self._agents["growth"])
        if "qualify" in e or "score" in e:
            return self._agents["qualification"]
        if "churn" in e or "engage" in e or "retention" in e:
            return self._agents["churn_risk"]
        if "pricing" in e or "funnel" in e or "exit" in e or "banner" in e:
            return self._agents["growth"]
        if "checkout" in e or "lead" in e or "sales" in e or "enterprise" in e:
            return self._agents["sales"]
        if "error" in e or "issue" in e or "help" in e or "ticket" in e:
            return self._agents["support"]
        return self._agents["reliability"]


from .collaboration import CollaborationResult, CollaborationSession  # noqa: E402  (defined after agents)
from .competitive_agent import CompetitiveIntelligenceAgent

__all__ = [
    "AgentInput",
    "AgentOutput",
    "AgentRegistry",
    "ChallengeNote",
    "ChurnRiskAgent",
    "CollaborationResult",
    "CollaborationSession",
    "GrowthAgent",
    "HandoffRequest",
    "ProposedAction",
    "QualificationAgent",
    "ReliabilityAgent",
    "SalesAgent",
    "SpecialistAgent",
    "SupportAgent",
]
