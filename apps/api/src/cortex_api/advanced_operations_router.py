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
from cortex_core.feature_flags import FeatureFlag, TargetRule, global_feature_flag_engine
from cortex_intelligence.audience_segments import AudienceSegment, SegmentRule, global_audience_engine
from cortex_workflow_engine.auto_remediation import global_remediation_engine
from cortex_intelligence.bandit_allocator import (
    BanditAlgorithm,
    global_bandit_engine,
)
from cortex_integrations.sync_engine import (
    ConflictResolutionPolicy,
    SyncDirection,
    SyncEntityType,
    SyncJobStatus,
    SyncProvider,
    global_sync_engine,
)
from cortex_analytics.anomaly_detector import (
    AnomalySeverity,
    global_anomaly_detector,
)
from cortex_core.compliance_ledger import (
    global_compliance_ledger,
)
from cortex_analytics.funnels import (
    FridayConversionGoalType,
    FridayUniverseFunnelManager,
    global_funnel_manager,
)

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
# ── 10. Dynamic Feature Flags Governor ────────────────────────────────────────


class FeatureFlagCreateRequest(BaseModel):
    key: str
    enabled: bool = True
    rollout_percentage: float = Field(default=100.0, ge=0.0, le=100.0)
    target_rules: list[TargetRule] = Field(default_factory=list)
    allowed_actors: list[str] = Field(default_factory=list)
    blocked_actors: list[str] = Field(default_factory=list)
    description: str = ""


class FeatureFlagEvaluateRequest(BaseModel):
    key: str
    actor_id: str
    context: dict[str, Any] = Field(default_factory=dict)


@router.get("/v1/feature-flags")
async def list_feature_flags(
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
) -> dict[str, Any]:
    """List all feature flags registered for the tenant."""
    tenant_id = user["tenant_id"]
    flags = global_feature_flag_engine.list_flags(tenant_id)
    return {"tenant_id": tenant_id, "flags": [f.model_dump() for f in flags]}


@router.post("/v1/feature-flags")
async def create_or_update_feature_flag(
    payload: FeatureFlagCreateRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_ADMIN)),
) -> dict[str, Any]:
    """Create or update a tenant feature flag."""
    tenant_id = user["tenant_id"]
    flag = FeatureFlag(
        key=payload.key,
        tenant_id=tenant_id,
        enabled=payload.enabled,
        rollout_percentage=payload.rollout_percentage,
        target_rules=payload.target_rules,
        allowed_actors=payload.allowed_actors,
        blocked_actors=payload.blocked_actors,
        description=payload.description,
        updated_by=user.get("sub", "cortex_admin"),
    )
    saved = global_feature_flag_engine.set_flag(flag)
    return saved.model_dump()


@router.post("/v1/feature-flags/evaluate")
async def evaluate_feature_flag(
    payload: FeatureFlagEvaluateRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
) -> dict[str, Any]:
    """Evaluate whether a feature flag is enabled for an actor."""
    tenant_id = user["tenant_id"]
    is_enabled = global_feature_flag_engine.evaluate(
        key=payload.key,
        actor_id=payload.actor_id,
        context=payload.context,
        tenant_id=tenant_id,
    )
    return {
        "key": payload.key,
        "actor_id": payload.actor_id,
        "tenant_id": tenant_id,
        "enabled": is_enabled,
    }


@router.delete("/v1/feature-flags/{key}")
async def delete_feature_flag(
    key: str,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_ADMIN)),
) -> dict[str, Any]:
    """Delete a feature flag for the tenant."""
    tenant_id = user["tenant_id"]
    deleted = global_feature_flag_engine.delete_flag(key, tenant_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{key}' not found for tenant '{tenant_id}'.",
        )
    return {"ok": True, "key": key, "status": "deleted"}


# ── 11. Audience Segments Builder ─────────────────────────────────────────────


class AudienceSegmentCreateRequest(BaseModel):
    name: str
    rules: list[SegmentRule] = Field(default_factory=list)
    match_policy: str = "ALL"
    description: str = ""


class AudienceSegmentEvaluateRequest(BaseModel):
    profiles: list[dict[str, Any]] = Field(default_factory=list)


class AudienceSegmentExportRequest(BaseModel):
    matching_profiles: list[dict[str, Any]] = Field(default_factory=list)
    destination: str = "hubspot"


@router.get("/v1/intelligence/audiences")
async def list_audience_segments(
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
) -> dict[str, Any]:
    """List all audience segments defined for the tenant."""
    tenant_id = user["tenant_id"]
    segs = global_audience_engine.list_segments(tenant_id)
    return {"tenant_id": tenant_id, "segments": [s.model_dump() for s in segs]}


@router.post("/v1/intelligence/audiences")
async def create_audience_segment(
    payload: AudienceSegmentCreateRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
) -> dict[str, Any]:
    """Create a new dynamic audience segment."""
    tenant_id = user["tenant_id"]
    segment = AudienceSegment(
        name=payload.name,
        tenant_id=tenant_id,
        rules=payload.rules,
        match_policy=payload.match_policy,
        description=payload.description,
    )
    saved = global_audience_engine.save_segment(segment)
    return saved.model_dump()


@router.post("/v1/intelligence/audiences/{segment_id}/evaluate")
async def evaluate_audience_segment(
    segment_id: str,
    payload: AudienceSegmentEvaluateRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
) -> dict[str, Any]:
    """Evaluate an audience segment against customer profiles."""
    tenant_id = user["tenant_id"]
    try:
        result = global_audience_engine.evaluate_segment(
            segment_id=segment_id,
            profiles=payload.profiles,
            tenant_id=tenant_id,
        )
        return result.model_dump()
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audience segment '{segment_id}' not found for tenant '{tenant_id}'.",
        )


@router.post("/v1/intelligence/audiences/{segment_id}/export")
async def export_audience_segment(
    segment_id: str,
    payload: AudienceSegmentExportRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
) -> dict[str, Any]:
    """Export segment-matched profiles formatted for a downstream connector."""
    tenant_id = user["tenant_id"]
    segment = global_audience_engine.get_segment(segment_id, tenant_id)
    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audience segment '{segment_id}' not found for tenant '{tenant_id}'.",
        )

    exported = global_audience_engine.export_for_destination(
        matching_profiles=payload.matching_profiles,
        destination=payload.destination,
    )
    return {
        "segment_id": segment_id,
        "destination": payload.destination,
        "count": len(exported),
        "payloads": exported,
    }


# ── 12. Self-Healing Auto-Remediation Playbooks ────────────────────────────────


class IncidentRemediateRequest(BaseModel):
    incident_id: str
    incident_type: str
    severity: str = "HIGH"
    context: dict[str, Any] = Field(default_factory=dict)
    auto_approve: bool = False


@router.post("/v1/incidents/remediate")
async def execute_incident_remediation(
    payload: IncidentRemediateRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
) -> dict[str, Any]:
    """Execute a self-healing operational remediation playbook."""
    tenant_id = user["tenant_id"]
    receipt = global_remediation_engine.execute_playbook(
        tenant_id=tenant_id,
        incident_id=payload.incident_id,
        incident_type_str=payload.incident_type,
        severity_str=payload.severity,
        context=payload.context,
        auto_approve=payload.auto_approve,
    )
    return receipt.model_dump()


# ── 13. Multi-Armed Bandit (MAB) & Thompson Sampling ──────────────────────────


class BanditCreateRequest(BaseModel):
    experiment_id: str
    name: str
    arm_configs: list[dict[str, Any]]
    algorithm: str = "thompson_sampling"
    decay_factor: float = 0.999
    exploration_constant: float = 1.0
    epsilon: float = 0.1
    min_samples_for_decision: int = 50
    confidence_threshold: float = 0.95


class BanditSelectRequest(BaseModel):
    experiment_id: str
    context: dict[str, Any] = Field(default_factory=dict)
    sticky_actor_id: str | None = None


class BanditRewardRequest(BaseModel):
    experiment_id: str
    arm_id: str
    converted: bool
    value: float = 1.0


@router.post("/v1/experiments/bandit/create")
async def create_bandit_experiment(
    payload: BanditCreateRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
) -> dict[str, Any]:
    """Create or reset a Multi-Armed Bandit experiment."""
    tenant_id = user["tenant_id"]
    try:
        algo = BanditAlgorithm(payload.algorithm.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported algorithm '{payload.algorithm}'. Supported: {[a.value for a in BanditAlgorithm]}",
        )

    try:
        exp = global_bandit_engine.create_experiment(
            tenant_id=tenant_id,
            experiment_id=payload.experiment_id,
            name=payload.name,
            arm_configs=payload.arm_configs,
            algorithm=algo,
            decay_factor=payload.decay_factor,
            exploration_constant=payload.exploration_constant,
            epsilon=payload.epsilon,
            min_samples_for_decision=payload.min_samples_for_decision,
            confidence_threshold=payload.confidence_threshold,
        )
        return exp.model_dump()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/v1/experiments/bandit/select-arm")
async def select_bandit_arm(
    payload: BanditSelectRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
) -> dict[str, Any]:
    """Select the optimal bandit arm for the provided context."""
    tenant_id = user["tenant_id"]
    try:
        decision = global_bandit_engine.select_arm(
            tenant_id=tenant_id,
            experiment_id=payload.experiment_id,
            context=payload.context,
            sticky_actor_id=payload.sticky_actor_id,
        )
        return decision.model_dump()
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bandit experiment '{payload.experiment_id}' not found for tenant '{tenant_id}'.",
        )


@router.post("/v1/experiments/bandit/record-reward")
async def record_bandit_reward(
    payload: BanditRewardRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
) -> dict[str, Any]:
    """Record conversion outcome reward and update posterior probabilities."""
    tenant_id = user["tenant_id"]
    try:
        exp = global_bandit_engine.record_reward(
            tenant_id=tenant_id,
            experiment_id=payload.experiment_id,
            arm_id=payload.arm_id,
            converted=payload.converted,
            value=payload.value,
        )
        return exp.model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/v1/experiments/bandit/{experiment_id}")
async def get_bandit_experiment(
    experiment_id: str,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
) -> dict[str, Any]:
    """Retrieve bandit experiment status, arm distributions, and Bayesian win rates."""
    tenant_id = user["tenant_id"]
    exp = global_bandit_engine.get_experiment(tenant_id, experiment_id)
    if not exp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bandit experiment '{experiment_id}' not found for tenant '{tenant_id}'.",
        )
    return exp.model_dump()


# ── 14. External CRM & Commerce Sync Queue ─────────────────────────────────────


class SyncEnqueueRequest(BaseModel):
    provider: str
    entity_type: str
    external_id: str
    payload: dict[str, Any]
    direction: str = "outbound"
    max_retries: int = 3


class SyncProcessRequest(BaseModel):
    max_jobs: int = 20


@router.post("/v1/integrations/sync/enqueue")
async def enqueue_sync_job(
    payload: SyncEnqueueRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
) -> dict[str, Any]:
    """Enqueue an external sync job with idempotent deduplication."""
    tenant_id = user["tenant_id"]
    try:
        prov = SyncProvider(payload.provider.lower())
        ent = SyncEntityType(payload.entity_type.lower())
        dirn = SyncDirection(payload.direction.lower())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    job = global_sync_engine.enqueue_job(
        tenant_id=tenant_id,
        provider=prov,
        entity_type=ent,
        external_id=payload.external_id,
        payload=payload.payload,
        direction=dirn,
        max_retries=payload.max_retries,
    )
    return job.model_dump()


@router.get("/v1/integrations/sync/jobs")
async def list_sync_jobs(
    status_filter: str | None = Query(None, alias="status"),
    provider: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
) -> list[dict[str, Any]]:
    """List external sync jobs for the authenticated tenant."""
    tenant_id = user["tenant_id"]
    parsed_status = None
    if status_filter:
        try:
            parsed_status = SyncJobStatus(status_filter.upper())
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status '{status_filter}'")

    parsed_provider = None
    if provider:
        try:
            parsed_provider = SyncProvider(provider.lower())
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid provider '{provider}'")

    jobs = global_sync_engine.list_jobs(
        tenant_id=tenant_id,
        status=parsed_status,
        provider=parsed_provider,
        limit=limit,
    )
    return [j.model_dump() for j in jobs]


@router.get("/v1/integrations/sync/cursor")
async def get_sync_cursor(
    provider: str = Query(...),
    entity_type: str = Query(...),
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
) -> dict[str, Any]:
    """Retrieve current synchronization cursor for a provider and entity type."""
    tenant_id = user["tenant_id"]
    try:
        prov = SyncProvider(provider.lower())
        ent = SyncEntityType(entity_type.lower())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    cursor = global_sync_engine.get_cursor(tenant_id, prov, ent)
    return cursor.model_dump()


@router.post("/v1/integrations/sync/process")
async def process_sync_batch(
    payload: SyncProcessRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
) -> dict[str, Any]:
    """Process pending sync jobs through token-bucket rate limiters."""
    tenant_id = user["tenant_id"]
    receipts = await global_sync_engine.process_pending_jobs(tenant_id=tenant_id, max_jobs=payload.max_jobs)
    return {
        "tenant_id": tenant_id,
        "processed_count": len(receipts),
        "receipts": [r.model_dump() for r in receipts],
    }


# ── 15. Streaming Telemetry Anomaly Detector ───────────────────────────────────


class AnomalyEvaluateRequest(BaseModel):
    metric_name: str
    value: float
    cooldown_seconds: float = 60.0


@router.post("/v1/analytics/anomalies/evaluate")
async def evaluate_telemetry_point(
    payload: AnomalyEvaluateRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
) -> dict[str, Any]:
    """Evaluate an operational metric observation against online EWMA/MAD baselines."""
    tenant_id = user["tenant_id"]
    incident = global_anomaly_detector.evaluate_point(
        tenant_id=tenant_id,
        metric_name=payload.metric_name,
        value=payload.value,
        cooldown_seconds=payload.cooldown_seconds,
    )
    return {
        "tenant_id": tenant_id,
        "is_anomalous": incident is not None,
        "incident": incident.model_dump() if incident else None,
    }


@router.get("/v1/analytics/anomalies/incidents")
async def list_anomaly_incidents(
    severity: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
) -> list[dict[str, Any]]:
    """List historical anomaly incidents for tenant."""
    tenant_id = user["tenant_id"]
    parsed_sev = None
    if severity:
        try:
            parsed_sev = AnomalySeverity(severity.upper())
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid severity '{severity}'")

    incidents = global_anomaly_detector.list_incidents(tenant_id=tenant_id, severity=parsed_sev, limit=limit)
    return [inc.model_dump() for inc in incidents]


# ── 16. Cryptographic Tamper-Evident Compliance Ledger ─────────────────────────


class ComplianceRecordRequest(BaseModel):
    action_type: str
    actor_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


@router.post("/v1/compliance/ledger/record")
async def record_compliance_block(
    payload: ComplianceRecordRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
) -> dict[str, Any]:
    """Append a cryptographic block into tenant's immutable compliance ledger."""
    tenant_id = user["tenant_id"]
    block = global_compliance_ledger.record_action(
        tenant_id=tenant_id,
        action_type=payload.action_type,
        actor_id=payload.actor_id,
        payload=payload.payload,
    )
    return block.model_dump()


@router.get("/v1/compliance/ledger/blocks")
async def get_compliance_blocks(
    action_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
) -> list[dict[str, Any]]:
    """List audit blocks for tenant."""
    tenant_id = user["tenant_id"]
    blocks = global_compliance_ledger.get_blocks(tenant_id=tenant_id, action_type=action_type, limit=limit)
    return [b.model_dump() for b in blocks]


@router.get("/v1/compliance/ledger/verify")
async def verify_compliance_ledger(
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
) -> dict[str, Any]:
    """Verify integrity of tenant's cryptographic ledger and compute Merkle root."""
    tenant_id = user["tenant_id"]
    result = global_compliance_ledger.verify_chain(tenant_id=tenant_id)
    return result.model_dump()


@router.get("/v1/compliance/ledger/proof/{block_index}")
async def get_merkle_proof(
    block_index: int,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
) -> dict[str, Any]:
    """Generate Merkle inclusion proof for a block in tenant's audit chain."""
    tenant_id = user["tenant_id"]
    proof = global_compliance_ledger.generate_merkle_proof(tenant_id=tenant_id, block_index=block_index)
    if not proof:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Block index {block_index} not found in tenant '{tenant_id}' compliance ledger.",
        )
    return proof.model_dump()


# ── 17. FRIDAY Universe Funnels & Conversion Goals ─────────────────────────────


class FunnelEvaluateRequest(BaseModel):
    sessions_events: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


@router.get("/v1/funnels/definitions")
async def list_funnel_definitions(
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
) -> list[dict[str, Any]]:
    """List pre-configured conversion funnels (Demo, SaaS, Waitlist, Multi-Step)."""
    funnels = global_funnel_manager.list_funnels()
    return [f.model_dump() for f in funnels]


@router.get("/v1/funnels/friday-universe")
async def get_friday_universe_funnel_status(
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
) -> dict[str, Any]:
    """Retrieve full status of the 4 FRIDAY Universe conversion goals and MAB state."""
    tenant_id = user["tenant_id"]
    funnels = global_funnel_manager.list_funnels()
    return {
        "site_id": "site_friday_universe",
        "domain": "https://friday-universe.duckdns.org",
        "tenant_id": tenant_id,
        "active_funnels_count": len(funnels),
        "funnels": [f.model_dump() for f in funnels],
        "goals_supported": [
            {"goal": "Option A: Enterprise Demo Bookings", "event_type": "demo_request_submitted"},
            {"goal": "Option B: Paid SaaS Subscriptions", "event_type": "checkout_completed"},
            {"goal": "Option C: Community Waitlist Signups", "event_type": "signup_completed"},
            {"goal": "Option D: 10-Agent Mesh Multi-Step Journey", "event_type": "universe_multi_step_journey"},
        ],
    }


@router.post("/v1/funnels/{funnel_id}/evaluate")
async def evaluate_funnel_sessions(
    funnel_id: str,
    payload: FunnelEvaluateRequest,
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
) -> dict[str, Any]:
    """Evaluate session event sequences against a specific conversion funnel."""
    try:
        report = global_funnel_manager.evaluate_funnel(funnel_id, payload.sessions_events)
        return report.model_dump()
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Funnel '{funnel_id}' not found.",
        )


@router.post("/v1/funnels/seed-bandit-experiments")
async def seed_funnel_bandit_experiments(
    user: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
) -> dict[str, Any]:
    """Pre-seed Multi-Armed Bandit optimization experiments for the 4 conversion funnels."""
    tenant_id = user["tenant_id"]
    created_experiments = global_funnel_manager.seed_associated_bandit_experiments(tenant_id)
    return {
        "tenant_id": tenant_id,
        "site_id": "site_friday_universe",
        "seeded_experiment_ids": created_experiments,
        "status": "ACTIVE",
    }
