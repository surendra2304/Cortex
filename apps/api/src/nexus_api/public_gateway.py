from fastapi import APIRouter, Depends, HTTPException, Header, status
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
import sys
import os

sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/agents/src"))
sys.path.insert(0, os.path.abspath("packages/ai_universe_adapter/src"))

from nexus_core.models import Lead, Visitor, AuditRecord, Workflow
from nexus_agents import AgentRegistry, AgentInput
from nexus_ai_universe_adapter import IntelligenceRequest, IntelligenceResponse, AIUniverseClient
from nexus_api.tracing import get_current_trace_id

router = APIRouter(prefix="/v1", tags=["Public API Gateway"])

# In-memory data store stubs
VISITORS_DB: Dict[str, Dict[str, Any]] = {
    "vis_123": {
        "id": "vis_123",
        "tenant_id": "tenant_1",
        "site_id": "site_main",
        "attributes": {"country": "US", "browser": "Chrome"},
        "first_seen_at": datetime.utcnow().isoformat()
    }
}
LEADS_DB: List[Dict[str, Any]] = []
ACTIONS_DB: Dict[str, Dict[str, Any]] = {
    "act_high_1": {
        "id": "act_high_1",
        "action_type": "banner_injection",
        "status": "pending_approval",
        "params": {"variant": "annual_discount_banner"},
        "reason": "High impact conversion banner"
    }
}
AUDIT_DB: List[Dict[str, Any]] = []

agent_registry = AgentRegistry()
ai_client = AIUniverseClient()


# Auth Stub
async def verify_jwt_token(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not authorization:
        # Default mock user context for development / API access
        return {"sub": "usr_dev_123", "role": "admin", "tenant_id": "tenant_default"}
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token format")
    token = authorization.split(" ")[1]
    return {"sub": f"usr_{token[:8]}", "role": "operator", "tenant_id": "tenant_default"}


# 1. Visitors
@router.get("/visitors/{visitor_id}")
async def get_visitor(visitor_id: str, auth: Dict[str, Any] = Depends(verify_jwt_token)):
    visitor = VISITORS_DB.get(visitor_id)
    if not visitor:
        raise HTTPException(status_code=404, detail="Visitor not found")
    return {"visitor": visitor, "trace_id": get_current_trace_id()}


# 2. Leads
@router.get("/leads")
async def list_leads(auth: Dict[str, Any] = Depends(verify_jwt_token)):
    return {"leads": LEADS_DB, "total": len(LEADS_DB), "trace_id": get_current_trace_id()}


@router.post("/leads")
async def create_lead(payload: Dict[str, Any], auth: Dict[str, Any] = Depends(verify_jwt_token)):
    lead_id = f"lead_{uuid.uuid4().hex[:8]}"
    lead_data = {
        "id": lead_id,
        "tenant_id": auth["tenant_id"],
        "score": payload.get("score", 50.0),
        "status": payload.get("status", "new"),
        "created_at": datetime.utcnow().isoformat(),
        "metadata": payload
    }
    LEADS_DB.append(lead_data)
    return {"lead": lead_data, "trace_id": get_current_trace_id()}


# 3. Analytics
@router.get("/analytics/{metric}")
async def get_analytics(metric: str, auth: Dict[str, Any] = Depends(verify_jwt_token)):
    return {
        "metric": metric,
        "tenant_id": auth["tenant_id"],
        "values": [
            {"timestamp": "2026-08-27T10:00:00Z", "value": 142},
            {"timestamp": "2026-08-27T11:00:00Z", "value": 189},
            {"timestamp": "2026-08-27T12:00:00Z", "value": 234}
        ],
        "trace_id": get_current_trace_id()
    }


# 4. Intelligence Requests
@router.post("/intelligence/requests")
async def create_intelligence_request(req: IntelligenceRequest, auth: Dict[str, Any] = Depends(verify_jwt_token)):
    res = await ai_client.evaluate(req)
    return {"response": res.model_dump(mode="json"), "trace_id": get_current_trace_id()}


# 5. Agents
@router.get("/agents")
async def list_agents(auth: Dict[str, Any] = Depends(verify_jwt_token)):
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
async def run_agent(agent_id: str, input_data: AgentInput, auth: Dict[str, Any] = Depends(verify_jwt_token)):
    agent = agent_registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found in registry")
    output = await agent.process(input_data)
    return {"output": output.model_dump(mode="json"), "trace_id": get_current_trace_id()}


# 6. Workflows
@router.get("/workflows")
async def list_workflows(auth: Dict[str, Any] = Depends(verify_jwt_token)):
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


# 7. Action Approvals (Governance)
@router.post("/actions/{action_id}/approve")
async def approve_action(action_id: str, payload: Dict[str, Any] = {}, auth: Dict[str, Any] = Depends(verify_jwt_token)):
    action = ACTIONS_DB.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    action["status"] = "approved"
    action["approved_by"] = auth["sub"]
    action["approved_at"] = datetime.utcnow().isoformat()
    return {"status": "approved", "action": action, "trace_id": get_current_trace_id()}


# 8. Audit Logs
@router.get("/audit/{resource_type}")
async def get_audit_logs(resource_type: str, auth: Dict[str, Any] = Depends(verify_jwt_token)):
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


# 9. Friday Command Bridge
@router.post("/friday/command")
async def execute_friday_command(payload: Dict[str, Any], auth: Dict[str, Any] = Depends(verify_jwt_token)):
    command = payload.get("command", "")
    return {
        "status": "acknowledged",
        "command": command,
        "executed_by": "FRIDAY_SUPERVISOR_BRIDGE",
        "timestamp": datetime.utcnow().isoformat(),
        "trace_id": get_current_trace_id()
    }
