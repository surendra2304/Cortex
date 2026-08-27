from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
import abc


class AgentInput(BaseModel):
    goal: str = Field(..., description="Primary objective or trigger purpose")
    context: Dict[str, Any] = Field(default_factory=dict, description="Session, visitor, tenant state")
    events: List[Dict[str, Any]] = Field(default_factory=list, description="Recent telemetry stream events")
    identity_scope: Dict[str, Any] = Field(default_factory=dict, description="Visitor/User identity parameters")
    allowed_capabilities: List[str] = Field(default_factory=list, description="Permitted action types")
    policy_constraints: List[str] = Field(default_factory=list, description="Hard safety boundaries")
    evidence_requirements: List[str] = Field(default_factory=list, description="Required evidence keys")
    budget: Dict[str, Any] = Field(default_factory=lambda: {"max_steps": 5, "timeout_seconds": 10})


class ProposedAction(BaseModel):
    action_type: str
    target: str
    params: Dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    side_effect_level: str = "READ"


class AgentOutput(BaseModel):
    agent_id: str
    decision: str
    reasoning_summary: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_refs: List[str] = Field(default_factory=list)
    dissent: Optional[str] = None
    proposed_actions: List[ProposedAction] = Field(default_factory=list)
    required_approvals: List[str] = Field(default_factory=list)
    expected_outcomes: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SpecialistAgent(abc.ABC):
    def __init__(self, agent_id: str, domain: str, capabilities: List[str]):
        self.agent_id = agent_id
        self.domain = domain
        self.capabilities = capabilities

    @abc.abstractmethod
    async def process(self, input_data: AgentInput) -> AgentOutput:
        pass


class GrowthAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(agent_id="agent_growth", domain="growth", capabilities=["experiment_mutate", "banner_injection"])

    async def process(self, input_data: AgentInput) -> AgentOutput:
        events = input_data.events or []
        context = input_data.context or {}
        session = context.get("session_summary", {})

        pricing_views = session.get("pricing_view_count")
        if pricing_views is None:
            pricing_views = sum(1 for e in events if "pricing" in e.get("type", "").lower() or "pricing" in str(e.get("data", {})).lower())

        demo_views = session.get("demo_view_count")
        if demo_views is None:
            demo_views = sum(1 for e in events if "demo" in e.get("type", "").lower() or "demo" in str(e.get("data", {})).lower())

        enterprise_views = sum(1 for e in events if any(k in e.get("type", "").lower() or k in str(e.get("data", {})).lower() for k in ["enterprise", "security", "compliance"]))
        page_depth = session.get("pages_viewed", len([e for e in events if "page_view" in e.get("type", "").lower()]))
        exit_intent = any("exit" in e.get("type", "").lower() for e in events) or session.get("exit_intent_detected", False)

        raw_score = (pricing_views * 0.35) + (demo_views * 0.40) + (enterprise_views * 0.10) + min(page_depth * 0.02, 0.15)
        intent_score = round(min(raw_score, 1.0), 2)

        evidence = [
            f"pricing_views={pricing_views}",
            f"demo_views={demo_views}",
            f"enterprise_views={enterprise_views}",
            f"page_depth={page_depth}",
            f"exit_intent={exit_intent}",
            f"intent_score={intent_score}"
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
                    side_effect_level="HIGH_IMPACT"
                )
            ]
            confidence = min(0.95, 0.7 + (intent_score * 0.25))
        elif intent_score >= 0.4:
            decision = "OPTIMIZE_FUNNEL"
            reasoning = f"Moderate intent detected ({intent_score=}, {page_depth=}). Offering educational soft touchpoint."
            actions = [
                ProposedAction(
                    action_type="banner_injection",
                    target="content_footer",
                    params={"variant": "soft_cta", "guide": "roi_calculator"},
                    rationale="Nurture moderate engagement visitor without aggressive sales friction.",
                    side_effect_level="HIGH_IMPACT"
                )
            ]
            confidence = 0.75
        else:
            decision = "NO_ACTION"
            reasoning = f"Low intent detected ({intent_score=}, {page_depth=}). Suppressing banner to avoid user fatigue."
            actions = []
            confidence = 0.90

        return AgentOutput(
            agent_id=self.agent_id,
            decision=decision,
            reasoning_summary=reasoning,
            confidence=round(confidence, 2),
            evidence_refs=evidence,
            proposed_actions=actions,
            expected_outcomes={"intent_score": intent_score, "actions_proposed": len(actions)}
        )


class SalesAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(agent_id="agent_sales", domain="sales", capabilities=["email_dispatch", "account_update", "crm_tool"])

    async def process(self, input_data: AgentInput) -> AgentOutput:
        events = input_data.events or []
        context = input_data.context or {}
        attrs = context.get("visitor_attributes", {})
        session = context.get("session_summary", {})

        pricing_views = session.get("pricing_view_count", sum(1 for e in events if "pricing" in e.get("type", "").lower()))
        demo_views = session.get("demo_view_count", sum(1 for e in events if "demo" in e.get("type", "").lower()))
        intent_score = min((pricing_views * 0.15 + demo_views * 0.25), 0.40)

        email = attrs.get("email", "") or context.get("profile_email", "") or ""
        company = attrs.get("company", "") or ""
        enterprise_domains = ["corp.com", "enterprise", "inc.com", "ltd.com", ".gov", ".edu", "tech.co"]
        
        is_enterprise_domain = any(d in email.lower() for d in enterprise_domains) or bool(company and len(company) > 3)
        if is_enterprise_domain:
            firmographic_score = 0.30
        elif email and "@" in email and not any(free in email.lower() for free in ["gmail.com", "yahoo.com", "hotmail.com"]):
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

        evidence = [
            f"intent_component={round(intent_score, 2)}",
            f"firmographic_component={round(firmographic_score, 2)}",
            f"recency_component={round(recency_score, 2)}",
            f"source_component={round(source_score, 2)}",
            f"email_present={bool(email)}",
            f"lead_score={lead_score}"
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
                    side_effect_level="SENSITIVE"
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
                    side_effect_level="SENSITIVE"
                )
            ]
        else:
            decision = "NURTURE_LEAD"
            reasoning = f"Early stage visitor ({lead_score=}). Keeping in automated nurture loop."
            actions = []

        return AgentOutput(
            agent_id=self.agent_id,
            decision=decision,
            reasoning_summary=reasoning,
            confidence=min(0.99, max(0.50, lead_score)),
            evidence_refs=evidence,
            proposed_actions=actions,
            expected_outcomes={"lead_score": lead_score, "assigned_tier": decision}
        )


class SupportAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(agent_id="agent_support", domain="support", capabilities=["session_inspect", "email_dispatch", "ticketing_tool"])

    async def process(self, input_data: AgentInput) -> AgentOutput:
        events = input_data.events or []
        context = input_data.context or {}

        error_events = [e for e in events if "error" in e.get("type", "").lower() or "exception" in e.get("type", "").lower() or "fail" in e.get("type", "").lower()]
        error_count = len(error_events)

        critical_keywords = ["checkout", "payment", "billing", "subscribe", "card", "order"]
        affected_critical = any(
            any(kw in str(e.get("data", {})).lower() or kw in e.get("type", "").lower() for kw in critical_keywords)
            for e in error_events
        )

        rage_clicks = sum(1 for e in events if "rage" in e.get("type", "").lower())
        rapid_navigation = sum(1 for e in events if "bounce" in e.get("type", "").lower() or "back" in e.get("type", "").lower())

        evidence = [
            f"error_count={error_count}",
            f"critical_page_affected={affected_critical}",
            f"rage_clicks={rage_clicks}",
            f"rapid_navigation={rapid_navigation}"
        ]

        if error_count >= 3 or (error_count >= 1 and affected_critical):
            decision = "HIGH_PRIORITY_INTERVENTION"
            reasoning = f"Critical errors observed in user journey ({error_count=}, {affected_critical=}). Initiating immediate inspection."
            actions = [
                ProposedAction(
                    action_type="session_inspect",
                    target="session_telemetry",
                    params={"inspect_depth": "full_replay", "error_count": error_count},
                    rationale="High error frequency or checkout disruption requires technical inspection.",
                    side_effect_level="READ"
                ),
                ProposedAction(
                    action_type="email_dispatch",
                    target="support_escalation",
                    params={"priority": "P1", "reason": "Checkout/payment failure detected"},
                    rationale="Alert support engineers to active customer degradation.",
                    side_effect_level="SENSITIVE"
                )
            ]
            confidence = 0.95
        elif error_count >= 1 or rage_clicks >= 2:
            decision = "MEDIUM_PRIORITY_MONITORING"
            reasoning = f"Minor session friction detected ({error_count=}, {rage_clicks=}). Scheduling proactive diagnostics."
            actions = [
                ProposedAction(
                    action_type="session_inspect",
                    target="session_telemetry",
                    params={"inspect_depth": "summary", "error_count": error_count},
                    rationale="Diagnose potential UI friction before customer escalates.",
                    side_effect_level="READ"
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
            expected_outcomes={"error_count": error_count, "intervention_level": decision}
        )


class ReliabilityAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(agent_id="agent_reliability", domain="reliability", capabilities=["session_inspect", "ticketing_tool"])

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
            f"breach_detected={latency_breach or error_breach}"
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
                    side_effect_level="READ"
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
            expected_outcomes={"sla_healthy": not (latency_breach or error_breach)}
        )


class QualificationAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(agent_id="agent_qualification", domain="qualification", capabilities=["account_update", "crm_tool"])

    async def process(self, input_data: AgentInput) -> AgentOutput:
        events = input_data.events or []
        context = input_data.context or {}
        attrs = context.get("visitor_attributes", {})

        behavioral_events = [e for e in events if any(k in e.get("type", "").lower() for k in ["page_view", "pricing", "demo", "docs", "feature"])]
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
            f"total_qualification_score={total_score}"
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
                    side_effect_level="SENSITIVE"
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
            expected_outcomes={"qualification_passed": total_score >= 0.60, "total_score": total_score}
        )


class ChurnRiskAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(agent_id="agent_churn_risk", domain="churn_risk", capabilities=["email_dispatch", "account_update"])

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
            e for e in events 
            if any(k in e.get("type", "").lower() for k in ["cancel", "downgrade", "complaint", "refund", "unsubscribe", "error"])
        ]

        evidence = [
            f"session_decline_pct={round(session_decline * 100, 1)}",
            f"support_tickets_count={support_tickets}",
            f"feature_usage_drop_pct={round(feature_usage_drop * 100, 1)}",
            f"negative_events_count={len(negative_events)}"
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
                    side_effect_level="SENSITIVE"
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
                    side_effect_level="SENSITIVE"
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
            expected_outcomes={"risk_level": decision, "remedy_scheduled": len(actions) > 0}
        )


class AgentRegistry:
    def __init__(self):
        self._agents: Dict[str, SpecialistAgent] = {}
        # Pre-register default domain agents
        self.register(GrowthAgent())
        self.register(SalesAgent())
        self.register(SupportAgent())
        self.register(ReliabilityAgent())
        self.register(QualificationAgent())
        self.register(ChurnRiskAgent())

    def register(self, agent: SpecialistAgent) -> None:
        self._agents[agent.agent_id] = agent
        self._agents[agent.domain] = agent

    def get(self, identifier: str) -> Optional[SpecialistAgent]:
        return self._agents.get(identifier)

    def route_for_event(self, event_type: str) -> SpecialistAgent:
        e = event_type.lower()
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
