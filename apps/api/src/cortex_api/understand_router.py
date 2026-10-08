"""Understand Layer: identity, scoring, analytics, memory, workflows, approvals.

Security contract (audit defect C4 + H1)
----------------------------------------
Every route requires authentication:

* Operator/dashboard routes use JWT RBAC (``CORTEX_VIEWER`` for reads,
  ``CORTEX_OPERATOR`` for mutations).
* ``/v1/identity/resolve`` is an internal service endpoint: it accepts a FRIDAY
  service key (``X-Friday-Api-Key``) *or* an operator JWT. A service caller may
  name the tenant explicitly; a JWT caller's tenant always comes from the token.
* Every read query is filtered by the authenticated ``tenant_id`` — no route
  ever trusts a client-supplied ``tenant_id`` query parameter.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from cortex_analytics import CohortEngine, FunnelEngine, OutcomeTracker, ScoringEngine
from cortex_identity import IdentityResolver
from cortex_intelligence import ContextBuilder
from cortex_memory import MemoryScope, MemoryStore
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from cortex_api.auth import Role, require_role, security, verify_friday_token, verify_jwt_token
from cortex_api.config import get_db_session, get_redis_client
from cortex_api.db_models import (
    ApprovalQueueModel,
    EventModel,
    IdentityLinkModel,
    LeadModel,
    ProfileModel,
    VisitorModel,
    WorkflowRunModel,
)

router = APIRouter(prefix="/v1", tags=["Understand Layer"])

identity_resolver = IdentityResolver()
scoring_engine = ScoringEngine()
funnel_engine = FunnelEngine()
cohort_engine = CohortEngine()
memory_store = MemoryStore()
context_builder = ContextBuilder()
outcome_tracker = OutcomeTracker()


async def service_or_operator_auth(
    x_friday_api_key: str | None = Header(None, alias="X-Friday-Api-Key"),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict[str, Any]:
    """Accept a FRIDAY service key or an operator JWT for internal endpoints."""
    if x_friday_api_key:
        return await verify_friday_token(x_friday_api_key)
    return await verify_jwt_token(credentials)


def resolve_tenant(auth: dict[str, Any], payload_tenant: str | None) -> str:
    """Derive the authoritative tenant for identity resolution."""
    token_tenant = auth.get("tenant_id")
    if token_tenant in (None, "system", "tenant_default") and payload_tenant:
        return payload_tenant
    if payload_tenant and payload_tenant != token_tenant:
        raise HTTPException(
            status_code=403,
            detail=f"Tenant mismatch: token tenant '{token_tenant}' cannot act on '{payload_tenant}'.",
        )
    return token_tenant or "tenant_default"


# ── 1. IDENTITY & PROFILES ───────────────────────────────────────────────────


@router.post("/identity/resolve")
async def resolve_identity_endpoint(
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db_session),
    auth: dict[str, Any] = Depends(service_or_operator_auth),
):
    """Internal identity resolution API (FRIDAY service key or operator JWT)."""
    visitor_id = payload.get("visitor_id")
    if not visitor_id:
        raise HTTPException(status_code=400, detail="visitor_id is required")

    tenant_id = resolve_tenant(auth, payload.get("tenant_id"))
    consent_granted = bool(payload.get("consent_granted", False))

    result = await identity_resolver.resolve_identity(
        db=db,
        visitor_id=visitor_id,
        user_id=payload.get("user_id"),
        email=payload.get("email"),
        device_fingerprint=payload.get("device_fingerprint"),
        tenant_id=tenant_id,
        site_id=payload.get("site_id", "default"),
        consent_granted=consent_granted,
        traits=payload.get("traits", {}),
        event_trigger=payload.get("event_trigger"),
    )
    return result


@router.get("/visitors/{visitor_id}/profile")
async def get_visitor_resolved_profile(
    visitor_id: str,
    db: AsyncSession = Depends(get_db_session),
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
):
    """Returns the resolved profile with linked identities for a visitor (tenant scoped)."""
    tenant_id = auth.get("tenant_id", "tenant_default")
    v_res = await db.execute(
        select(VisitorModel).where(VisitorModel.id == visitor_id, VisitorModel.tenant_id == tenant_id)
    )
    visitor = v_res.scalar_one_or_none()
    if not visitor:
        raise HTTPException(status_code=404, detail="Visitor not found")

    profile_data = None
    links_data = []

    if visitor.profile_id:
        p_res = await db.execute(
            select(ProfileModel).where(ProfileModel.id == visitor.profile_id, ProfileModel.tenant_id == tenant_id)
        )
        profile = p_res.scalar_one_or_none()
        if profile:
            profile_data = {
                "id": profile.id,
                "primary_email": profile.primary_email,
                "identities": profile.identities,
                "traits": profile.traits,
                "created_at": profile.created_at.isoformat() if profile.created_at else None,
            }

        l_res = await db.execute(
            select(IdentityLinkModel).where(
                IdentityLinkModel.target_id == visitor.profile_id,
                IdentityLinkModel.tenant_id == tenant_id,
            )
        )
        links_data = [
            {
                "link_id": link.id,
                "source_type": link.source_type,
                "source_value": link.source_value,
                "confidence": link.confidence,
            }
            for link in l_res.scalars().all()
        ]

    return {
        "visitor_id": visitor.id,
        "first_seen_at": visitor.first_seen_at.isoformat() if visitor.first_seen_at else None,
        "last_seen_at": visitor.last_seen_at.isoformat() if visitor.last_seen_at else None,
        "attributes": visitor.attributes,
        "profile": profile_data,
        "linked_identities": links_data,
    }


# ── 2. LEAD SCORING & TRENDS ─────────────────────────────────────────────────


@router.get("/leads/{lead_id}/score")
async def get_lead_score_with_history(
    lead_id: str,
    db: AsyncSession = Depends(get_db_session),
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
):
    """Returns the current lead score breakdown and score trend history."""
    tenant_id = auth.get("tenant_id", "tenant_default")
    lead_res = await db.execute(select(LeadModel).where(LeadModel.id == lead_id, LeadModel.tenant_id == tenant_id))
    lead = lead_res.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    history = await scoring_engine.get_score_history(db, lead_id)
    return {
        "lead_id": lead.id,
        "current_score": lead.score,
        "status": lead.status,
        "source": lead.source,
        "metadata": lead.lead_metadata,
        "score_history": history,
    }


# ── 3. ANALYTICS (FUNNELS, COHORTS, ATTRIBUTION) ─────────────────────────────


async def _tenant_events(db: AsyncSession, tenant_id: str, site_id: str, limit: int = 500, newest_first: bool = True):
    order = desc(EventModel.occurred_at) if newest_first else EventModel.occurred_at.asc()
    result = await db.execute(
        select(EventModel)
        .where(EventModel.site_id == site_id, EventModel.tenant_id == tenant_id)
        .order_by(order)
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/analytics/funnel")
async def get_funnel_analysis(
    steps: str | None = Query(None, description="Comma-separated step identifiers"),
    site_id: str = "default",
    db: AsyncSession = Depends(get_db_session),
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
):
    """Computes conversion rates and drop-off analysis for a multi-step funnel."""
    tenant_id = auth.get("tenant_id", "tenant_default")
    step_list = [step.strip() for step in steps.split(",")] if steps else ["page_view", "pricing", "demo", "checkout"]

    events = [
        {
            "type": event.type,
            "session_id": event.session_id,
            "data": event.data,
            "occurred_at": event.occurred_at.isoformat(),
        }
        for event in await _tenant_events(db, tenant_id, site_id)
    ]
    result = funnel_engine.analyze_funnel(events, step_list)
    if isinstance(result, dict):
        result.setdefault("tenant_id", tenant_id)
    return result


@router.get("/analytics/cohorts")
async def get_cohort_analysis(
    site_id: str = "default",
    db: AsyncSession = Depends(get_db_session),
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
):
    """Returns weekly visitor retention cohorts."""
    tenant_id = auth.get("tenant_id", "tenant_default")
    events = [
        {"actor_id": event.actor_id, "occurred_at": event.occurred_at.isoformat()}
        for event in await _tenant_events(db, tenant_id, site_id)
    ]
    return cohort_engine.compute_cohorts(events)


@router.get("/analytics/attribution")
async def get_attribution_analysis(
    site_id: str = "default",
    db: AsyncSession = Depends(get_db_session),
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
):
    """Calculates first-touch attribution from acquisition events."""
    tenant_id = auth.get("tenant_id", "tenant_default")
    attribution_counts: dict[str, int] = {}
    for event in await _tenant_events(db, tenant_id, site_id, newest_first=False):
        data = event.data or {}
        source = data.get("utm_source") or data.get("source") or "direct"
        attribution_counts[source] = attribution_counts.get(source, 0) + 1

    return {
        "site_id": site_id,
        "tenant_id": tenant_id,
        "first_touch_breakdown": attribution_counts,
        "total_touchpoints": sum(attribution_counts.values()),
    }


# ── 4. MEMORY SERVICE ────────────────────────────────────────────────────────


@router.get("/memory/{scope}/{scope_id}")
async def get_memory_entries(
    scope: str,
    scope_id: str,
    key: str | None = None,
    db: AsyncSession = Depends(get_db_session),
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
):
    """Retrieves scoped memory entries (visitor, lead, strategy, ...) for the caller's tenant."""
    try:
        MemoryScope(scope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown memory scope '{scope}'.") from exc

    tenant_id = auth.get("tenant_id", "tenant_default")
    entries = await memory_store.get(db=db, scope=scope, scope_id=scope_id, key=key, tenant_id=tenant_id)
    return {
        "scope": scope,
        "scope_id": scope_id,
        "tenant_id": tenant_id,
        "entries": [entry.model_dump(mode="json") for entry in entries],
    }


# ── 5. WORKFLOWS & AUTOMATION ────────────────────────────────────────────────

from cortex_workflow_engine import WorkflowStateMachine  # noqa: E402

WORKFLOW_EVENT_MAP = {
    "HIGH_INTENT_FOLLOWUP": "high_intent.detected",
    "LEAD_QUALIFICATION_ROUTING": "lead.qualification_requested",
    "ABANDONED_FORM_RECOVERY": "form.abandoned",
    "CONVERSION_DROP_DIAGNOSIS": "funnel.anomaly_detected",
    "CHURN_RISK_INTERVENTION": "churn.risk_detected",
}


@router.get("/workflows")
async def list_available_workflows(auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER))):
    """Returns definitions of all first-class operational workflows."""
    return [
        {
            "name": "HIGH_INTENT_FOLLOWUP",
            "description": "High intent detection -> business hours check -> email dispatch -> open/reply outcome tracking",
        },
        {
            "name": "LEAD_QUALIFICATION_ROUTING",
            "description": "Lead score computation -> AI qualification review -> route to sales tier",
        },
        {
            "name": "ABANDONED_FORM_RECOVERY",
            "description": "Form started without submit -> wait -> recovery email -> completion tracking",
        },
        {
            "name": "CONVERSION_DROP_DIAGNOSIS",
            "description": "Funnel anomaly detected -> slice segments -> AI debate mode -> auto-remediate",
        },
        {
            "name": "CHURN_RISK_INTERVENTION",
            "description": "Churn signals -> ChurnRiskAgent -> AI strategy -> win-back proposal",
        },
    ]


@router.post("/workflows/{workflow_name}/run")
async def trigger_workflow_run(
    workflow_name: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db_session),
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
):
    """Trigger a new execution run of a named workflow, scoped to the caller's tenant."""
    state_machine = WorkflowStateMachine(db=db)
    tenant_id = auth.get("tenant_id", "tenant_default")
    site_id = payload.get("site_id", "default")

    ctx = await state_machine.start_workflow(
        workflow_name=workflow_name,
        trigger_event=payload.get("trigger_event", {"type": WORKFLOW_EVENT_MAP.get(workflow_name, "manual_trigger")}),
        context_data=payload.get("context_data", {}),
        tenant_id=tenant_id,
        site_id=site_id,
    )

    if workflow_name == "HIGH_INTENT_FOLLOWUP":
        await state_machine.execute_high_intent_followup(ctx, None)
    elif workflow_name == "CONVERSION_DROP_DIAGNOSIS":
        await state_machine.execute_conversion_drop_diagnosis(ctx, None)

    return {
        "status": "started",
        "run_id": ctx.run_id,
        "tenant_id": tenant_id,
        "state": ctx.current_state.value,
        "steps": ctx.steps,
    }


@router.get("/workflows/runs/{run_id}")
async def get_workflow_run_details(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
):
    """Fetch execution run history and step timeline for a workflow run."""
    tenant_id = auth.get("tenant_id", "tenant_default")
    stmt = select(WorkflowRunModel).where(WorkflowRunModel.id == run_id, WorkflowRunModel.tenant_id == tenant_id)
    res = await db.execute(stmt)
    run = res.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")

    return {
        "run_id": run.id,
        "workflow_name": run.workflow_name,
        "trigger_event": run.trigger_event,
        "state": run.state,
        "steps": run.steps,
        "context_data": run.context_data,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


# ── 6. APPROVAL QUEUE (HUMAN-IN-THE-LOOP) ────────────────────────────────────


@router.get("/approvals/pending")
async def get_pending_approvals(
    db: AsyncSession = Depends(get_db_session),
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
):
    """Returns all pending approval items for the authenticated tenant."""
    tenant_id = auth.get("tenant_id", "tenant_default")
    stmt = (
        select(ApprovalQueueModel)
        .where(ApprovalQueueModel.tenant_id == tenant_id, ApprovalQueueModel.status == "pending")
        .order_by(desc(ApprovalQueueModel.risk_score))
    )
    res = await db.execute(stmt)
    return [
        {
            "id": item.id,
            "workflow_run_id": item.workflow_run_id,
            "action_type": item.action_type,
            "target": item.target,
            "params": item.params,
            "rationale": item.rationale,
            "execution_status": item.execution_status,
            "execution_result": item.execution_result,
            "evidence_refs": item.evidence_refs,
            "risk_score": item.risk_score,
            "expires_at": item.expires_at.isoformat() if item.expires_at else None,
        }
        for item in res.scalars().all()
    ]


async def _decide_action(
    db: AsyncSession,
    auth: dict[str, Any],
    action_id: str,
    approve: bool,
    payload: dict[str, Any] | None,
) -> ApprovalQueueModel:
    tenant_id = auth.get("tenant_id", "tenant_default")
    stmt = select(ApprovalQueueModel).where(
        ApprovalQueueModel.id == action_id, ApprovalQueueModel.tenant_id == tenant_id
    )
    res = await db.execute(stmt)
    item = res.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Approval item not found")
    if item.status != "pending":
        raise HTTPException(status_code=409, detail=f"Approval item is already '{item.status}'.")

    now = datetime.now(UTC)
    if item.expires_at and item.expires_at.replace(tzinfo=item.expires_at.tzinfo or UTC) <= now:
        item.status = "expired"
        item.decided_at = now
        item.decision_reason = "Auto-expired: decision window closed."
        await db.commit()
        raise HTTPException(status_code=409, detail="Approval request has expired.")

    operator = auth.get("sub", "cortex_operator")
    item.status = "approved" if approve else "rejected"
    item.decision_by = operator
    item.decided_at = now
    item.decision_reason = ((payload or {}).get("reason") if payload else None) or (
        "Approved by operator." if approve else "Operator rejected action"
    )
    await db.commit()
    return item


async def _execute_approved_action(
    db: AsyncSession, item: ApprovalQueueModel, redis_client: Any
) -> dict[str, Any]:
    """Execute an approved action through the tool bus, idempotent per approval.

    Closing the loop: approving used to only flip the row status — the action
    never ran. Now the approval executes the tool (Redis idempotency key per
    approval id, so a replayed approval cannot double-execute) and the outcome
    is recorded on the row.
    """
    from cortex_core.orchestrator import build_default_tool_bus
    from cortex_tool_runtime import Execution

    bus = build_default_tool_bus(redis_client=redis_client)
    execution = Execution(
        request_id=f"approval_{item.id}",
        tool_name=item.action_type,
        actor={"type": "operator", "id": item.decision_by or "cortex_operator"},
        reason=item.rationale,
        params=item.params,
        idempotency_key=f"approval_exec_{item.id}",
        approval={"approved": True, "approver_id": item.decision_by or "operator"},
    )
    try:
        result = await bus.execute(item.action_type, item.params, execution)
        status = str(result.get("status", "executed"))
        item.execution_status = status if status in {"executed", "blocked", "skipped"} else "executed"
        item.execution_result = result
        summary = {
            "status": item.execution_status,
            "tool": item.action_type,
            "result_status": status,
            "verification": result.get("verification"),
        }
    except Exception as exc:
        item.execution_status = "failed"
        item.execution_result = {"error": type(exc).__name__, "detail": str(exc)[:500]}
        summary = {"status": "failed", "tool": item.action_type, "error": type(exc).__name__}
    try:
        await db.commit()
    except Exception:
        await db.rollback()
    return summary


@router.post("/actions/{action_id}/approve")
async def approve_action(
    action_id: str,
    payload: dict[str, Any] | None = None,
    db: AsyncSession = Depends(get_db_session),
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
    redis_client: Any = Depends(get_redis_client),
):
    """Approve a pending high-impact action and execute it through the tool bus."""
    item = await _decide_action(db, auth, action_id, approve=True, payload=payload)
    execution_summary = await _execute_approved_action(db, item, redis_client)
    return {
        "status": "approved",
        "action_id": action_id,
        "decided_by": auth.get("sub"),
        "execution": execution_summary,
    }


@router.post("/actions/{action_id}/reject")
async def reject_action(
    action_id: str,
    payload: dict[str, Any] | None = None,
    db: AsyncSession = Depends(get_db_session),
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
):
    """Reject a pending high-impact action with an optional reason."""
    item = await _decide_action(db, auth, action_id, approve=False, payload=payload)
    return {"status": "rejected", "action_id": action_id, "reason": item.decision_reason}


# ── 7. STRATEGY PERFORMANCE & OUTCOMES ───────────────────────────────────────


@router.get("/strategies/performance")
async def get_strategies_performance(
    db: AsyncSession = Depends(get_db_session),
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
):
    """Returns PROVEN, PROBATION and DEMOTED strategy performance ratings."""
    return await outcome_tracker.get_strategy_performance(db, tenant_id=auth.get("tenant_id", "tenant_default"))
