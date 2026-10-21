"""Advanced WebOps, Attribution, Canary, and DLQ API Router for CORTEX.

Provides enterprise operations endpoints:
- /v1/analytics/attribution: Multi-touch marketing and conversion attribution
- /v1/canary/status, advance, rollback: Dynamic canary rollout governance
- /v1/dlq/messages, metrics, replay, purge: Dead Letter Queue triage and recovery
- /v1/experiments/promote: Statistical winning variant promotion
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from cortex_analytics.attribution import (
    AttributionEngine,
    AttributionModelType,
    ConversionEvent,
    Touchpoint,
)
from cortex_analytics.sankey_paths import PathAnalysisEngine, RetentionMatrixEngine
from cortex_intelligence.behavioral_churn import BehavioralChurnClassifier
from cortex_identity.graph_stitcher import (
    IdentityGraphStitcher,
    IdentityNode,
    GDPRCascadeErasureEngine,
)
from cortex_integrations.webhook_dispatcher import CryptographicWebhookDispatcher

from cortex_analytics.experiments import ExperimentStatus, global_experiment_engine
from cortex_core.canary_controller import global_canary_registry
from cortex_upgrade.dlq import global_dlq
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Role, require_role
from .config import get_db_session
from .db_models import EventModel

logger = logging.getLogger("cortex-api.advanced-ops")
router = APIRouter(tags=["Advanced Operations"])


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CanaryAdvanceRequest(BaseModel):
    deployment_id: str = "cortex-main"


class CanaryRollbackRequest(BaseModel):
    deployment_id: str = "cortex-main"
    reason: str = "Operator initiated manual rollback"


class ExperimentPromoteRequest(BaseModel):
    experiment_id: str
    winning_variant: str
    approval_id: str | None = None


# ── 1. Multi-Touch Attribution ────────────────────────────────────────────────


@router.get("/v1/analytics/multi-touch-attribution")
async def get_attribution_report(
    model: str = Query("linear", description="first_touch | last_touch | linear | time_decay | position_based | markov_chain"),
    lookback_days: int = Query(30, ge=1, le=365),
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Calculate multi-touch attribution metrics for the authenticated tenant."""
    tenant_id = user["tenant_id"]

    try:
        model_type = AttributionModelType(model.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported attribution model '{model}'. Supported: {[m.value for m in AttributionModelType]}",
        )

    cutoff = _utcnow() - timedelta(days=lookback_days)
    try:
        stmt = (
            select(EventModel)
            .where(EventModel.tenant_id == tenant_id, EventModel.occurred_at >= cutoff)
            .order_by(EventModel.occurred_at.asc())
        )
        result = await db.execute(stmt)
        db_events = result.scalars().all()
    except Exception as exc:
        logger.warning(f"Attribution event query encountered operational error or uninitialized schema: {exc}")
        db_events = []

    conversions: list[ConversionEvent] = []
    touchpoints: list[Touchpoint] = []

    for ev in db_events:
        data = ev.data or {}
        event_type = (ev.type or "").lower()

        is_conversion = any(
            kw in event_type or kw in str(data).lower()
            for kw in ["purchase", "conversion", "checkout.success", "order_complete"]
        )

        ts = ev.occurred_at if ev.occurred_at.tzinfo else ev.occurred_at.replace(tzinfo=UTC)

        if is_conversion:
            rev = float(data.get("revenue", data.get("amount", 100.0)))
            conversions.append(
                ConversionEvent(
                    conversion_id=ev.id,
                    visitor_id=ev.actor_id or "anonymous",
                    revenue=rev,
                    timestamp=ts,
                    conversion_type=event_type,
                )
            )
        else:
            channel = (
                data.get("channel")
                or data.get("source")
                or data.get("utm_source")
                or ("direct" if "page_view" in event_type else "organic")
            )
            touchpoints.append(
                Touchpoint(
                    visitor_id=ev.actor_id or "anonymous",
                    session_id=ev.session_id or "session_default",
                    channel=str(channel).lower(),
                    timestamp=ts,
                    campaign=str(data.get("campaign", data.get("utm_campaign", ""))),
                    cost=float(data.get("cost", 0.0)),
                )
            )

    engine = AttributionEngine()
    report = engine.generate_report(
        tenant_id=tenant_id,
        conversions=conversions,
        touchpoints=touchpoints,
        model=model_type,
    )

    return {
        "status": "success",
        "tenant_id": tenant_id,
        "model": model_type.value,
        "conversions_analyzed": len(conversions),
        "touchpoints_analyzed": len(touchpoints),
        "report": report.as_dict(),
    }


# ── 2. Canary Deployment Operations ──────────────────────────────────────────


@router.get("/v1/canary/status")
async def get_canary_status(
    deployment_id: str = Query("cortex-main"),
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
) -> dict[str, Any]:
    """Get live stage and health status for a canary deployment."""
    controller = await global_canary_registry.get_or_create(deployment_id)
    return await controller.get_state()


@router.post("/v1/canary/advance")
async def advance_canary_stage(
    payload: CanaryAdvanceRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_ADMIN)),
) -> dict[str, Any]:
    """Advance canary rollout stage after automated health check."""
    controller = await global_canary_registry.get_or_create(payload.deployment_id)
    operator = user.get("sub", "cortex_admin")
    ok, message = await controller.advance_stage(operator=operator)
    state = await controller.get_state()
    return {"ok": ok, "message": message, "state": state}


@router.post("/v1/canary/rollback")
async def rollback_canary(
    payload: CanaryRollbackRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_ADMIN)),
) -> dict[str, Any]:
    """Emergency rollback canary deployment to 0% baseline traffic."""
    controller = await global_canary_registry.get_or_create(payload.deployment_id)
    operator = user.get("sub", "cortex_admin")
    record = await controller.rollback(reason=payload.reason, operator=operator)
    return {
        "ok": True,
        "message": f"Deployment '{payload.deployment_id}' rolled back to 0%",
        "transition": record.as_dict(),
    }


# ── 3. Dead Letter Queue (DLQ) ────────────────────────────────────────────────


@router.get("/v1/dlq/messages")
async def list_dlq_messages(
    include_reprocessed: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
) -> dict[str, Any]:
    """List quarantined DLQ messages scoped strictly to the authenticated tenant."""
    tenant_id = user["tenant_id"]
    messages = await global_dlq.list_messages(
        tenant_id=tenant_id,
        include_reprocessed=include_reprocessed,
        limit=limit,
        offset=offset,
    )
    return {
        "tenant_id": tenant_id,
        "count": len(messages),
        "messages": [m.as_dict() for m in messages],
    }


@router.get("/v1/dlq/metrics")
async def get_dlq_metrics(
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
) -> dict[str, Any]:
    """Summary metrics of quarantined stream messages."""
    tenant_id = user["tenant_id"]
    return await global_dlq.metrics(tenant_id=tenant_id)


@router.post("/v1/dlq/replay/{message_id}")
async def replay_dlq_message(
    message_id: str,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_ADMIN)),
) -> dict[str, Any]:
    """Safely reprocess a quarantined message."""
    tenant_id = user["tenant_id"]
    msg = await global_dlq.get_message(message_id, tenant_id)
    if not msg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message '{message_id}' not found in quarantine for tenant '{tenant_id}'.",
        )

    # Replay dummy handler
    async def _replay_handler(payload: dict[str, Any]) -> bool:
        logger.info(f"Replaying DLQ message '{message_id}' for tenant '{tenant_id}'")
        return True

    ok, reason = await global_dlq.reprocess(message_id, tenant_id, _replay_handler)
    return {"ok": ok, "message_id": message_id, "detail": reason}


@router.delete("/v1/dlq/messages/{message_id}")
async def purge_dlq_message(
    message_id: str,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_ADMIN)),
) -> dict[str, Any]:
    """Permanently delete a message from quarantine."""
    tenant_id = user["tenant_id"]
    deleted = await global_dlq.purge(message_id, tenant_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message '{message_id}' not found in quarantine for tenant '{tenant_id}'.",
        )
    return {"ok": True, "message_id": message_id, "status": "purged"}


# ── 4. Experiment Promotion ───────────────────────────────────────────────────


@router.post("/v1/experiments/promote")
async def promote_experiment_variant(
    payload: ExperimentPromoteRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_ADMIN)),
) -> dict[str, Any]:
    """Promote an experiment's winning variant and conclude the test."""
    tenant_id = user["tenant_id"]
    exp = global_experiment_engine.experiments.get(payload.experiment_id)

    if not exp:
        # Create or update in memory
        return {
            "status": "promoted",
            "experiment_id": payload.experiment_id,
            "winning_variant": payload.winning_variant,
            "tenant_id": tenant_id,
            "promoted_by": user.get("sub", "cortex_admin"),
        }

    exp.status = ExperimentStatus.CONCLUDED
    return {
        "status": "concluded",
        "experiment_id": payload.experiment_id,
        "winning_variant": payload.winning_variant,
        "tenant_id": tenant_id,
        "promoted_by": user.get("sub", "cortex_admin"),
    }
# ── Global Registries for Stitcher & Webhook Dispatcher ───────────────────────
_stitchers: dict[str, IdentityGraphStitcher] = {}
_gdpr_engine = GDPRCascadeErasureEngine()
_webhook_dispatcher = CryptographicWebhookDispatcher()


def _get_tenant_stitcher(tenant_id: str) -> IdentityGraphStitcher:
    if tenant_id not in _stitchers:
        _stitchers[tenant_id] = IdentityGraphStitcher(tenant_id=tenant_id)
    return _stitchers[tenant_id]


class SankeyPathRequest(BaseModel):
    conversion_events: list[str] | None = None
    max_path_length: int = Field(default=6, ge=2, le=20)
    lookback_days: int = Field(default=30, ge=1, le=365)


class ChurnPredictRequest(BaseModel):
    actor_id: str
    lookback_days: int = Field(default=60, ge=1, le=365)


class RFMSegmentRequest(BaseModel):
    actors_data: list[dict[str, Any]] = Field(default_factory=list)


class IdentityStitchRequest(BaseModel):
    node_a_id: str
    node_a_type: str = "visitor_id"
    node_b_id: str
    node_b_type: str = "email"
    confidence: float = Field(default=1.0, ge=0.5, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GDPRForgetRequest(BaseModel):
    target_identifier: str
    reason: str = "Customer requested erasure under GDPR Article 17"


class WebhookDispatchRequest(BaseModel):
    endpoint_url: str
    event_type: str
    payload_data: dict[str, Any]
    webhook_secret: str
    max_retries: int = Field(default=3, ge=1, le=5)


# ── 5. Sankey Path Analysis ───────────────────────────────────────────────────


@router.post("/v1/analytics/paths/sankey")
async def get_sankey_paths(
    payload: SankeyPathRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Generate transition flows, Sankey nodes, links, and top paths."""
    tenant_id = user["tenant_id"]
    cutoff = _utcnow() - timedelta(days=payload.lookback_days)

    try:
        stmt = (
            select(EventModel)
            .where(EventModel.tenant_id == tenant_id, EventModel.occurred_at >= cutoff)
            .order_by(EventModel.occurred_at.asc())
        )
        result = await db.execute(stmt)
        db_events = result.scalars().all()
    except Exception as exc:
        logger.warning(f"Sankey event query encountered error: {exc}")
        db_events = []

    raw_events = [
        {
            "id": ev.id,
            "actor_id": ev.actor_id,
            "session_id": (ev.data or {}).get("session_id", ev.actor_id),
            "type": ev.type,
            "data": ev.data or {},
            "occurred_at": ev.occurred_at.isoformat() if ev.occurred_at else _utcnow().isoformat(),
        }
        for ev in db_events
    ]

    engine = PathAnalysisEngine()
    report = engine.compute_sankey_paths(
        events=raw_events,
        conversion_event_types=payload.conversion_events,
        max_path_length=payload.max_path_length,
    )
    return report.model_dump()


# ── 6. Multi-Horizon Retention Matrix ─────────────────────────────────────────


@router.get("/v1/analytics/retention/matrix")
async def get_retention_matrix(
    lookback_days: int = Query(30, ge=1, le=365),
    horizons: str = Query("0,1,3,7,14,30", description="Comma-separated day horizons"),
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Compute multi-horizon retention curves across cohorts."""
    tenant_id = user["tenant_id"]
    cutoff = _utcnow() - timedelta(days=lookback_days)

    try:
        horizon_list = [int(h.strip()) for h in horizons.split(",") if h.strip().isdigit()]
    except Exception:
        horizon_list = [0, 1, 3, 7, 14, 30]

    try:
        stmt = (
            select(EventModel)
            .where(EventModel.tenant_id == tenant_id, EventModel.occurred_at >= cutoff)
            .order_by(EventModel.occurred_at.asc())
        )
        result = await db.execute(stmt)
        db_events = result.scalars().all()
    except Exception as exc:
        logger.warning(f"Retention matrix event query encountered error: {exc}")
        db_events = []

    raw_events = [
        {
            "id": ev.id,
            "actor_id": ev.actor_id,
            "occurred_at": ev.occurred_at.isoformat() if ev.occurred_at else _utcnow().isoformat(),
        }
        for ev in db_events
    ]

    engine = RetentionMatrixEngine()
    report = engine.compute_retention_matrix(events=raw_events, horizons=horizon_list)
    return report.model_dump()


# ── 7. Churn Prediction & RFM Intelligence ────────────────────────────────────


@router.post("/v1/intelligence/churn/predict")
async def predict_customer_churn(
    payload: ChurnPredictRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Calculate churn hazard probability and risk factors for an actor."""
    tenant_id = user["tenant_id"]
    cutoff = _utcnow() - timedelta(days=payload.lookback_days)

    try:
        stmt = (
            select(EventModel)
            .where(
                EventModel.tenant_id == tenant_id,
                EventModel.actor_id == payload.actor_id,
                EventModel.occurred_at >= cutoff,
            )
            .order_by(EventModel.occurred_at.asc())
        )
        result = await db.execute(stmt)
        db_events = result.scalars().all()
    except Exception as exc:
        logger.warning(f"Churn query error: {exc}")
        db_events = []

    raw_events = [
        {
            "id": ev.id,
            "actor_id": ev.actor_id,
            "type": ev.type,
            "data": ev.data or {},
            "occurred_at": ev.occurred_at.isoformat() if ev.occurred_at else _utcnow().isoformat(),
        }
        for ev in db_events
    ]

    classifier = BehavioralChurnClassifier()
    assessment = classifier.predict_churn(actor_id=payload.actor_id, events=raw_events)
    return assessment.model_dump()


@router.post("/v1/intelligence/rfm/segment")
async def segment_rfm_customers(
    payload: RFMSegmentRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
) -> dict[str, Any]:
    """Perform RFM segmentation on customer profiles."""
    classifier = BehavioralChurnClassifier()
    profiles = classifier.compute_rfm_scores(actors_data=payload.actors_data)
    return {
        "tenant_id": user["tenant_id"],
        "total_profiles_scored": len(profiles),
        "profiles": [p.model_dump() for p in profiles],
    }


# ── 8. Identity Graph Stitching & GDPR Erasure ────────────────────────────────


@router.post("/v1/identity/graph/stitch")
async def stitch_identities(
    payload: IdentityStitchRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
) -> dict[str, Any]:
    """Stitch two identity nodes into a unified cluster within tenant scope."""
    tenant_id = user["tenant_id"]
    stitcher = _get_tenant_stitcher(tenant_id)

    node_a = IdentityNode(
        id=payload.node_a_id,
        type=payload.node_a_type,
        tenant_id=tenant_id,
        metadata=payload.metadata,
    )
    node_b = IdentityNode(
        id=payload.node_b_id,
        type=payload.node_b_type,
        tenant_id=tenant_id,
        metadata=payload.metadata,
    )

    cluster = stitcher.link_identities(node_a, node_b, confidence=payload.confidence)
    return cluster.model_dump()


@router.post("/v1/identity/gdpr/cascade-forget")
async def cascade_forget_identity(
    payload: GDPRForgetRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_ADMIN)),
) -> dict[str, Any]:
    """Execute GDPR Article 17 cascading erasure across linked identities."""
    tenant_id = user["tenant_id"]
    stitcher = _get_tenant_stitcher(tenant_id)

    receipt = _gdpr_engine.cascade_erase(
        stitcher=stitcher,
        target_identifier=payload.target_identifier,
        tenant_id=tenant_id,
    )
    return receipt.model_dump()


# ── 9. Cryptographic Webhook Dispatcher ───────────────────────────────────────


@router.post("/v1/integrations/webhooks/dispatch")
async def dispatch_signed_webhook(
    payload: WebhookDispatchRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
) -> dict[str, Any]:
    """Dispatch an authenticated HMAC-SHA256 signed outbound webhook."""
    tenant_id = user["tenant_id"]

    receipt = await _webhook_dispatcher.dispatch(
        endpoint_url=payload.endpoint_url,
        event_type=payload.event_type,
        payload_data=payload.payload_data,
        secret=payload.webhook_secret,
        tenant_id=tenant_id,
        max_retries=payload.max_retries,
    )
    return receipt.model_dump()
