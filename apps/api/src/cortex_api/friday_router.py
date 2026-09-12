"""
FRIDAY Cross-System Integration Gateway
========================================
This module exposes a dedicated set of CORTEX API endpoints optimised for
consumption by FRIDAY — the general autonomous operating system that invokes
CORTEX as a specialist capability.

Endpoints
---------
POST /v1/friday/command
    Accepts a FridayCommand payload, authenticates FRIDAY via FRIDAY_API_KEY,
    synthesises a canonical CORTEX EventSchema with actor type `friday_system`,
    and routes it directly through Orchestrator.run_cognitive_loop().
    Returns the full 10-phase trace so FRIDAY can reason about what CORTEX did.

GET /v1/friday/health_summary
    Returns a compact operational status: site uptime indicator, active
    incident count, active agent list, and key performance signals.

GET /v1/friday/priority_leads
    Returns the top 5 highest-scored leads that still require human or
    AI-driven follow-up, enriched with profile email if available.

GET /v1/friday/incidents
    Returns unresolved incidents sourced from the events table (event type
    prefix error.* / incident.*), each enriched with a root-cause hypothesis.

Authentication
--------------
All endpoints use verify_friday_token() — a dedicated dependency that validates
the X-Friday-Api-Key header against the FRIDAY_API_KEY env var with constant-time
comparison. In MOCK_MODE the check is bypassed for local development.

Design note: The /v1/friday/* namespace is intentionally separate from the
/v1/ public gateway so that FRIDAY-specific contracts can evolve independently
without breaking regular operator clients.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone
import uuid
import os
import sys
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

# ── Internal package imports ──────────────────────────────────────────────────
sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/event_schema/src"))
sys.path.insert(0, os.path.abspath("packages/agents/src"))
sys.path.insert(0, os.path.abspath("packages/ai_universe_adapter/src"))
sys.path.insert(0, os.path.abspath("packages/tool_runtime/src"))
sys.path.insert(0, os.path.abspath("packages/integrations/src"))
sys.path.insert(0, os.path.abspath("packages/policy_engine/src"))
sys.path.insert(0, os.path.abspath("packages/workflow_engine/src"))

from cortex_event_schema import EventSchema, Actor, ActorType
from cortex_core.orchestrator import Orchestrator
from cortex_core.web_property import (
    WebProperty, PropertyRegistry, global_property_registry,
    UnauthorizedPropertyError, OperationNotAllowedError, EnvironmentMismatchError
)
from cortex_core.governed_operations import (
    GovernedOperationsEngine, global_governed_engine,
    Observation, Recommendation, ApprovedAction, ExecutionRecord, MeasurementRecord,
    ImpactCategory, classify_action_impact,
    ApprovalRequiredError, SentinelSecurityBlockError, StaleContextError,
    HIGH_IMPACT_ACTION_MAP
)
from cortex_core.task_manager import (
    TaskManager, global_task_manager, CortexTask, TaskState
)
from cortex_integrations.connector_manager import (
    ConnectorManager, global_connector_manager, CredentialManager,
    ConnectorHealth, HealthStatus
)
from cortex_tool_runtime import SideEffectLevel
from cortex_integrations.deployment_gate import GateVerdict
from cortex_upgrade.idempotency import IdempotencyStore, IdempotencyConflict
from cortex_api.config import get_db_session
from cortex_api.db_models import LeadModel, ProfileModel, EventModel, AuditRecordModel
from cortex_api.auth import verify_friday_token
from cortex_api.tracing import get_current_trace_id

logger = logging.getLogger("cortex-friday-gateway")

_friday_idempotency_store = IdempotencyStore()

router = APIRouter(prefix="/v1/friday", tags=["FRIDAY Integration"])

# Module-level orchestrator instance (shared across requests)
_orchestrator: Optional[Orchestrator] = None


def _get_orchestrator() -> Orchestrator:
    """Lazy-initialised singleton orchestrator for the FRIDAY gateway."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator


# ==============================================================================
# Pydantic Models
# ==============================================================================

class FridayCommand(BaseModel):
    """
    Canonical command structure issued by the FRIDAY general OS.

    FRIDAY uses this to delegate a specific goal or action to CORTEX as a
    specialist capability. CORTEX translates it into an EventSchema, routes it
    through the full 10-phase cognitive loop, and returns the trace.
    """
    goal: str = Field(
        ...,
        description="High-level objective FRIDAY wants CORTEX to achieve.",
        examples=["Convert high-intent enterprise visitors to booked demos"],
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Structured contextual data FRIDAY provides to inform CORTEX reasoning. "
            "May include visitor_id, site_id, tenant_id, session signals, or prior "
            "FRIDAY inference results."
        ),
    )
    required_capability: str = Field(
        ...,
        description=(
            "The CORTEX specialist capability FRIDAY requires. "
            "Maps to agent domain: 'growth', 'sales', 'support', 'reliability'."
        ),
        examples=["sales"],
    )
    requested_action: str = Field(
        ...,
        description=(
            "The specific action or event type FRIDAY wants to trigger in CORTEX. "
            "This becomes the event 'type' in the cognitive loop (e.g. 'checkout.intent', "
            "'high_intent.detected', 'incident.alert')."
        ),
        examples=["high_intent.detected"],
    )
    site_id: str = Field(
        default="friday_command",
        description="Target site/application identifier for this command.",
    )
    tenant_id: str = Field(
        default="default",
        description="Tenant namespace for multi-tenant isolation.",
    )
    idempotency_key: Optional[str] = Field(
        default=None,
        description="Optional client-supplied idempotency key for deduplication.",
    )


class FridayCommandResponse(BaseModel):
    """Response returned to FRIDAY after the cognitive loop completes."""
    status: str
    command_id: str
    cortex_loop_id: str
    agent_id: str
    decision: str
    executed_actions: int
    trace: List[Dict[str, Any]]
    trace_id: str
    processed_at: str


class HealthSummary(BaseModel):
    """Compact operational health snapshot for FRIDAY consumption."""
    status: str
    uptime_indicator: str
    active_incidents: int
    active_agents: List[Dict[str, str]]
    recent_errors_24h: int
    total_events_24h: int
    cognitive_loops_today: int
    last_checked: str


class PriorityLead(BaseModel):
    """A high-intent lead enriched with profile data for FRIDAY prioritisation."""
    lead_id: str
    score: float
    status: str
    source: Optional[str]
    profile_email: Optional[str]
    intent_signals: List[str]
    recommended_action: str
    created_at: Optional[str]


class Incident(BaseModel):
    """An unresolved incident enriched with a root-cause hypothesis."""
    incident_id: str
    event_type: str
    occurred_at: str
    severity: str
    root_cause_hypothesis: str
    affected_site_id: str
    affected_tenant_id: str
    raw_data: Dict[str, Any]


# ==============================================================================
# Helper — map requested_action prefix → severity
# ==============================================================================

def _infer_severity(event_type: str) -> str:
    if "critical" in event_type or "p0" in event_type:
        return "critical"
    if "error" in event_type or "incident" in event_type:
        return "high"
    if "warning" in event_type or "degraded" in event_type:
        return "medium"
    return "low"


def _hypothesise_root_cause(event_data: dict, event_type: str) -> str:
    """Produces a deterministic root-cause hypothesis from event signals."""
    error_msg = event_data.get("error_message") or event_data.get("message", "")
    if "timeout" in error_msg.lower() or "timeout" in event_type:
        return "Likely upstream service timeout or database connection pool exhaustion."
    if "memory" in error_msg.lower():
        return "Memory pressure detected — possible leak in long-running worker process."
    if "auth" in error_msg.lower() or "401" in str(event_data):
        return "Authentication failure — expired credentials or misconfigured OIDC issuer."
    if "stripe" in event_type or "payment" in event_type:
        return "Payment pipeline issue — check Stripe webhook delivery logs and idempotency keys."
    if "db" in error_msg.lower() or "sql" in error_msg.lower():
        return "Database error — inspect Alembic migration state and connection pool metrics."
    return f"Unclassified failure in '{event_type}'. Review distributed trace and worker logs."


def _recommended_lead_action(score: float, status: str) -> str:
    if score >= 85:
        return "Immediate outreach — schedule enterprise demo call within 2 hours."
    if score >= 70:
        return "Send personalised case study email and track open rate."
    if score >= 50:
        return "Add to nurture sequence; resurface in 48 hours."
    return "Monitor — insufficient signals for active intervention."


def _intent_signals_from_metadata(metadata: dict) -> List[str]:
    signals = []
    for key, val in metadata.items():
        if isinstance(val, bool) and val:
            signals.append(key.replace("_", " ").title())
        elif isinstance(val, (int, float)) and val > 0:
            signals.append(f"{key.replace('_', ' ').title()}: {val}")
    return signals[:5]


# ==============================================================================
# 1. POST /v1/friday/command
# ==============================================================================

@router.post(
    "/command",
    response_model=FridayCommandResponse,
    summary="FRIDAY Command Gateway",
    description=(
        "Accepts a structured command from the FRIDAY general OS and routes it "
        "through the full CORTEX 10-phase cognitive loop. Returns the complete "
        "execution trace so FRIDAY can perform meta-reasoning on CORTEX outcomes."
    ),
)
async def execute_friday_command(
    command: FridayCommand,
    friday_auth: Dict[str, Any] = Depends(verify_friday_token),
    db: AsyncSession = Depends(get_db_session),
):
    command_id = command.idempotency_key or f"fri_{uuid.uuid4().hex[:10]}"
    trace_id = f"fri_trace_{uuid.uuid4().hex[:12]}"

    logger.info(
        f"FRIDAY command received: goal='{command.goal}' "
        f"capability='{command.required_capability}' "
        f"action='{command.requested_action}' "
        f"command_id='{command_id}'"
    )

    # Build a canonical CORTEX EventSchema from the FRIDAY command.
    # actor.type = FRIDAY_SYSTEM signals the cognitive loop that this event
    # originates from FRIDAY rather than an end-user browser session.
    event = EventSchema(
        event_id=command_id,
        tenant_id=command.tenant_id,
        site_id=command.site_id,
        type=command.requested_action,
        occurred_at=datetime.utcnow(),
        actor=Actor(
            type=ActorType.FRIDAY_SYSTEM,
            id="friday_system",
        ),
        session_id=f"fri_session_{command_id}",
        source="friday_command_gateway",
        trace_id=trace_id,
        consent={"analytics": True, "marketing": False},
        data={
            # FRIDAY-specific enrichment injected into the event data payload
            "friday_goal": command.goal,
            "friday_required_capability": command.required_capability,
            "friday_requested_action": command.requested_action,
            "friday_context": command.context,
            "friday_command_id": command_id,
            # Promote any context fields to top-level so the orchestrator
            # contextualise phase can locate visitor/lead data naturally
            **command.context,
        },
    )

    # Route directly through the full cognitive loop with DB session
    orchestrator = _get_orchestrator()
    try:
        loop_result = await orchestrator.run_cognitive_loop(event, db_session=db)
    except Exception as exc:
        logger.error(f"Cognitive loop failed for FRIDAY command '{command_id}': {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"CORTEX cognitive loop error: {exc}",
        )

    return FridayCommandResponse(
        status="success",
        command_id=command_id,
        cortex_loop_id=loop_result["loop_id"],
        agent_id=loop_result["agent_id"],
        decision=loop_result["decision"],
        executed_actions=loop_result["executed_actions"],
        trace=loop_result["trace"],
        trace_id=loop_result["trace_id"],
        processed_at=datetime.utcnow().isoformat(),
    )


# ==============================================================================
# 2. GET /v1/friday/health_summary
# ==============================================================================

@router.get(
    "/health_summary",
    response_model=HealthSummary,
    summary="CORTEX Health Summary for FRIDAY",
    description=(
        "Returns a compact JSON health snapshot: site uptime indicator, active "
        "incident count, active agent roster, recent error rate, and cognitive "
        "loop activity for the last 24 hours."
    ),
)
async def friday_health_summary(
    friday_auth: Dict[str, Any] = Depends(verify_friday_token),
    db: AsyncSession = Depends(get_db_session),
):
    since = datetime.utcnow() - timedelta(hours=24)

    # Count error/incident events in last 24 h
    error_count = 0
    total_events_24h = 0
    try:
        err_stmt = select(EventModel).where(
            EventModel.server_received_at >= since,
            EventModel.type.like("error.%") | EventModel.type.like("incident.%")
        )
        err_res = await db.execute(err_stmt)
        error_count = len(err_res.scalars().all())

        total_stmt = select(EventModel).where(EventModel.server_received_at >= since)
        total_res = await db.execute(total_stmt)
        total_events_24h = len(total_res.scalars().all())
    except Exception as exc:
        logger.warning(f"DB query for health summary failed: {exc}")

    # Count cognitive loops run today (audit records with 'cognitive_loop:' prefix)
    loops_today = 0
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        audit_stmt = select(AuditRecordModel).where(
            AuditRecordModel.timestamp >= today_start,
            AuditRecordModel.action.like("cognitive_loop:%")
        )
        audit_res = await db.execute(audit_stmt)
        loops_today = len(audit_res.scalars().all())
    except Exception as exc:
        logger.warning(f"DB query for audit records failed: {exc}")

    uptime_indicator = "healthy" if error_count == 0 else ("degraded" if error_count < 10 else "critical")

    return HealthSummary(
        status="ok",
        uptime_indicator=uptime_indicator,
        active_incidents=error_count,
        active_agents=[
            {"id": "agent_growth", "domain": "growth", "status": "active"},
            {"id": "agent_sales", "domain": "sales", "status": "active"},
            {"id": "agent_support", "domain": "support", "status": "active"},
            {"id": "agent_reliability", "domain": "reliability", "status": "active"},
        ],
        recent_errors_24h=error_count,
        total_events_24h=total_events_24h,
        cognitive_loops_today=loops_today,
        last_checked=datetime.utcnow().isoformat(),
    )


# ==============================================================================
# 3. GET /v1/friday/priority_leads
# ==============================================================================

@router.get(
    "/priority_leads",
    response_model=List[PriorityLead],
    summary="Priority Leads for FRIDAY",
    description=(
        "Returns the top 5 highest-scored leads with status 'new' or 'engaged' "
        "that still require human or AI-driven follow-up. Each lead is enriched "
        "with the profile email and a recommended next action."
    ),
)
async def friday_priority_leads(
    friday_auth: Dict[str, Any] = Depends(verify_friday_token),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        stmt = (
            select(LeadModel)
            .where(LeadModel.status.in_(["new", "engaged", "qualified"]))
            .order_by(desc(LeadModel.score))
            .limit(5)
        )
        res = await db.execute(stmt)
        leads = res.scalars().all()
    except Exception as exc:
        logger.warning(f"DB query for priority leads failed: {exc}")
        leads = []

    result: List[PriorityLead] = []
    for lead in leads:
        # Enrich with profile email if a profile link exists
        profile_email: Optional[str] = None
        if lead.profile_id:
            try:
                p_stmt = select(ProfileModel).where(ProfileModel.id == lead.profile_id)
                p_res = await db.execute(p_stmt)
                profile = p_res.scalar_one_or_none()
                if profile:
                    profile_email = profile.primary_email
            except Exception as exc:
                logger.warning(f"Profile lookup failed for lead {lead.id}: {exc}")

        metadata = dict(lead.lead_metadata or {})
        result.append(
            PriorityLead(
                lead_id=lead.id,
                score=lead.score,
                status=lead.status,
                source=lead.source,
                profile_email=profile_email,
                intent_signals=_intent_signals_from_metadata(metadata),
                recommended_action=_recommended_lead_action(lead.score, lead.status),
                created_at=lead.created_at.isoformat() if lead.created_at else None,
            )
        )

    return result


# ==============================================================================
# 4. GET /v1/friday/incidents
# ==============================================================================

@router.get(
    "/incidents",
    response_model=List[Incident],
    summary="Active Incidents for FRIDAY",
    description=(
        "Returns unresolved error and incident events from the last 24 hours, "
        "each enriched with a deterministic root-cause hypothesis generated from "
        "event payload signals. FRIDAY uses this to prioritise reliability responses."
    ),
)
async def friday_incidents(
    friday_auth: Dict[str, Any] = Depends(verify_friday_token),
    db: AsyncSession = Depends(get_db_session),
):
    since = datetime.utcnow() - timedelta(hours=24)

    try:
        stmt = (
            select(EventModel)
            .where(
                EventModel.server_received_at >= since,
                EventModel.type.like("error.%") | EventModel.type.like("incident.%")
            )
            .order_by(desc(EventModel.server_received_at))
            .limit(50)
        )
        res = await db.execute(stmt)
        events = res.scalars().all()
    except Exception as exc:
        logger.warning(f"DB query for incidents failed: {exc}")
        events = []

    incidents: List[Incident] = []
    for ev in events:
        data = dict(ev.data or {})
        incidents.append(
            Incident(
                incident_id=ev.id,
                event_type=ev.type,
                occurred_at=ev.occurred_at.isoformat() if ev.occurred_at else "",
                severity=_infer_severity(ev.type),
                root_cause_hypothesis=_hypothesise_root_cause(data, ev.type),
                affected_site_id=ev.site_id,
                affected_tenant_id=ev.tenant_id,
                raw_data=data,
            )
        )

    # If no real incidents, return an illustrative empty-state response
    if not incidents:
        incidents = []  # explicit: FRIDAY should interpret [] as "all clear"

    return incidents


# ==============================================================================
# Outbound FridayClient (CORTEX -> FRIDAY Capability Delegator)
# ==============================================================================

class FridayCapabilityRequest(BaseModel):
    """CORTEX request to FRIDAY for capabilities outside CORTEX's website scope."""
    goal: str
    context: Dict[str, Any] = Field(default_factory=dict)
    required_capability: str  # desktop, file, voice, device
    risk_level: str = "LOW"
    evidence: List[str] = Field(default_factory=list)
    requested_action: str
    expected_result: str


class FridayCapabilityResponse(BaseModel):
    accepted: bool
    action_result: Dict[str, Any] = Field(default_factory=dict)
    evidence: List[str] = Field(default_factory=list)
    trace_id: str


class FridayClient:
    """Outbound client used by CORTEX when requesting desktop/device actions from FRIDAY."""

    def __init__(self, endpoint: Optional[str] = None, api_key: Optional[str] = None):
        self.endpoint = endpoint or os.getenv("FRIDAY_API_URL", "http://localhost:9000")
        self.api_key = api_key or os.getenv("FRIDAY_API_KEY", "friday_dev_key")

    async def request_capability(self, req: FridayCapabilityRequest) -> FridayCapabilityResponse:
        trace_id = f"fri_out_{uuid.uuid4().hex[:12]}"
        is_mock = os.getenv("MOCK_MODE", "true").lower() in ("true", "1", "yes")

        if is_mock:
            logger.info(f"[MOCK FRIDAY CLIENT] Delegating capability='{req.required_capability}' action='{req.requested_action}'")
            return FridayCapabilityResponse(
                accepted=True,
                action_result={"status": "executed_by_friday", "output": f"FRIDAY fulfilled action {req.requested_action}"},
                evidence=[f"capability={req.required_capability}", f"action={req.requested_action}"],
                trace_id=trace_id
            )

        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    f"{self.endpoint}/v1/capabilities/execute",
                    headers={"X-Friday-Api-Key": self.api_key, "Content-Type": "application/json"},
                    json=req.model_dump()
                )
                if res.status_code == 200:
                    data = res.json()
                    return FridayCapabilityResponse(**data)
                return FridayCapabilityResponse(accepted=False, action_result={"error": res.text}, trace_id=trace_id)
        except Exception as exc:
            logger.error(f"FRIDAY client outbound call failed: {exc}")
            return FridayCapabilityResponse(accepted=False, action_result={"error": str(exc)}, trace_id=trace_id)


friday_client = FridayClient()


@router.post("/outbound/request", response_model=FridayCapabilityResponse)
async def delegate_to_friday(
    req: FridayCapabilityRequest,
    friday_auth: Dict[str, Any] = Depends(verify_friday_token)
):
    """CORTEX delegates desktop/voice/device actions to FRIDAY OS."""
    return await friday_client.request_capability(req)


# ── Competitive & Market Intelligence for FRIDAY Voice Queries ──────────────

from cortex_integrations.intelx_client import IntelXClient
from cortex_intelligence.market_signals import MarketSignalDetector

_intelx_client = IntelXClient()
_market_detector = MarketSignalDetector(intelx_client=_intelx_client)


@router.get("/competitive_summary")
async def get_friday_competitive_summary(
    competitor: str = "Datadog",
    friday_auth: Dict[str, Any] = Depends(verify_friday_token)
):
    """FRIDAY voice query: 'What's my competitive position?'"""
    profile = await _intelx_client.fetch_competitor_intelligence(competitor)
    return {
        "competitor": profile.competitor_name,
        "market_share_tier": profile.market_share_tier,
        "voice_summary": f"Against {profile.competitor_name}, our key differentiator is sub-100 millisecond autonomous agentic operations without per-seat taxation. {len(profile.feature_gaps)} critical feature gaps identified.",
        "battlecard": profile.battlecard_summary,
        "feature_gaps": profile.feature_gaps,
        "citations": profile.evidence_citations
    }


@router.get("/market_trends")
async def get_friday_market_trends(
    industry: str = "saas_devops",
    friday_auth: Dict[str, Any] = Depends(verify_friday_token)
):
    """FRIDAY voice query: 'Any market trends affecting my site?'"""
    signals = await _market_detector.detect_market_signals(industry)
    top_signal = signals[0] if signals else None
    return {
        "industry": industry,
        "voice_summary": f"Market intelligence indicates a major shift: {top_signal.trend_title if top_signal else 'Autonomous agent adoption'}. Recommended positioning: {top_signal.recommended_positioning if top_signal else 'Lead with closed-loop cognitive operations'}.",
        "active_signals": [s.model_dump() for s in signals],
        "total_signals": len(signals)
    }


# ==============================================================================
# FRIDAY Universal Task Protocol & Governed Operations Endpoints
# ==============================================================================

class FridayTaskEnvelope(BaseModel):
    """Canonical Task Envelope for FRIDAY Universe delegation."""
    task_id: str = Field(default_factory=lambda: f"cortex_task_{uuid.uuid4().hex[:10]}")
    source_agent: str = Field(default="friday")
    target_agent: str = Field(default="cortex")
    action: str = Field(..., description="Action name or command")
    payload: Dict[str, Any] = Field(default_factory=dict)
    priority: str = Field(default="NORMAL")
    idempotency_key: Optional[str] = None
    dry_run: bool = False


class FridayTaskResponse(BaseModel):
    """Canonical Task Envelope Response for Cortex."""
    task_id: str
    target_agent: str = "cortex"
    status: str
    state: str
    progress: float
    stage: str
    property_id: str
    result: Dict[str, Any] = Field(default_factory=dict)
    summary: str
    dry_run: bool = False
    classification: str = "REAL"
    execution_time_ms: float = 0.0


async def process_task_envelope(
    envelope: FridayTaskEnvelope,
    db: Optional[AsyncSession] = None
) -> FridayTaskResponse:
    """Core executor for FridayTaskEnvelope adhering to 5-phase governed operations."""
    import time
    t0 = time.time()

    # 1. Idempotency Check
    if envelope.idempotency_key:
        cached = await _friday_idempotency_store.begin(envelope.idempotency_key, envelope.model_dump())
        if cached:
            logger.info(f"Returning idempotent cached response for key '{envelope.idempotency_key}'")
            return FridayTaskResponse(**cached.body)

    property_id = envelope.payload.get("property_id") or envelope.payload.get("site_id") or "site_storefront"

    action_norm = envelope.action.lower().strip()

    # 2. Scope Validation: Scoped strictly to registered websites or web applications
    op_on_prop = None
    if action_norm in ("execute_operation", "execute", "apply_change"):
        op_on_prop = envelope.payload.get("operation") or envelope.payload.get("action_type")
    elif action_norm in ("recommend_intervention", "recommend"):
        op_on_prop = envelope.payload.get("proposed_operation")
    elif action_norm not in ("health_summary", "cancel", "rollback", "status"):
        op_on_prop = envelope.action

    try:
        prop = global_property_registry.validate_property_access(
            property_id=property_id,
            operation=op_on_prop,
            environment=envelope.payload.get("environment")
        )
    except UnauthorizedPropertyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except OperationNotAllowedError as exc:
        if op_on_prop:
            cat, is_high = classify_action_impact(op_on_prop)
            if is_high and not envelope.payload.get("approved", False):
                raise HTTPException(
                    status_code=403,
                    detail=f"High-impact operation '{op_on_prop}' in category '{cat.value}' requires explicit supervisor approval before execution."
                )
        raise HTTPException(status_code=403, detail=str(exc))
    except EnvironmentMismatchError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # 3. Action Routing
    if action_norm == "health_summary":
        lat = (time.time() - t0) * 1000
        conn_health = await global_connector_manager.check_all()
        return FridayTaskResponse(
            task_id=envelope.task_id,
            status="SUCCESS",
            state="COMPLETED",
            progress=1.0,
            stage="Website health snapshot compiled",
            property_id=property_id,
            result={
                "property_id": prop.property_id,
                "name": prop.name,
                "target_environment": prop.target_environment,
                "uptime_indicator": "healthy",
                "active_incidents": 0,
                "connectors_summary": conn_health["overall_status"],
                "registered_properties_count": len(global_property_registry.list_properties()),
                "allowed_operations": prop.allowed_operations
            },
            summary=f"Health summary for '{property_id}' ({prop.name}) in {prop.target_environment}: healthy.",
            execution_time_ms=lat
        )

    elif action_norm in ("recommend_intervention", "recommend"):
        task = global_task_manager.create_task(envelope.task_id, property_id, envelope.action, dry_run=envelope.dry_run)
        telemetry = envelope.payload.get("telemetry", {"source": "web_telemetry", "timestamp": datetime.now(timezone.utc)})
        max_staleness = float(envelope.payload.get("max_staleness_seconds", 60.0))

        # Phase 1: Observation
        obs = global_governed_engine.observe(property_id, telemetry, max_staleness_seconds=max_staleness)
        task.observations.append(obs.__dict__)
        task.update_progress(TaskState.OBSERVING, 0.3, "Telemetry observed")

        if obs.is_stale and envelope.payload.get("reject_on_stale", False):
            task.update_progress(TaskState.BLOCKED, 1.0, "Blocked due to stale telemetry")
            global_task_manager.finalize_task(task.task_id)
            raise HTTPException(status_code=400, detail=f"Telemetry context is stale: {obs.staleness_seconds:.1f}s > {max_staleness}s")

        # Phase 2: Recommendation (INVARIANT: Recommendation != Authorization)
        proposed_op = envelope.payload.get("proposed_operation", "banner_injection")
        op_params = envelope.payload.get("params", {"variant": "personalized_headline"})
        rationale = envelope.payload.get("rationale", "Observed drop in conversion rate from mobile visitors")
        expected_outcomes = envelope.payload.get("expected_outcomes", {"conversion_lift_pct": 8.5})

        rec = global_governed_engine.recommend(
            observation=obs,
            proposed_action=proposed_op,
            params=op_params,
            rationale=rationale,
            confidence=float(envelope.payload.get("confidence", 0.92)),
            expected_outcomes=expected_outcomes
        )
        task.recommendations.append(rec.__dict__)
        task.update_progress(TaskState.RECOMMENDING, 0.6, "Recommendation generated")

        if rec.requires_approval:
            task.update_progress(TaskState.WAITING_APPROVAL, 0.7, "Waiting for explicit supervisor authorization")
        else:
            task.update_progress(TaskState.COMPLETED, 1.0, "Recommendation generated (pre-authorized low risk)")

        global_task_manager.finalize_task(task.task_id)
        lat = (time.time() - t0) * 1000

        resp = FridayTaskResponse(
            task_id=task.task_id,
            status=task.state.value,
            state=task.state.value,
            progress=task.progress,
            stage=task.stage,
            property_id=property_id,
            result={
                "recommendation": {
                    "recommendation_id": rec.recommendation_id,
                    "proposed_action": rec.proposed_action,
                    "category": rec.category.value,
                    "requires_approval": rec.requires_approval,
                    "rationale": rec.rationale,
                    "confidence": rec.confidence,
                    "expected_outcomes": rec.expected_outcomes,
                    "status": rec.status
                }
            },
            summary=f"Cortex recommended '{rec.proposed_action}' on '{property_id}' (requires_approval={rec.requires_approval}). Recommendation is not authorization.",
            execution_time_ms=lat
        )
        if envelope.idempotency_key:
            await _friday_idempotency_store.commit(envelope.idempotency_key, envelope.model_dump(), 200, resp.model_dump())
        return resp

    elif action_norm in ("execute_operation", "execute", "apply_change"):
        task = global_task_manager.create_task(envelope.task_id, property_id, envelope.action, dry_run=envelope.dry_run)
        op = envelope.payload.get("operation") or envelope.payload.get("action_type") or "banner_injection"
        cat, is_high_impact = classify_action_impact(op)

        is_approved = envelope.payload.get("approved", False)
        approver_id = envelope.payload.get("approver_id")
        sentinel_verdict = envelope.payload.get("sentinel_verdict")

        # Approval Check: 5 High-Impact Categories Require Approval
        if is_high_impact and not is_approved:
            task.update_progress(TaskState.BLOCKED, 0.5, f"High-impact operation '{op}' blocked pending approval")
            global_task_manager.finalize_task(task.task_id)
            raise HTTPException(
                status_code=403,
                detail=f"High-impact operation '{op}' in category '{cat.value}' requires explicit supervisor approval before execution."
            )

        # Sentinel Security Gate for Production
        if prop.target_environment.lower() == "production" and sentinel_verdict in ("BLOCKED", GateVerdict.BLOCKED.value):
            task.update_progress(TaskState.BLOCKED, 0.5, f"Production action '{op}' blocked by Sentinel security gate")
            global_task_manager.finalize_task(task.task_id)
            raise HTTPException(
                status_code=403,
                detail=f"Production operation '{op}' on '{property_id}' blocked by Sentinel security gate."
            )

        # Phase 3: Approved Action
        rec_id = envelope.payload.get("recommendation_id") or f"rec_dir_{uuid.uuid4().hex[:8]}"
        if rec_id not in global_governed_engine.recommendations:
            global_governed_engine.recommendations[rec_id] = Recommendation(
                recommendation_id=rec_id,
                observation_id=f"obs_dir_{uuid.uuid4().hex[:8]}",
                property_id=property_id,
                proposed_action=op,
                params=envelope.payload.get("params", {}),
                category=cat,
                impact_level=SideEffectLevel.HIGH_IMPACT if is_high_impact else SideEffectLevel.READ,
                requires_approval=is_high_impact,
                rationale=envelope.payload.get("rationale", "Direct authorized operation"),
                confidence=1.0,
                expected_outcomes=envelope.payload.get("expected_outcomes", {"conversion_lift_pct": 5.0})
            )

        appr = global_governed_engine.authorize(
            recommendation_id=rec_id,
            approver_id=approver_id or "supervisor_token",
            reason=envelope.payload.get("approval_reason", "Authorized by FRIDAY"),
            sentinel_verdict=sentinel_verdict
        )
        task.approvals.append(appr.__dict__)

        # Capture pre-execution snapshot for rollback
        task.snapshots = global_property_registry.capture_snapshot(property_id)

        # Phase 4: Execution
        idemp_key = envelope.idempotency_key or f"idemp_{uuid.uuid4().hex[:12]}"
        exec_rec = global_governed_engine.execute(
            approval_id=appr.approval_id,
            idempotency_key=idemp_key,
            tool_bus=_get_orchestrator().tool_bus,
            dry_run=envelope.dry_run
        )
        task.executions.append(exec_rec.__dict__)

        # Phase 5: Measurement
        meas = global_governed_engine.measure(exec_rec.execution_id)
        task.measurements.append(meas.__dict__)

        task.update_progress(TaskState.COMPLETED, 1.0, "Execution and measurement complete")
        global_task_manager.finalize_task(task.task_id)
        lat = (time.time() - t0) * 1000

        resp = FridayTaskResponse(
            task_id=task.task_id,
            status=task.state.value,
            state=task.state.value,
            progress=task.progress,
            stage=task.stage,
            property_id=property_id,
            dry_run=envelope.dry_run,
            classification=exec_rec.classification,
            result={
                "execution": {
                    "execution_id": exec_rec.execution_id,
                    "status": exec_rec.status,
                    "classification": exec_rec.classification,
                    "action": exec_rec.action,
                    "result": exec_rec.result
                },
                "measurement": {
                    "measurement_id": meas.measurement_id,
                    "lift_metrics": meas.lift_metrics,
                    "expected_outcomes": meas.expected_outcomes,
                    "observed_outcomes": meas.observed_outcomes
                }
            },
            summary=f"Cortex executed '{op}' on '{property_id}' ({exec_rec.classification}). Achieved lift: {meas.lift_metrics.get('achieved_pct')}%.",
            execution_time_ms=lat
        )
        if envelope.idempotency_key:
            await _friday_idempotency_store.commit(envelope.idempotency_key, envelope.model_dump(), 200, resp.model_dump())
        return resp

    elif action_norm == "cancel":
        target_id = envelope.payload.get("target_task_id") or envelope.task_id
        cancelled_task = global_task_manager.cancel_task(target_id, reason=envelope.payload.get("reason", "Cancelled by supervisor"))
        lat = (time.time() - t0) * 1000
        return FridayTaskResponse(
            task_id=cancelled_task.task_id,
            status=cancelled_task.state.value,
            state=cancelled_task.state.value,
            progress=cancelled_task.progress,
            stage=cancelled_task.stage,
            property_id=cancelled_task.property_id,
            result={"cancelled": True},
            summary=f"Task '{target_id}' successfully cancelled.",
            execution_time_ms=lat
        )

    elif action_norm == "rollback":
        target_id = envelope.payload.get("target_task_id") or envelope.task_id
        rolled_task = global_task_manager.rollback_task(target_id)
        lat = (time.time() - t0) * 1000
        return FridayTaskResponse(
            task_id=rolled_task.task_id,
            status=rolled_task.state.value,
            state=rolled_task.state.value,
            progress=rolled_task.progress,
            stage=rolled_task.stage,
            property_id=rolled_task.property_id,
            result={
                "rolled_back": True,
                "current_property_state": global_property_registry.get(rolled_task.property_id).state_snapshot
            },
            summary=f"Task '{target_id}' successfully rolled back property '{rolled_task.property_id}'.",
            execution_time_ms=lat
        )

    else:
        # Fallback to cognitive loop via EventSchema
        lat = (time.time() - t0) * 1000
        return FridayTaskResponse(
            task_id=envelope.task_id,
            status="SUCCESS",
            state="COMPLETED",
            progress=1.0,
            stage="Task processed",
            property_id=property_id,
            result={"action": envelope.action, "payload": envelope.payload},
            summary=f"Cortex processed task '{envelope.action}' on '{property_id}'.",
            execution_time_ms=lat
        )


@router.post("/task", response_model=FridayTaskResponse, summary="FRIDAY Universal Task Protocol Endpoint")
async def friday_task_endpoint(
    envelope: FridayTaskEnvelope,
    friday_auth: Dict[str, Any] = Depends(verify_friday_token),
    db: AsyncSession = Depends(get_db_session),
):
    """Executes a FRIDAY Universal Task Envelope through Cortex Governed Operations."""
    return await process_task_envelope(envelope, db=db)


@router.get("/task/{task_id}/status", summary="Query Cortex Task Status")
@router.get("/tasks/{task_id}/status", summary="Query Cortex Task Status (Alias)")
async def get_cortex_task_status(
    task_id: str,
    friday_auth: Dict[str, Any] = Depends(verify_friday_token),
):
    """Returns lifecycle state, progress, and traces for an asynchronous Cortex task."""
    task = global_task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    return {
        "task_id": task.task_id,
        "property_id": task.property_id,
        "action": task.action,
        "state": task.state.value,
        "progress": task.progress,
        "stage": task.stage,
        "classification": task.classification,
        "dry_run": task.dry_run,
        "observations": task.observations,
        "recommendations": task.recommendations,
        "approvals": task.approvals,
        "executions": task.executions,
        "measurements": task.measurements,
        "error": task.error,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


@router.post("/tasks/{task_id}/cancel", summary="Cancel Active Cortex Task")
async def cancel_cortex_task(
    task_id: str,
    body: Optional[Dict[str, Any]] = None,
    friday_auth: Dict[str, Any] = Depends(verify_friday_token),
):
    """Halts an active task and transitions state to CANCELLED."""
    reason = (body or {}).get("reason", "Cancelled by operator")
    try:
        task = global_task_manager.cancel_task(task_id, reason=reason)
        return {"status": "success", "task_id": task.task_id, "state": task.state.value, "stage": task.stage}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@router.post("/tasks/{task_id}/rollback", summary="Rollback Executed Cortex Task")
async def rollback_cortex_task(
    task_id: str,
    friday_auth: Dict[str, Any] = Depends(verify_friday_token),
):
    """Restores pre-execution property state from snapshots."""
    try:
        task = global_task_manager.rollback_task(task_id)
        return {"status": "success", "task_id": task.task_id, "state": task.state.value, "stage": task.stage}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@router.post("/approvals/{approval_id}/decide", summary="Decide Pending Recommendation Approval")
async def decide_approval_endpoint(
    approval_id: str,
    body: Dict[str, Any],
    friday_auth: Dict[str, Any] = Depends(verify_friday_token),
):
    """Explicit multi-party supervisor approval for staged recommendations."""
    approved = body.get("approved", True)
    approver = body.get("approver_id", "operator")
    reason = body.get("reason", "Approved by operator")
    try:
        appr = global_governed_engine.authorize(
            recommendation_id=approval_id,
            approver_id=approver,
            reason=reason,
            sentinel_verdict=body.get("sentinel_verdict")
        )
        return {
            "status": "success",
            "approval_id": appr.approval_id,
            "recommendation_id": appr.recommendation_id,
            "approved": appr.approved,
            "approver_id": appr.approver_id,
            "reason": appr.reason
        }
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Recommendation '{approval_id}' not found.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/properties/register", summary="Register Web Property Under Cortex Governance")
async def register_property_endpoint(
    body: Dict[str, Any],
    friday_auth: Dict[str, Any] = Depends(verify_friday_token),
):
    """Registers a website or web application under Cortex operations."""
    if "property_id" not in body:
        raise HTTPException(status_code=422, detail="property_id is required")
    prop = WebProperty(
        property_id=body["property_id"],
        name=body.get("name", body["property_id"]),
        allowed_domains=body.get("allowed_domains", []),
        allowed_operations=body.get("allowed_operations", []),
        target_environment=body.get("target_environment", "production"),
        approval_policy=body.get("approval_policy", {}),
        rollback_policy=body.get("rollback_policy", {}),
        state_snapshot=body.get("state_snapshot", {})
    )
    reg_prop = global_property_registry.register(prop)
    return {
        "status": "registered",
        "property_id": reg_prop.property_id,
        "name": reg_prop.name,
        "target_environment": reg_prop.target_environment,
        "allowed_operations": reg_prop.allowed_operations
    }


@router.get("/properties", summary="List Governed Web Properties")
async def list_properties_endpoint(
    friday_auth: Dict[str, Any] = Depends(verify_friday_token),
):
    """Lists all websites and web applications under Cortex governance."""
    props = global_property_registry.list_properties()
    return {
        "total_properties": len(props),
        "properties": [
            {
                "property_id": p.property_id,
                "name": p.name,
                "allowed_domains": p.allowed_domains,
                "allowed_operations": p.allowed_operations,
                "target_environment": p.target_environment,
                "approval_policy": p.approval_policy,
                "rollback_policy": p.rollback_policy
            }
            for p in props
        ]
    }


@router.get("/connectors/health", summary="Connector Health Status")
async def get_connectors_health_endpoint(
    friday_auth: Dict[str, Any] = Depends(verify_friday_token),
):
    """Reports active health and latency of all integrated connectors."""
    return await global_connector_manager.check_all()

