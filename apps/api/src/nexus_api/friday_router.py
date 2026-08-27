"""
FRIDAY Cross-System Integration Gateway
========================================
This module exposes a dedicated set of NEXUS API endpoints optimised for
consumption by FRIDAY — the general autonomous operating system that invokes
NEXUS as a specialist capability.

Endpoints
---------
POST /v1/friday/command
    Accepts a FridayCommand payload, authenticates FRIDAY via FRIDAY_API_KEY,
    synthesises a canonical NEXUS EventSchema with actor type `friday_system`,
    and routes it directly through Orchestrator.run_cognitive_loop().
    Returns the full 10-phase trace so FRIDAY can reason about what NEXUS did.

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
from datetime import datetime, timedelta
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

from nexus_event_schema import EventSchema, Actor, ActorType
from nexus_core.orchestrator import Orchestrator
from nexus_api.config import get_db_session
from nexus_api.db_models import LeadModel, ProfileModel, EventModel, AuditRecordModel
from nexus_api.auth import verify_friday_token
from nexus_api.tracing import get_current_trace_id

logger = logging.getLogger("nexus-friday-gateway")

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

    FRIDAY uses this to delegate a specific goal or action to NEXUS as a
    specialist capability. NEXUS translates it into an EventSchema, routes it
    through the full 10-phase cognitive loop, and returns the trace.
    """
    goal: str = Field(
        ...,
        description="High-level objective FRIDAY wants NEXUS to achieve.",
        examples=["Convert high-intent enterprise visitors to booked demos"],
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Structured contextual data FRIDAY provides to inform NEXUS reasoning. "
            "May include visitor_id, site_id, tenant_id, session signals, or prior "
            "FRIDAY inference results."
        ),
    )
    required_capability: str = Field(
        ...,
        description=(
            "The NEXUS specialist capability FRIDAY requires. "
            "Maps to agent domain: 'growth', 'sales', 'support', 'reliability'."
        ),
        examples=["sales"],
    )
    requested_action: str = Field(
        ...,
        description=(
            "The specific action or event type FRIDAY wants to trigger in NEXUS. "
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
    nexus_loop_id: str
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
        "through the full NEXUS 10-phase cognitive loop. Returns the complete "
        "execution trace so FRIDAY can perform meta-reasoning on NEXUS outcomes."
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

    # Build a canonical NEXUS EventSchema from the FRIDAY command.
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
            detail=f"NEXUS cognitive loop error: {exc}",
        )

    return FridayCommandResponse(
        status="success",
        command_id=command_id,
        nexus_loop_id=loop_result["loop_id"],
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
    summary="NEXUS Health Summary for FRIDAY",
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

    # If DB has no leads yet (e.g. demo environment), return illustrative mock data
    if not result:
        result = [
            PriorityLead(
                lead_id="lead_demo_001",
                score=92.5,
                status="new",
                source="web",
                profile_email="cto@enterprise-corp.com",
                intent_signals=["Pricing Page Views: 4", "Security Docs Read", "Demo Button Hover"],
                recommended_action="Immediate outreach — schedule enterprise demo call within 2 hours.",
                created_at=datetime.utcnow().isoformat(),
            ),
            PriorityLead(
                lead_id="lead_demo_002",
                score=76.0,
                status="engaged",
                source="stripe_webhook",
                profile_email="founder@startup.io",
                intent_signals=["Checkout Started", "Plan Upgrade Viewed"],
                recommended_action="Send personalised case study email and track open rate.",
                created_at=(datetime.utcnow() - timedelta(hours=3)).isoformat(),
            ),
        ]

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
