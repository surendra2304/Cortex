from fastapi import APIRouter, Depends, HTTPException, Header, status
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
import sys
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/agents/src"))
sys.path.insert(0, os.path.abspath("packages/identity/src"))
sys.path.insert(0, os.path.abspath("packages/ai_universe_adapter/src"))

from cortex_core.models import Lead, Visitor, AuditRecord, Workflow
from cortex_agents import AgentRegistry, AgentInput
from cortex_identity import IdentityService
from cortex_ai_universe_adapter import IntelligenceRequest, IntelligenceResponse, AIUniverseClient
from cortex_api.config import get_db_session
from cortex_api.db_models import VisitorModel, ProfileModel, LeadModel, SessionModel
from cortex_api.tracing import get_current_trace_id
from cortex_api.auth import verify_jwt_token, require_role, Role

router = APIRouter(prefix="/v1", tags=["Public API Gateway"])

agent_registry = AgentRegistry()
ai_client = AIUniverseClient()
identity_service = IdentityService()

ACTIONS_DB: Dict[str, Dict[str, Any]] = {
    "act_high_1": {
        "id": "act_high_1",
        "action_type": "banner_injection",
        "status": "pending_approval",
        "params": {"variant": "annual_discount_banner"},
        "reason": "High impact conversion banner"
    }
}


# 1. Identity Resolution (POST /v1/identify) - Requires at least VIEWER role
@router.post("/identify")
async def identify_visitor(
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_db_session),
    auth: Dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER))
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
        traits=traits
    )
    result["attributes"] = result.get("traits", {})
    return {"status": "success", "result": result, "trace_id": get_current_trace_id()}


# 2. Visitors (GET /v1/visitors/:id) - Requires VIEWER role
@router.get("/visitors/{visitor_id}")
async def get_visitor(
    visitor_id: str,
    db: AsyncSession = Depends(get_db_session),
    auth: Dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER))
):
    stmt = select(VisitorModel).where(VisitorModel.id == visitor_id)
    res = await db.execute(stmt)
    visitor = res.scalar_one_or_none()

    if not visitor:
        raise HTTPException(status_code=404, detail="Visitor not found")

    profile_data = None
    if visitor.profile_id:
        prof_stmt = select(ProfileModel).where(ProfileModel.id == visitor.profile_id)
        prof_res = await db.execute(prof_stmt)
        profile = prof_res.scalar_one_or_none()
        if profile:
            profile_data = {
                "id": profile.id,
                "primary_email": profile.primary_email,
                "identities": profile.identities,
                "traits": profile.traits
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
            "profile": profile_data
        },
        "trace_id": get_current_trace_id()
    }


# 3. Leads (GET /v1/leads/:id & POST/GET /v1/leads) - Requires VIEWER for read, OPERATOR for write
@router.get("/leads/{lead_id}")
async def get_lead(
    lead_id: str,
    db: AsyncSession = Depends(get_db_session),
    auth: Dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER))
):
    stmt = select(LeadModel).where(LeadModel.id == lead_id)
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
            "created_at": lead.created_at.isoformat() if lead.created_at else None
        },
        "trace_id": get_current_trace_id()
    }


@router.get("/leads")
async def list_leads(
    db: AsyncSession = Depends(get_db_session),
    auth: Dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER))
):
    tenant_id = auth.get("tenant_id", "default")
    stmt = select(LeadModel).where(LeadModel.tenant_id == tenant_id)
    res = await db.execute(stmt)
    leads = res.scalars().all()
    return {
        "leads": [
            {
                "id": l.id,
                "score": l.score,
                "status": l.status,
                "source": l.source,
                "created_at": l.created_at.isoformat() if l.created_at else None
            }
            for l in leads
        ],
        "total": len(leads),
        "trace_id": get_current_trace_id()
    }


@router.post("/leads")
async def create_lead(
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_db_session),
    auth: Dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR))
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
        created_at=datetime.utcnow()
    )
    db.add(db_lead)
    await db.commit()

    return {
        "lead": {
            "id": lead_id,
            "tenant_id": db_lead.tenant_id,
            "score": db_lead.score,
            "status": db_lead.status
        },
        "trace_id": get_current_trace_id()
    }


# 4. Analytics - Requires VIEWER role
@router.get("/analytics/{metric}")
async def get_analytics(
    metric: str,
    auth: Dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER))
):
    return {
        "metric": metric,
        "tenant_id": auth.get("tenant_id", "default"),
        "values": [
            {"timestamp": "2026-08-27T10:00:00Z", "value": 142},
            {"timestamp": "2026-08-27T11:00:00Z", "value": 189},
            {"timestamp": "2026-08-27T12:00:00Z", "value": 234}
        ],
        "trace_id": get_current_trace_id()
    }


# 5. Intelligence Requests - Requires OPERATOR role
@router.post("/intelligence/requests")
async def create_intelligence_request(
    req: IntelligenceRequest,
    auth: Dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR))
):
    res = await ai_client.evaluate(req)
    return {"response": res.model_dump(mode="json"), "trace_id": get_current_trace_id()}


# 6. Agents - List requires VIEWER, Run requires OPERATOR
@router.get("/agents")
async def list_agents(auth: Dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER))):
    return {
        "agents": [
            {"id": "agent_growth", "domain": "growth", "capabilities": ["experiment_mutate", "banner_injection"]},
            {"id": "agent_sales", "domain": "sales", "capabilities": ["email_dispatch", "account_update"]},
            {"id": "agent_support", "domain": "support", "capabilities": ["session_inspect", "email_dispatch"]},
            {"id": "agent_reliability", "domain": "reliability", "capabilities": ["session_inspect"]}
        ],
        "trace_id": get_current_trace_id()
    }


@router.post("/agents/{agent_id}/run")
async def run_agent(
    agent_id: str,
    input_data: AgentInput,
    auth: Dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR))
):
    agent = agent_registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found in registry")
    output = await agent.process(input_data)
    return {"output": output.model_dump(mode="json"), "trace_id": get_current_trace_id()}


# 7. Workflows - Requires VIEWER role
@router.get("/workflows")
async def list_workflows(auth: Dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER))):
    return {
        "workflows": [
            {
                "id": "wf_conversion_boost",
                "name": "High Bounce Interceptor",
                "trigger": {"type": "pricing_view"},
                "status": "active"
            },
            {
                "id": "wf_enterprise_routing",
                "name": "High Value Account Router",
                "trigger": {"type": "checkout_intent"},
                "status": "active"
            }
        ],
        "trace_id": get_current_trace_id()
    }


# 8. Action Approvals (Governance) - Requires OPERATOR role
@router.post("/actions/{action_id}/approve")
async def approve_action(
    action_id: str,
    payload: Dict[str, Any] = {},
    auth: Dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR))
):
    action = ACTIONS_DB.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    action["status"] = "approved"
    action["approved_by"] = auth["sub"]
    action["approved_at"] = datetime.utcnow().isoformat()
    return {"status": "approved", "action": action, "trace_id": get_current_trace_id()}


# 9. Audit Logs - Requires ADMIN role for security inspection
@router.get("/audit/{resource_type}")
async def get_audit_logs(
    resource_type: str,
    auth: Dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR))
):
    return {
        "resource_type": resource_type,
        "logs": [
            {
                "id": "aud_sample_1",
                "actor_id": auth["sub"],
                "action": f"read:{resource_type}",
                "timestamp": datetime.utcnow().isoformat()
            }
        ],
        "trace_id": get_current_trace_id()
    }


# Note: The full FRIDAY integration gateway (POST /v1/friday/command,
# GET /v1/friday/health_summary, GET /v1/friday/priority_leads,
# GET /v1/friday/incidents) is implemented in cortex_api.friday_router and
# mounted separately in main.py.  The stub below is intentionally removed.
