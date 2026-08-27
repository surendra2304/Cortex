from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
import sys
import os

sys.path.insert(0, os.path.abspath("packages/identity/src"))
sys.path.insert(0, os.path.abspath("packages/analytics/src"))
sys.path.insert(0, os.path.abspath("packages/memory/src"))
sys.path.insert(0, os.path.abspath("packages/intelligence/src"))

from nexus_identity import IdentityResolver
from nexus_analytics import ScoringEngine, FunnelEngine, CohortEngine
from nexus_memory import MemoryStore, MemoryScope
from nexus_intelligence import ContextBuilder
from nexus_api.config import get_db_session
from nexus_api.db_models import ProfileModel, VisitorModel, LeadModel, EventModel, IdentityLinkModel

router = APIRouter(prefix="/v1", tags=["Understand Layer"])

identity_resolver = IdentityResolver()
scoring_engine = ScoringEngine()
funnel_engine = FunnelEngine()
cohort_engine = CohortEngine()
memory_store = MemoryStore()
context_builder = ContextBuilder()


# ── 1. IDENTITY & PROFILES ───────────────────────────────────────────────────

@router.post("/identity/resolve")
async def resolve_identity_endpoint(
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_db_session)
):
    """Internal identity resolution API."""
    visitor_id = payload.get("visitor_id")
    if not visitor_id:
        raise HTTPException(status_code=400, detail="visitor_id is required")

    result = await identity_resolver.resolve_identity(
        db=db,
        visitor_id=visitor_id,
        user_id=payload.get("user_id"),
        email=payload.get("email"),
        device_fingerprint=payload.get("device_fingerprint"),
        tenant_id=payload.get("tenant_id", "default"),
        site_id=payload.get("site_id", "default"),
        consent_granted=payload.get("consent_granted", True),
        traits=payload.get("traits", {}),
        event_trigger=payload.get("event_trigger")
    )
    return result


@router.get("/visitors/{visitor_id}/profile")
async def get_visitor_resolved_profile(
    visitor_id: str,
    db: AsyncSession = Depends(get_db_session)
):
    """Returns resolved profile with linked identities for a visitor."""
    v_res = await db.execute(select(VisitorModel).where(VisitorModel.id == visitor_id))
    visitor = v_res.scalar_one_or_none()
    if not visitor:
        raise HTTPException(status_code=404, detail="Visitor not found")

    profile_data = None
    links_data = []

    if visitor.profile_id:
        p_res = await db.execute(select(ProfileModel).where(ProfileModel.id == visitor.profile_id))
        profile = p_res.scalar_one_or_none()
        if profile:
            profile_data = {
                "id": profile.id,
                "primary_email": profile.primary_email,
                "identities": profile.identities,
                "traits": profile.traits,
                "created_at": profile.created_at.isoformat()
            }

        l_res = await db.execute(
            select(IdentityLinkModel).where(IdentityLinkModel.target_id == visitor.profile_id)
        )
        links_data = [
            {
                "link_id": l.id,
                "source_type": l.source_type,
                "source_value": l.source_value,
                "confidence": l.confidence
            }
            for l in l_res.scalars().all()
        ]

    return {
        "visitor_id": visitor.id,
        "first_seen_at": visitor.first_seen_at.isoformat() if visitor.first_seen_at else None,
        "last_seen_at": visitor.last_seen_at.isoformat() if visitor.last_seen_at else None,
        "attributes": visitor.attributes,
        "profile": profile_data,
        "linked_identities": links_data
    }


# ── 2. LEAD SCORING & TRENDS ─────────────────────────────────────────────────

@router.get("/leads/{lead_id}/score")
async def get_lead_score_with_history(
    lead_id: str,
    db: AsyncSession = Depends(get_db_session)
):
    """Returns current lead score breakdown + score trend history."""
    lead_res = await db.execute(select(LeadModel).where(LeadModel.id == lead_id))
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
        "score_history": history
    }


# ── 3. ANALYTICS (FUNNELS, COHORTS, ATTRIBUTION) ─────────────────────────────

@router.get("/analytics/funnel")
async def get_funnel_analysis(
    steps: Optional[str] = Query(None, description="Comma-separated step identifiers"),
    site_id: str = "default",
    db: AsyncSession = Depends(get_db_session)
):
    """Computes conversion rates and drop-off analysis for a multi-step funnel."""
    step_list = [s.strip() for s in steps.split(",")] if steps else [
        "page_view", "pricing", "demo", "checkout"
    ]

    events_res = await db.execute(
        select(EventModel).where(EventModel.site_id == site_id).order_by(desc(EventModel.occurred_at)).limit(500)
    )
    events = [
        {"type": e.type, "session_id": e.session_id, "data": e.data, "occurred_at": e.occurred_at.isoformat()}
        for e in events_res.scalars().all()
    ]

    return funnel_engine.analyze_funnel(events, step_list)


@router.get("/analytics/cohorts")
async def get_cohort_analysis(
    site_id: str = "default",
    db: AsyncSession = Depends(get_db_session)
):
    """Returns weekly visitor retention cohorts."""
    events_res = await db.execute(
        select(EventModel).where(EventModel.site_id == site_id).order_by(desc(EventModel.occurred_at)).limit(500)
    )
    events = [
        {"actor_id": e.actor_id, "occurred_at": e.occurred_at.isoformat()}
        for e in events_res.scalars().all()
    ]
    return cohort_engine.compute_cohorts(events)


@router.get("/analytics/attribution")
async def get_attribution_analysis(
    site_id: str = "default",
    db: AsyncSession = Depends(get_db_session)
):
    """Calculates first-touch attribution from acquisition events."""
    events_res = await db.execute(
        select(EventModel).where(EventModel.site_id == site_id).order_by(EventModel.occurred_at.asc()).limit(500)
    )
    attribution_counts: Dict[str, int] = {}
    for e in events_res.scalars().all():
        data = e.data or {}
        utm = data.get("utm_source") or data.get("source") or "direct"
        attribution_counts[utm] = attribution_counts.get(utm, 0) + 1

    return {
        "site_id": site_id,
        "first_touch_breakdown": attribution_counts,
        "total_touchpoints": sum(attribution_counts.values())
    }


# ── 4. MEMORY SERVICE ────────────────────────────────────────────────────────

@router.get("/memory/{scope}/{scope_id}")
async def get_memory_entries(
    scope: str,
    scope_id: str,
    key: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session)
):
    """Retrieves scoped memory entries (visitor, lead, strategy, etc.)."""
    entries = await memory_store.get(db=db, scope=scope, scope_id=scope_id, key=key)
    return {
        "scope": scope,
        "scope_id": scope_id,
        "entries": [e.model_dump(mode="json") for e in entries]
    }
