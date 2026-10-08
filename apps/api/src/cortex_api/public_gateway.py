import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/agents/src"))
sys.path.insert(0, os.path.abspath("packages/identity/src"))
sys.path.insert(0, os.path.abspath("packages/ai_universe_adapter/src"))

from cortex_agents import AgentInput, AgentRegistry
from cortex_ai_universe_adapter import AIUniverseClient, IntelligenceRequest
from cortex_identity import IdentityService

from cortex_api.auth import Role, require_role
from cortex_api.config import get_db_session
from cortex_api.db_models import AuditRecordModel, EventModel, LeadModel, ProfileModel, VisitorModel
from cortex_api.tracing import get_current_trace_id


def _utcnow() -> datetime:
    """Timezone-aware UTC now (never a naive timestamp)."""
    return datetime.now(UTC)


router = APIRouter(prefix="/v1", tags=["Public API Gateway"])

agent_registry = AgentRegistry()
ai_client = AIUniverseClient()
identity_service = IdentityService()


# 1. Identity Resolution (POST /v1/identify) - Requires at least VIEWER role
@router.post("/identify")
async def identify_visitor(
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db_session),
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
):
    visitor_id = payload.get("visitor_id")
    if not visitor_id:
        raise HTTPException(status_code=400, detail="visitor_id is required")

    traits = payload.get("traits", {})
    email = payload.get("email") or traits.get("email")

    result = await identity_service.resolve_identity(
        db=db,
        visitor_id=visitor_id,
        user_id=payload.get("user_id"),
        email=email,
        tenant_id=auth.get("tenant_id", "default"),
        site_id=payload.get("site_id", "default"),
        consent_granted=payload.get("consent_granted", True),
        traits=traits,
    )
    result["attributes"] = result.get("traits", {})
    return {"status": "success", "result": result, "trace_id": get_current_trace_id()}


# 2. Visitors (GET /v1/visitors/:id) - Requires VIEWER role
@router.get("/visitors/{visitor_id}")
async def get_visitor(
    visitor_id: str,
    db: AsyncSession = Depends(get_db_session),
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
):
    # Tenant-scoped: a visitor id is only meaningful inside the caller's tenant
    # (cross-tenant id reads were a live-confirmed IDOR).
    tenant_id = auth.get("tenant_id", "default")
    stmt = select(VisitorModel).where(VisitorModel.id == visitor_id, VisitorModel.tenant_id == tenant_id)
    res = await db.execute(stmt)
    visitor = res.scalar_one_or_none()

    if not visitor:
        raise HTTPException(status_code=404, detail="Visitor not found")

    profile_data = None
    if visitor.profile_id:
        prof_stmt = select(ProfileModel).where(
            ProfileModel.id == visitor.profile_id, ProfileModel.tenant_id == tenant_id
        )
        prof_res = await db.execute(prof_stmt)
        profile = prof_res.scalar_one_or_none()
        if profile:
            profile_data = {
                "id": profile.id,
                "primary_email": profile.primary_email,
                "identities": profile.identities,
                "traits": profile.traits,
            }

    return {
        "visitor": {
            "id": visitor.id,
            "tenant_id": visitor.tenant_id,
            "site_id": visitor.site_id,
            "profile_id": visitor.profile_id,
            "attributes": visitor.attributes,
            "first_seen_at": visitor.first_seen_at.isoformat() if visitor.first_seen_at else None,
            "last_seen_at": visitor.last_seen_at.isoformat() if visitor.last_seen_at else None,
            "profile": profile_data,
        },
        "trace_id": get_current_trace_id(),
    }


# 3. Leads (GET /v1/leads/:id & POST/GET /v1/leads) - Requires VIEWER for read, OPERATOR for write
@router.get("/leads/{lead_id}")
async def get_lead(
    lead_id: str,
    db: AsyncSession = Depends(get_db_session),
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
):
    # Tenant-scoped: a lead id is only meaningful inside the caller's tenant
    # (cross-tenant id reads were a live-confirmed IDOR).
    tenant_id = auth.get("tenant_id", "default")
    stmt = select(LeadModel).where(LeadModel.id == lead_id, LeadModel.tenant_id == tenant_id)
    res = await db.execute(stmt)
    lead = res.scalar_one_or_none()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    return {
        "lead": {
            "id": lead.id,
            "tenant_id": lead.tenant_id,
            "profile_id": lead.profile_id,
            "score": lead.score,
            "status": lead.status,
            "source": lead.source,
            "metadata": lead.lead_metadata,
            "created_at": lead.created_at.isoformat() if lead.created_at else None,
        },
        "trace_id": get_current_trace_id(),
    }


@router.get("/leads")
async def list_leads(
    db: AsyncSession = Depends(get_db_session), auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER))
):
    tenant_id = auth.get("tenant_id", "default")
    stmt = select(LeadModel).where(LeadModel.tenant_id == tenant_id)
    res = await db.execute(stmt)
    leads = res.scalars().all()
    return {
        "leads": [
            {
                "id": lead.id,
                "score": lead.score,
                "status": lead.status,
                "source": lead.source,
                "created_at": lead.created_at.isoformat() if lead.created_at else None,
            }
            for lead in leads
        ],
        "total": len(leads),
        "trace_id": get_current_trace_id(),
    }


@router.post("/leads")
async def create_lead(
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db_session),
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
):
    lead_id = f"lead_{uuid.uuid4().hex[:8]}"
    db_lead = LeadModel(
        id=lead_id,
        tenant_id=auth.get("tenant_id", "default"),
        profile_id=payload.get("profile_id"),
        score=payload.get("score", 50.0),
        status=payload.get("status", "new"),
        source=payload.get("source", "web"),
        lead_metadata=payload.get("metadata", {}),
        created_at=_utcnow(),
    )
    db.add(db_lead)
    await db.commit()

    return {
        "lead": {"id": lead_id, "tenant_id": db_lead.tenant_id, "score": db_lead.score, "status": db_lead.status},
        "trace_id": get_current_trace_id(),
    }


# 4. Analytics - Requires VIEWER role
EVENT_BACKED_METRICS = {"events", "event_count", "page_views", "page_view", "conversions", "signups"}


@router.get("/analytics/{metric}")
async def get_analytics(
    metric: str,
    hours: int = 24,
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
    db: AsyncSession = Depends(get_db_session),
):
    """Hourly series computed from the tenant's real events.

    Previously this returned three hardcoded 2026-08-27 data points for every metric name,
    which is indistinguishable from real telemetry in a dashboard. Only event-derived metrics
    are served now; anything else reports ``supported: false`` rather than inventing numbers.
    """
    tenant_id = auth.get("tenant_id", "tenant_default")
    if metric not in EVENT_BACKED_METRICS:
        return {
            "metric": metric,
            "tenant_id": tenant_id,
            "supported": False,
            "values": [],
            "note": "Only event-derived metrics are available; this deployment has no aggregation "
            "source for the requested metric. No sample data is returned.",
            "trace_id": get_current_trace_id(),
        }

    hours = max(1, min(hours, 24 * 30))
    since = _utcnow() - timedelta(hours=hours)
    stmt = select(EventModel.occurred_at).where(EventModel.tenant_id == tenant_id, EventModel.occurred_at >= since)
    if metric in {"page_views", "page_view"}:
        stmt = stmt.where(EventModel.type == "page_view")
    elif metric in {"conversions", "signups"}:
        stmt = stmt.where(EventModel.type.in_(["conversion", "signup"]))

    buckets: dict[str, int] = {}
    for occurred_at in (await db.execute(stmt)).scalars().all():
        if occurred_at is None:
            continue
        key = occurred_at.replace(minute=0, second=0, microsecond=0).isoformat()
        buckets[key] = buckets.get(key, 0) + 1

    return {
        "metric": metric,
        "tenant_id": tenant_id,
        "supported": True,
        "window_hours": hours,
        "values": [{"timestamp": key, "value": value} for key, value in sorted(buckets.items())],
        "trace_id": get_current_trace_id(),
    }


# 5. Intelligence Requests - Requires OPERATOR role
@router.post("/intelligence/requests")
async def create_intelligence_request(
    req: IntelligenceRequest, auth: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR))
):
    res = await ai_client.evaluate(req)
    return {"response": res.model_dump(mode="json"), "trace_id": get_current_trace_id()}


# 6. Agents - List requires VIEWER, Run requires OPERATOR
@router.get("/agents")
async def list_agents(auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER))):
    return {
        "agents": [
            {"id": "agent_growth", "domain": "growth", "capabilities": ["experiment_mutate", "banner_injection"]},
            {"id": "agent_sales", "domain": "sales", "capabilities": ["email_dispatch", "account_update"]},
            {"id": "agent_support", "domain": "support", "capabilities": ["session_inspect", "email_dispatch"]},
            {"id": "agent_reliability", "domain": "reliability", "capabilities": ["session_inspect"]},
        ],
        "trace_id": get_current_trace_id(),
    }


@router.post("/agents/{agent_id}/run")
async def run_agent(
    agent_id: str, input_data: AgentInput, auth: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR))
):
    agent = agent_registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found in registry")
    output = await agent.process(input_data)
    return {"output": output.model_dump(mode="json"), "trace_id": get_current_trace_id()}


# 9. Audit Logs - Requires OPERATOR role for security inspection
@router.get("/audit/{resource_type}")
async def get_audit_logs(
    resource_type: str,
    tenant_id: str | None = None,
    limit: int = 50,
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Return persisted audit records for the caller's tenant.

    This endpoint used to synthesize a single ``aud_sample_1`` row timestamped at request
    time, which made an empty audit trail look like a recorded one. An audit log must never
    invent entries: an empty result now means "no records", full stop.
    """
    limit = max(1, min(limit, 200))
    tenant_scope = tenant_id or auth.get("tenant_id", "tenant_default")
    if tenant_id and tenant_id != auth.get("tenant_id") and auth.get("role") != Role.CORTEX_ADMIN.value:
        raise HTTPException(status_code=403, detail="Cross-tenant audit access requires the admin role.")

    stmt = select(AuditRecordModel).where(AuditRecordModel.tenant_id == tenant_scope)
    if resource_type and resource_type not in {"all", "*"}:
        stmt = stmt.where(AuditRecordModel.action.contains(resource_type))
    stmt = stmt.order_by(desc(AuditRecordModel.timestamp)).limit(limit)

    records = (await db.execute(stmt)).scalars().all()
    return {
        "resource_type": resource_type,
        "tenant_id": tenant_scope,
        "count": len(records),
        "logs": [
            {
                "id": record.id,
                "actor_id": record.actor_id,
                "action": record.action,
                "target_resource": record.target_resource,
                "verification_status": record.verification_status,
                "timestamp": record.timestamp.isoformat() if record.timestamp else None,
                "trace_id": record.trace_id,
            }
            for record in records
        ],
        "trace_id": get_current_trace_id(),
    }


# Note: The full FRIDAY integration gateway (POST /v1/friday/command,
# GET /v1/friday/health_summary, GET /v1/friday/priority_leads,
# GET /v1/friday/incidents) is implemented in cortex_api.friday_router and
# mounted separately in main.py.  The stub below is intentionally removed.
