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
        return AgentOutput(
            agent_id=self.agent_id,
            decision="OPTIMIZE_FUNNEL",
            reasoning_summary="Identified high drop-off on pricing table; suggesting CTA variant.",
            confidence=0.88,
            evidence_refs=["pricing_view_event", "session_exit_intent"],
            proposed_actions=[
                ProposedAction(
                    action_type="banner_injection",
                    target="pricing_cta",
                    params={"variant": "annual_discount_banner"},
                    rationale="Improve conversion rate by offering annual discount.",
                    side_effect_level="HIGH_IMPACT"
                )
            ],
            expected_outcomes={"conversion_lift_pct": 12.5}
        )


class SalesAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(agent_id="agent_sales", domain="sales", capabilities=["email_dispatch", "account_update"])

    async def process(self, input_data: AgentInput) -> AgentOutput:
        return AgentOutput(
            agent_id=self.agent_id,
            decision="ROUTE_ENTERPRISE_LEAD",
            reasoning_summary="Visitor firmographics match ICP threshold.",
            confidence=0.92,
            evidence_refs=["page_view_enterprise", "employee_count_gt_500"],
            proposed_actions=[
                ProposedAction(
                    action_type="account_update",
                    target="lead_qualification",
                    params={"tier": "enterprise_tier_1", "sales_rep_assigned": "rep_alice"},
                    rationale="Route lead to enterprise sales executive.",
                    side_effect_level="SENSITIVE"
                )
            ],
            expected_outcomes={"sla_response_hours": 1}
        )


class SupportAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(agent_id="agent_support", domain="support", capabilities=["session_inspect", "email_dispatch"])

    async def process(self, input_data: AgentInput) -> AgentOutput:
        return AgentOutput(
            agent_id=self.agent_id,
            decision="OFFER_PROACTIVE_ASSISTANCE",
            reasoning_summary="Repeated error events detected in session.",
            confidence=0.85,
            evidence_refs=["api_500_error_count_gt_3"],
            proposed_actions=[
                ProposedAction(
                    action_type="session_inspect",
                    target="session_telemetry",
                    params={"inspect_depth": "full_replay"},
                    rationale="Diagnose checkout friction.",
                    side_effect_level="READ"
                )
            ],
            expected_outcomes={"resolution_time_reduction_pct": 25.0}
        )


class ReliabilityAgent(SpecialistAgent):
    def __init__(self):
        super().__init__(agent_id="agent_reliability", domain="reliability", capabilities=["session_inspect"])

    async def process(self, input_data: AgentInput) -> AgentOutput:
        return AgentOutput(
            agent_id=self.agent_id,
            decision="MONITOR_LATENCY",
            reasoning_summary="P99 latency within acceptable bounds.",
            confidence=0.98,
            evidence_refs=["p99_latency_metric_ms_120"],
            proposed_actions=[],
            expected_outcomes={"availability": 0.9999}
        )


class AgentRegistry:
    def __init__(self):
        self._agents: Dict[str, SpecialistAgent] = {}
        # Pre-register default domain agents
        self.register(GrowthAgent())
        self.register(SalesAgent())
        self.register(SupportAgent())
        self.register(ReliabilityAgent())

    def register(self, agent: SpecialistAgent) -> None:
        self._agents[agent.agent_id] = agent
        self._agents[agent.domain] = agent

    def get(self, identifier: str) -> Optional[SpecialistAgent]:
        return self._agents.get(identifier)

    def route_for_event(self, event_type: str) -> SpecialistAgent:
        if "pricing" in event_type or "funnel" in event_type:
            return self._agents["growth"]
        if "checkout" in event_type or "lead" in event_type:
            return self._agents["sales"]
        if "error" in event_type or "issue" in event_type:
            return self._agents["support"]
        return self._agents["reliability"]
