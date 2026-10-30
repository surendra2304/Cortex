import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlparse

import redis.asyncio as aioredis
from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from cortex_api.api_keys import provision_api_key
from cortex_api.auth import Role, require_role, verify_friday_token
from cortex_api.config import get_db_session, get_redis_client, settings
from cortex_api.db_models import (
    ApiKeyModel,
    AuditRecordModel,
    EventModel,
    ProfileModel,
    SentinelFindingModel,
    SentinelScanModel,
    TenantModel,
    VisitorModel,
    WorkflowRunModel,
)
from cortex_api.ws_auth import authenticate_websocket
from cortex_upgrade.audit import redact

logger = logging.getLogger("cortex-production-hardening")
router = APIRouter(tags=["Production & Observability"])

# Prometheus Metrics Storage in memory
METRICS = {
    "events_ingested_total": 0,
    "cognitive_loop_duration_seconds_sum": 0.0,
    "cognitive_loop_duration_seconds_count": 0,
    "ai_universe_calls_total": 0,
    "ai_universe_fallback_total": 0,
    "workflow_runs_total": 0,
    "approval_queue_depth": 0,
    "strategy_performance_gauge": 0.85,
    "security_findings_received_total": 0,
    "security_incidents_created_total": 0,
    "deployment_gates_evaluated_total": 0,
    "intelx_research_submitted_total": 0,
    "competitive_intelligence_findings_total": 0,
    "futuris_forecasts_requested_total": 0,
    "predictive_personalization_adjustments_total": 0,
    "capacity_preparation_triggered_total": 0,
}


def increment_metric(name: str, value: float = 1.0) -> None:
    if name in METRICS:
        METRICS[name] += value


def observe_duration(name_prefix: str, duration_sec: float) -> None:
    METRICS[f"{name_prefix}_sum"] += duration_sec
    METRICS[f"{name_prefix}_count"] += 1


# ── 1. PROMETHEUS METRICS ENDPOINT ───────────────────────────────────────────


@router.get("/metrics")
async def prometheus_metrics(
    authorization: str | None = Header(None),
    x_metrics_token: str | None = Header(None, alias="X-Metrics-Token"),
):
    """Exposes Prometheus metrics.

    Scraping is protected when ``METRICS_TOKEN`` is configured: callers must
    send ``Authorization: Bearer <token>`` or ``X-Metrics-Token``.  Without a
    configured token the endpoint stays open (documented, and the deployment
    guide recommends setting one behind a public ingress).
    """
    expected = settings.metrics_token
    if expected:
        supplied = x_metrics_token or (
            authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else None
        )
        if not supplied or not hmac.compare_digest(supplied, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Metrics endpoint requires a valid METRICS_TOKEN.",
            )
    avg_loop_duration = (
        METRICS["cognitive_loop_duration_seconds_sum"] / METRICS["cognitive_loop_duration_seconds_count"]
        if METRICS["cognitive_loop_duration_seconds_count"] > 0
        else 0.0
    )

    lines = [
        "# HELP events_ingested_total Total count of events ingested across all endpoints",
        "# TYPE events_ingested_total counter",
        f"events_ingested_total {METRICS['events_ingested_total']}",
        "",
        "# HELP cognitive_loop_duration_seconds Duration of cognitive loop executions",
        "# TYPE cognitive_loop_duration_seconds summary",
        f"cognitive_loop_duration_seconds_sum {METRICS['cognitive_loop_duration_seconds_sum']:.4f}",
        f"cognitive_loop_duration_seconds_count {METRICS['cognitive_loop_duration_seconds_count']}",
        f"cognitive_loop_duration_seconds_avg {avg_loop_duration:.4f}",
        "",
        "# HELP ai_universe_calls_total Total calls made to AI Universe deliberation layer",
        "# TYPE ai_universe_calls_total counter",
        f"ai_universe_calls_total {METRICS['ai_universe_calls_total']}",
        "",
        "# HELP ai_universe_fallback_total Total times deterministic fallback was engaged",
        "# TYPE ai_universe_fallback_total counter",
        f"ai_universe_fallback_total {METRICS['ai_universe_fallback_total']}",
        "",
        "# HELP workflow_runs_total Total automated workflow state machine runs",
        "# TYPE workflow_runs_total counter",
        f"workflow_runs_total {METRICS['workflow_runs_total']}",
        "",
        "# HELP security_findings_received_total Total security findings ingested from Sentinel",
        "# TYPE security_findings_received_total counter",
        f"security_findings_received_total {METRICS['security_findings_received_total']}",
        "",
        "# HELP security_incidents_created_total Total security incidents triaged and created",
        "# TYPE security_incidents_created_total counter",
        f"security_incidents_created_total {METRICS['security_incidents_created_total']}",
        "",
        "# HELP deployment_gates_evaluated_total Total deployment gates evaluated",
        "# TYPE deployment_gates_evaluated_total counter",
        f"deployment_gates_evaluated_total {METRICS['deployment_gates_evaluated_total']}",
        "",
        "# HELP intelx_research_submitted_total Total research queries submitted to IntelX",
        "# TYPE intelx_research_submitted_total counter",
        f"intelx_research_submitted_total {METRICS['intelx_research_submitted_total']}",
        "",
        "# HELP competitive_intelligence_findings_total Total competitor insights synthesized",
        "# TYPE competitive_intelligence_findings_total counter",
        f"competitive_intelligence_findings_total {METRICS['competitive_intelligence_findings_total']}",
        "",
        "# HELP futuris_forecasts_requested_total Total forecasting requests to Futuris",
        "# TYPE futuris_forecasts_requested_total counter",
        f"futuris_forecasts_requested_total {METRICS['futuris_forecasts_requested_total']}",
        "",
        "# HELP predictive_personalization_adjustments_total Total proactive predictive adjustments",
        "# TYPE predictive_personalization_adjustments_total counter",
        f"predictive_personalization_adjustments_total {METRICS['predictive_personalization_adjustments_total']}",
        "",
        "# HELP capacity_preparation_triggered_total Total auto-scaling & cache preparations",
        "# TYPE capacity_preparation_triggered_total counter",
        f"capacity_preparation_triggered_total {METRICS['capacity_preparation_triggered_total']}",
        "",
        "# HELP approval_queue_depth Pending human-in-the-loop approvals gauge",
        "# TYPE approval_queue_depth gauge",
        f"approval_queue_depth {METRICS['approval_queue_depth']}",
        "",
        "# HELP strategy_performance_gauge Aggregated strategy win rate",
        "# TYPE strategy_performance_gauge gauge",
        f"strategy_performance_gauge {METRICS['strategy_performance_gauge']:.2f}",
    ]

    return Response(content="\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


# ── 2. HEALTH & READINESS PROBES ─────────────────────────────────────────────


_START_TIME = time.time()


@router.api_route("/health", methods=["GET", "HEAD"])
async def liveness_probe():
    """Liveness probe: verifies the process is alive and answering requests.

    Used by the Docker HEALTHCHECK directive and the Caddy reverse proxy
    at https://friday-universe.duckdns.org/cortex/health.
    """
    observed_at = datetime.now(UTC).isoformat()
    return {
        "status": "healthy",
        "service": "cortex",
        "version": "2.1.0",
        "evidence_class": "process_liveness",
        "observed_at": observed_at,
        "timestamp": observed_at,
    }


@router.api_route("/status", methods=["GET", "HEAD"])
async def status_probe():
    """Diagnostic status reporting uptime, service health, and request performance."""
    uptime = time.time() - _START_TIME
    return {
        "status": "operational",
        "service": "cortex",
        "version": "2.1.0",
        "uptime_seconds": round(uptime, 2),
        "environment": settings.app_env,
        "observed_at": datetime.now(UTC).isoformat(),
    }


@router.api_route("/ready", methods=["GET", "HEAD"])
@router.api_route("/health/ready", methods=["GET", "HEAD"])
async def readiness_probe(
    db: AsyncSession = Depends(get_db_session), redis_client: aioredis.Redis = Depends(get_redis_client)
):
    """Readiness probe: validates the Oracle database, Redis, and optional peer integrations."""
    checks = {
        "database": "UNKNOWN",
        "schema": "UNKNOWN",
        "redis": "UNKNOWN",
        # These integrations do not have live readiness probes wired here.
        # Keep their state explicit instead of claiming availability.
        "ai_universe": "UNKNOWN: no live readiness probe configured",
        "sentinel": "UNKNOWN: no live readiness probe configured",
        "intelx": "UNKNOWN: no live readiness probe configured",
        "futuris": "UNKNOWN: no live readiness probe configured",
    }

    # 1. Database check (Oracle Autonomous Database in production)
    try:
        await db.execute(text("SELECT 1 FROM DUAL"))
        checks["database"] = "UP"
    except Exception as exc:
        checks["database"] = f"DOWN: {str(exc)[:50]}"

    # 1b. Schema check — a reachable database with no tables is NOT ready.
    try:
        from cortex_api.config import engine as _engine
        from cortex_api.schema import missing_tables as _missing

        absent = await _missing(_engine)
        checks["schema"] = "UP" if not absent else f"DOWN: missing tables {', '.join(absent)}"
    except Exception as exc:
        checks["schema"] = f"UNKNOWN: {str(exc)[:80]}"

    # 2. Redis check
    try:
        ping = await redis_client.ping()
        checks["redis"] = "UP" if ping else "DOWN"
    except Exception as exc:
        redis_host = urlparse(settings.redis_url).hostname
        if redis_host in {"localhost", "127.0.0.1", "::1"}:
            checks["redis"] = (
                "DOWN: REDIS_URL points to localhost; set REDIS_URL to the "
                "reachable Redis service in the deployment environment."
            )
        else:
            checks["redis"] = f"DOWN: {str(exc)[:120]}"

    # Readiness is decided by the dependencies this service needs to serve traffic. The
    # optional external integrations (AI Universe, Sentinel, IntelX, Futuris) have no live
    # probe configured by default, and treating "UNKNOWN" as fatal made a healthy
    # deployment permanently NOT_READY — a readiness gate that can never pass is worse than
    # none, because platforms stop routing traffic to a service that is actually fine.
    required = ("database", "schema", "redis")
    required_ok = all(checks[name] == "UP" for name in required)
    degraded = [name for name, value in checks.items() if name not in required and value.startswith("UNKNOWN")]

    return Response(
        content=json.dumps(
            {
                "status": "READY" if required_ok else "NOT_READY",
                "service": "cortex",
                "evidence_class": "dependency_readiness",
                "observed_at": datetime.now(UTC).isoformat(),
                "required_dependencies": list(required),
                "degraded": degraded,
                "dependencies": checks,
            }
        ),
        status_code=status.HTTP_200_OK if required_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        media_type="application/json",
    )


# ── 3. WEBSOCKET LIVE EVENT STREAM ───────────────────────────────────────────


class ConnectionManager:
    def __init__(self, max_connections_per_tenant: int = 100):
        self.active_connections: dict[str, list[WebSocket]] = {}
        self.max_connections = max_connections_per_tenant

    async def connect(self, websocket: WebSocket, tenant_id: str = "tenant_default") -> bool:
        conns = self.active_connections.setdefault(tenant_id, [])
        if len(conns) >= self.max_connections:
            await websocket.close(code=1008)
            return False
        await websocket.accept()
        conns.append(websocket)
        return True

    def disconnect(self, websocket: WebSocket, tenant_id: str = "tenant_default"):
        if tenant_id in self.active_connections and websocket in self.active_connections[tenant_id]:
            self.active_connections[tenant_id].remove(websocket)

    async def broadcast(self, message: str, tenant_id: str | None = None):
        targets = []
        if tenant_id and tenant_id in self.active_connections:
            targets = list(self.active_connections[tenant_id])
        elif not tenant_id:
            for group in self.active_connections.values():
                targets.extend(group)
        for connection in targets:
            try:
                await connection.send_text(message)
            except Exception:
                pass


ws_manager = ConnectionManager()


@router.websocket("/v1/ws/events")
async def websocket_live_events(websocket: WebSocket, token: str | None = Query(None)):
    """Real-time authenticated WebSocket event stream for dashboard live telemetry."""
    tenant_id = await authenticate_websocket(websocket, token)
    if tenant_id is None:
        return

    connected = await ws_manager.connect(websocket, tenant_id=tenant_id)
    if not connected:
        return
    try:
        while True:
            # Keep-alive heartbeat
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, tenant_id=tenant_id)
    except Exception:
        ws_manager.disconnect(websocket, tenant_id=tenant_id)


# ── 4. CONNECTOR REGISTRY & HEALTH ───────────────────────────────────────────

from cortex_integrations import get_connector_registry  # noqa: E402 - deliberate late import (avoids an import cycle)


@router.get("/connectors")
async def list_registered_connectors(auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER))):
    """Live health, scopes and probe details for all ecosystem connectors.

    Serves the real ConnectorManager checks — the old static table reported every
    connector HEALTHY and hid outages (audit S10).
    """
    return await get_connector_registry()


# ── 5. EXPERIMENTATION & PERSONALIZATION ─────────────────────────────────────

from cortex_analytics import (  # noqa: E402 - deliberate late import (avoids an import cycle)
    ExperimentationEngine,
    ExperimentDefinition,
    ExperimentStatus,
    ExperimentVariant,
)

exp_engine = ExperimentationEngine()

DEMO_EXPERIMENTS: list[ExperimentDefinition] = [
    ExperimentDefinition(
        id="exp_hero_cta_v1",
        name="Homepage Hero CTA Optimization",
        hypothesis="High-contrast aggressive CTA variant increases demo request conversion rate by >15%.",
        target_page="/",
        primary_metric="conversion_rate",
        variants=[
            ExperimentVariant(
                id="var_control",
                name="Control (Standard Blue)",
                weight=0.5,
                visitors_count=1200,
                conversions_count=84,
                payload={"cta_color": "#2563eb", "text": "Get Started"},
            ),
            ExperimentVariant(
                id="var_variant_b",
                name="Variant B (Emerald Glow)",
                weight=0.5,
                visitors_count=1240,
                conversions_count=128,
                payload={"cta_color": "#059669", "text": "Deploy Autonomous Agent Now"},
            ),
        ],
        status=ExperimentStatus.ACTIVE,
    )
]


@router.get("/experiments")
async def list_experiments(auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER))):
    """List all active and concluded A/B experiments with statistical significance results."""
    results = []
    for exp in DEMO_EXPERIMENTS:
        stats = {}
        if len(exp.variants) >= 2:
            stats = exp_engine.calculate_significance(exp.variants[0], exp.variants[1])
        results.append(
            {
                "id": exp.id,
                "name": exp.name,
                "hypothesis": exp.hypothesis,
                "target_page": exp.target_page,
                "status": exp.status.value,
                "variants": [v.model_dump() for v in exp.variants],
                "statistics": stats,
            }
        )
    return results


@router.post("/personalization/match")
async def match_personalization_experience(
    payload: dict[str, Any], auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER))
):
    """Matches visitor traits to dynamic experience variants."""
    traits = payload.get("traits", {})
    page_path = payload.get("path", "/")
    rules = [
        {
            "segment": "enterprise",
            "path": "/",
            "experience_payload": {
                "hero_title": "Autonomous Website Intelligence for Enterprise Teams",
                "badge": "SOC2 Certified",
            },
        },
        {"device": "mobile", "path": "/", "experience_payload": {"nav_mode": "compact_sheet", "cta_size": "large"}},
    ]
    matched = exp_engine.evaluate_personalization_rules(traits, page_path, rules)
    return {"matched": matched is not None, "experience": matched}


# ── 6. NATURAL LANGUAGE ANALYTICS QUERYING ───────────────────────────────────

from cortex_analytics import (  # noqa: E402 - deliberate late import (avoids an import cycle)
    AdvancedAnalyticsEngine,
    NLQueryRequest,
    NLQueryResponse,
)

nl_analytics_engine = AdvancedAnalyticsEngine()


@router.post("/analytics/query", response_model=NLQueryResponse)
async def query_analytics_natural_language(
    req: NLQueryRequest, auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER))
):
    """Parses natural language operations questions and returns structured query results."""
    return nl_analytics_engine.parse_natural_language_query(req.question)


# ── 7. COMPLIANCE, PRIVACY & GOVERNANCE ─────────────────────────────────────

from cortex_policy_engine import (  # noqa: E402 - deliberate late import (avoids an import cycle)
    DataSubjectExport,
    PrivacyComplianceService,
)

privacy_service = PrivacyComplianceService()


@router.post("/privacy/export/{visitor_id}", response_model=DataSubjectExport)
@router.post("/v1/privacy/export/{visitor_id}", response_model=DataSubjectExport)
async def export_visitor_data(
    visitor_id: str,
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """GDPR Art. 15 / CCPA Right of Access: Generates full structured JSON export scoped to tenant."""
    tenant_id = auth.get("tenant_id", "tenant_default")
    try:
        # Resolve visitor -> profile: profiles carry their own ids (prof_*), so
        # looking the profile up by the visitor id always missed and the export
        # 404'd for every real data subject.
        v_stmt = select(VisitorModel).where(VisitorModel.tenant_id == tenant_id, VisitorModel.id == visitor_id)
        vres = await db.execute(v_stmt)
        visitor = vres.scalar_one_or_none()

        profile_data: dict[str, Any] = {}
        if visitor and visitor.profile_id:
            p_stmt = select(ProfileModel).where(
                ProfileModel.tenant_id == tenant_id, ProfileModel.id == visitor.profile_id
            )
            pres = await db.execute(p_stmt)
            prof = pres.scalar_one_or_none()
            if prof:
                profile_data = {"visitor_id": visitor.id, "email": prof.primary_email, "traits": prof.traits}

        e_stmt = (
            select(EventModel).where(EventModel.tenant_id == tenant_id, EventModel.actor_id == visitor_id).limit(100)
        )
        eres = await db.execute(e_stmt)
        evts = eres.scalars().all()
        event_list = [
            {
                "type": e.type,
                "site_id": e.site_id,
                "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
                "data": redact(e.data or {}),
            }
            for e in evts
        ]
    except Exception as exc:
        # A compliance export must never be answered with invented data.
        logger.error("Failed to query DB for visitor export (%s): %s", visitor_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to assemble the data export right now; please retry.",
        ) from exc

    if not profile_data and not event_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No records held for subject '{visitor_id}' in this tenant.",
        )

    return privacy_service.generate_data_export(visitor_id, profile_data, event_list)


@router.post("/privacy/delete/{visitor_id}")
@router.post("/v1/privacy/delete/{visitor_id}")
async def erase_visitor_data(
    visitor_id: str,
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """GDPR Art. 17 / CCPA Right to be Forgotten: Cascading hard erasure across all stores."""
    tenant_id = auth.get("tenant_id", "tenant_default")
    # Strict tenant boundary: cross-tenant delete attempt returns 403, non-existent returns 404
    from cortex_api.db_models import VisitorModel

    vis_check = (await db.execute(select(VisitorModel).where(VisitorModel.id == visitor_id))).scalar_one_or_none()
    if vis_check and vis_check.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant visitor deletion forbidden.")
    if not vis_check:
        raise HTTPException(status_code=404, detail="Visitor not found.")
    try:
        result = await privacy_service.execute_hard_erasure(db=db, visitor_id=visitor_id, tenant_id=tenant_id)
    except Exception as exc:
        await db.rollback()
        logger.error("Hard erasure failed for %s: %s", visitor_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erasure could not be completed; nothing was reported as erased.",
        ) from exc
    return result


@router.get("/audit/export")
async def export_audit_log(
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_ADMIN)), db: AsyncSession = Depends(get_db_session)
):
    """Returns hash-chained compliance audit records for compliance officers."""
    tenant_id = auth.get("tenant_id", "tenant_default")
    records = []
    try:
        stmt = (
            select(AuditRecordModel)
            .where(AuditRecordModel.tenant_id == tenant_id)
            .order_by(desc(AuditRecordModel.timestamp))
            .limit(100)
        )
        res = await db.execute(stmt)
        for r in res.scalars().all():
            records.append(
                {
                    "action": r.action,
                    "actor": r.actor_id,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else datetime.now(UTC).isoformat(),
                    "changes": redact(r.changes or {}),
                }
            )
    except Exception as exc:
        # A compliance export must fail loudly, never fall back to invented records.
        logger.error("Failed to query audit records: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Audit records could not be read; refusing to export an incomplete record set.",
        ) from exc

    return {
        "status": "success",
        "tenant_id": tenant_id,
        "retention_policy_years": 7,
        "total_audit_records": len(records),
        "tamper_evidence_hash": hashlib.sha256(json.dumps(records, sort_keys=True, default=str).encode()).hexdigest(),
        "records": records,
    }


# ── 8. MULTI-TENANT SAAS & WHITE-LABEL DEPLOYMENT ───────────────────────────


class TenantOnboardingRequest(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=255)
    admin_email: str = Field(min_length=3, max_length=254)
    plan: Literal["free", "pro", "enterprise"] = "pro"


class TenantSettings(BaseModel):
    tenant_id: str
    name: str
    plan: str
    max_sites: int
    monthly_event_limit: int
    branding: dict[str, Any] = Field(
        default_factory=lambda: {
            "logo_url": "/cortex-logo.png",
            "primary_color": "#0284c7",
            "custom_domain": "app.tenant.io",
        }
    )
    retention_days: int = 90


@router.post("/v1/tenants", status_code=status.HTTP_201_CREATED)
async def onboard_tenant(
    req: TenantOnboardingRequest,
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_PLATFORM_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Persist a tenant and provision a working, hashed public SDK key.

    Operator sessions are issued by the configured JWT/OIDC issuer. This endpoint
    deliberately does not return a per-tenant JWT secret because the authentication
    layer does not support tenant-specific signing secrets.
    """
    tenant_id = f"ten_{uuid.uuid4().hex}"
    site_id = f"site_{uuid.uuid4().hex}"
    created_at = datetime.now(UTC)
    tenant = TenantModel(
        id=tenant_id,
        name=req.tenant_name.strip(),
        admin_email=req.admin_email.strip().lower(),
        plan=req.plan,
        primary_site_id=site_id,
        created_by=str(auth.get("sub") or "platform-admin"),
        is_active=True,
        created_at=created_at,
    )
    db.add(tenant)

    try:
        # provision_api_key commits through this same session, atomically persisting
        # the tenant row and its key digest; plaintext is returned once only.
        public_sdk_key, _key_record = await provision_api_key(
            db=db,
            tenant_id=tenant_id,
            site_id=site_id,
            name="tenant-onboarding",
        )
    except Exception as exc:
        await db.rollback()
        logger.exception("Tenant onboarding persistence failed for %s", tenant_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tenant onboarding could not be persisted; no credentials were issued.",
        ) from exc

    return {
        "status": "created",
        "tenant_id": tenant_id,
        "tenant_name": tenant.name,
        "plan": tenant.plan,
        "admin_email": tenant.admin_email,
        "primary_site_id": site_id,
        "public_sdk_key": public_sdk_key,
        "created_at": created_at.isoformat(),
    }


DEFAULT_TENANT_PLAN = {
    "plan": "enterprise",
    "max_sites": 10,
    "monthly_event_limit": 5_000_000,
    "retention_days": 365,
}


def _tenant_plan(tenant_id: str, tenant: TenantModel | None = None) -> dict[str, Any]:
    """Return the configured plan label while preserving existing enforced quota limits.

    Tier-specific quota policy is not defined in this repository yet. Existing enforced
    limits therefore remain unchanged; a registered tenant's stored plan label is returned
    accurately instead of reporting every tenant as enterprise.
    """
    del tenant_id
    plan = dict(DEFAULT_TENANT_PLAN)
    if tenant is not None:
        plan["plan"] = tenant.plan
    return plan


@router.get("/v1/tenant/settings", response_model=TenantSettings)
async def get_tenant_settings(
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Returns persisted tenant identity and the currently enforced plan limits."""
    tenant_id = auth.get("tenant_id", "tenant_default")
    tenant_res = await db.execute(select(TenantModel).where(TenantModel.id == tenant_id))
    tenant = tenant_res.scalar_one_or_none()
    plan = _tenant_plan(tenant_id, tenant)
    return TenantSettings(
        tenant_id=tenant_id,
        name=tenant.name if tenant else f"Tenant ({tenant_id})",
        plan=plan["plan"],
        max_sites=plan["max_sites"],
        monthly_event_limit=plan["monthly_event_limit"],
        branding={"logo_url": "/cortex-logo.png", "primary_color": "#0284c7", "custom_domain": f"ops.{tenant_id}.com"},
        retention_days=plan["retention_days"],
    )


@router.get("/v1/tenant/usage")
async def get_tenant_usage(
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
    db: AsyncSession = Depends(get_db_session),
):
    """Current-period usage metered from persisted state.

    Every value here used to be a hardcoded constant (184500 events, 850 workflow runs, ...),
    unrelated to what the tenant had actually stored — a metering endpoint that reports
    invented numbers is worse than no metering at all.
    """
    tenant_id = auth.get("tenant_id", "tenant_default")
    now = datetime.now(UTC)
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    events_ingested = (
        await db.execute(
            select(func.count())
            .select_from(EventModel)
            .where(EventModel.tenant_id == tenant_id, EventModel.occurred_at >= period_start)
        )
    ).scalar_one()
    active_sites = (
        await db.execute(
            select(func.count(func.distinct(EventModel.site_id))).where(
                EventModel.tenant_id == tenant_id, EventModel.occurred_at >= period_start
            )
        )
    ).scalar_one()
    workflow_runs = (
        await db.execute(
            select(func.count())
            .select_from(WorkflowRunModel)
            .where(WorkflowRunModel.tenant_id == tenant_id, WorkflowRunModel.started_at >= period_start)
        )
    ).scalar_one()

    tenant_res = await db.execute(select(TenantModel).where(TenantModel.id == tenant_id))
    tenant = tenant_res.scalar_one_or_none()
    plan = _tenant_plan(tenant_id, tenant)
    monthly_limit = int(plan["monthly_event_limit"])
    usage_pct = round(events_ingested / monthly_limit * 100, 4) if monthly_limit else 0.0
    return {
        "tenant_id": tenant_id,
        "period": now.strftime("%Y-%m"),
        "plan": plan["plan"],
        "events_ingested": events_ingested,
        "monthly_limit": monthly_limit,
        "usage_pct": usage_pct,
        "active_sites": active_sites,
        "max_sites": int(plan["max_sites"]),
        # Counters are process-local; report the real values (0 until the metric is incremented).
        "ai_universe_calls": METRICS["ai_universe_calls_total"],
        "workflow_runs": workflow_runs,
    }


# ── 6. SENTINEL INTEGRATION & SECURITY INCIDENT COORDINATION ──────────────────

from cortex_integrations.sentinel_client import (  # noqa: E402 - deliberate late import (avoids an import cycle)
    SentinelClient,
)
from cortex_integrations.sentinel_listener import (  # noqa: E402 - deliberate late import (avoids an import cycle)
    SentinelEventListener,
    SentinelPayload,
)
from cortex_intelligence.exposure_monitor import (
    AssetExposureMonitor,
)
from cortex_workflow_engine.security_incident import (
    SecurityIncidentWorkflow,
)

_exposure_monitor = AssetExposureMonitor()
_sentinel_listener = SentinelEventListener(exposure_monitor=_exposure_monitor)
_sentinel_client = SentinelClient()
_sec_workflow = SecurityIncidentWorkflow()


async def _resolve_sentinel_tenant(db: AsyncSession, site_id: str) -> str:
    """Resolve a scanner asset to exactly one active tenant before accepting findings."""
    key_result = await db.execute(
        select(ApiKeyModel.tenant_id)
        .where(ApiKeyModel.site_id == site_id, ApiKeyModel.is_active.is_(True))
        .distinct()
    )
    owners = {str(value) for value in key_result.scalars().all() if value}

    primary_result = await db.execute(select(TenantModel).where(TenantModel.primary_site_id == site_id))
    primary_tenant = primary_result.scalar_one_or_none()
    if primary_tenant is not None:
        if not primary_tenant.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sentinel asset belongs to an inactive tenant.",
            )
        owners.add(primary_tenant.id)

    if not owners:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sentinel asset is not registered to an active tenant.")

    registry_result = await db.execute(select(TenantModel).where(TenantModel.id.in_(owners)))
    registered = {row.id: row for row in registry_result.scalars().all()}
    disabled = {owner for owner in owners if owner in registered and not registered[owner].is_active}
    active_owners = owners - disabled
    if not active_owners:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sentinel asset has no active tenant owner.")
    if len(active_owners) != 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sentinel asset has ambiguous tenant ownership.")
    return next(iter(active_owners))


async def _persist_sentinel_scan(db: AsyncSession, payload: SentinelPayload, tenant_id: str) -> SentinelScanModel:
    """Persist each scan and its finding set atomically; retrying a task replaces that set."""
    now = datetime.now(UTC)
    try:
        result = await db.execute(
            select(SentinelScanModel).where(
                SentinelScanModel.tenant_id == tenant_id,
                SentinelScanModel.site_id == payload.asset_id,
                SentinelScanModel.sentinel_task_id == payload.sentinel_task_id,
            )
        )
        scan = result.scalar_one_or_none()
        if scan is None:
            scan = SentinelScanModel(
                id=f"scan_{uuid.uuid4().hex}",
                tenant_id=tenant_id,
                site_id=payload.asset_id,
                sentinel_task_id=payload.sentinel_task_id,
                posture_score=payload.posture_score,
                occurred_at=payload.timestamp,
                received_at=now,
            )
            db.add(scan)
            await db.flush()
        else:
            scan.posture_score = payload.posture_score
            scan.occurred_at = payload.timestamp
            scan.received_at = now
            await db.execute(delete(SentinelFindingModel).where(SentinelFindingModel.scan_id == scan.id))

        for finding in payload.findings:
            db.add(
                SentinelFindingModel(
                    id=f"sf_{uuid.uuid4().hex}",
                    scan_id=scan.id,
                    tenant_id=tenant_id,
                    site_id=payload.asset_id,
                    finding_id=finding.finding_id,
                    severity=finding.severity.lower(),
                    title=finding.title,
                    description=finding.description,
                    evidence_ref=finding.evidence_ref,
                    attack_vector=finding.attack_vector,
                    affected_endpoint=finding.affected_endpoint,
                    occurred_at=payload.timestamp,
                    received_at=now,
                )
            )
        await db.commit()
        return scan
    except IntegrityError as exc:
        await db.rollback()
        logger.warning("Concurrent duplicate Sentinel scan task %s for site %s", payload.sentinel_task_id, payload.asset_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A conflicting Sentinel scan task was received concurrently; retry with the same task ID.",
        ) from exc
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        logger.exception("Failed to persist Sentinel scan task %s for site %s", payload.sentinel_task_id, payload.asset_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sentinel finding store is unavailable; findings were not accepted.",
        ) from exc


@router.post("/v1/sentinel/findings", status_code=status.HTTP_202_ACCEPTED)
async def receive_sentinel_findings(
    payload: SentinelPayload,
    auth: dict[str, Any] = Depends(verify_friday_token),
    db: AsyncSession = Depends(get_db_session),
):
    """Accept scanner findings only for a registered tenant site, then persist them."""
    tenant_id = await _resolve_sentinel_tenant(db, payload.asset_id)
    await _persist_sentinel_scan(db, payload, tenant_id)
    ingest_result = await _sentinel_listener.handle_findings(payload, tenant_id=tenant_id)

    triaged_incidents = []
    for finding in payload.findings:
        if finding.severity.lower() in ("critical", "high"):
            exposure = _exposure_monitor.evaluate_exposure(
                payload.asset_id, finding.affected_endpoint or f"/api/{payload.asset_id}"
            )
            incident = await _sec_workflow.execute_security_incident_triage(
                finding={**finding.model_dump(), "asset_id": payload.asset_id, "tenant_id": tenant_id},
                asset_exposure=exposure,
            )
            triaged_incidents.append(incident)

    return {**ingest_result, "tenant_id": tenant_id, "security_incidents_triaged": triaged_incidents}


@router.get("/v1/sentinel/exposure")
async def get_asset_exposure(auth: dict[str, Any] = Depends(require_role(Role.CORTEX_PLATFORM_ADMIN))):
    """Returns live asset exposure and attack surface mappings."""
    return {
        "assets": _exposure_monitor.list_monitored_assets(),
        "total_monitored": len(_exposure_monitor.asset_registry),
    }


@router.get("/v1/sentinel/findings")
async def get_sentinel_findings(
    asset_id: str | None = Query(None, min_length=1, max_length=64),
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
    db: AsyncSession = Depends(get_db_session),
):
    """Return persisted findings scoped to the authenticated tenant (or platform admin)."""
    is_platform_admin = auth.get("role") == Role.CORTEX_PLATFORM_ADMIN.value
    finding_filters = []
    scan_filters = []
    if not is_platform_admin:
        tenant_id = str(auth.get("tenant_id") or "").strip()
        if not tenant_id or tenant_id == "system":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="A tenant-bound identity is required to read Sentinel findings.",
            )
        finding_filters.append(SentinelFindingModel.tenant_id == tenant_id)
        scan_filters.append(SentinelScanModel.tenant_id == tenant_id)

    if asset_id:
        finding_filters.append(SentinelFindingModel.site_id == asset_id)
        scan_filters.append(SentinelScanModel.site_id == asset_id)

    count_result = await db.execute(select(func.count()).select_from(SentinelFindingModel).where(*finding_filters))
    total = int(count_result.scalar_one())
    finding_result = await db.execute(
        select(SentinelFindingModel, SentinelScanModel.sentinel_task_id, SentinelScanModel.posture_score)
        .join(SentinelScanModel, SentinelScanModel.id == SentinelFindingModel.scan_id)
        .where(*finding_filters)
        .order_by(desc(SentinelFindingModel.received_at))
        .limit(500)
    )
    records = finding_result.all()
    score_result = await db.execute(
        select(SentinelScanModel.posture_score)
        .where(*scan_filters)
        .order_by(desc(SentinelScanModel.received_at))
        .limit(1)
    )
    pushed_score = score_result.scalar_one_or_none()

    findings = [
        {
            "finding_id": row.finding_id,
            "sentinel_task_id": task_id,
            "tenant_id": row.tenant_id,
            "asset_id": row.site_id,
            "site_id": row.site_id,
            "posture_score": score,
            "severity": row.severity,
            "title": row.title,
            "description": row.description,
            "evidence_ref": row.evidence_ref,
            "attack_vector": row.attack_vector,
            "affected_endpoint": row.affected_endpoint,
            "timestamp": row.occurred_at.isoformat(),
            "received_at": row.received_at.isoformat(),
        }
        for row, task_id, score in records
    ]
    return {
        "findings": findings,
        "total": total,
        "posture_score": pushed_score,
        "posture_source": "sentinel_push" if pushed_score is not None else "none",
    }


@router.get("/v1/sentinel/posture")
async def get_live_security_posture(auth: dict[str, Any] = Depends(require_role(Role.CORTEX_PLATFORM_ADMIN))):
    """Live security posture read from the Sentinel service (or the documented baseline)."""
    posture = await _sentinel_client.fetch_security_posture()
    payload = posture.model_dump()
    payload["assets"] = [asset.model_dump() for asset in await _sentinel_client.fetch_asset_inventory()]
    return payload


# ── 7. DEVSECOPS DEPLOYMENT SECURITY GATES & COMPLIANCE ───────────────────────

from cortex_analytics.security_baseline import (
    SecurityBaselineTracker,  # noqa: E402 - deliberate late import (avoids an import cycle)
)
from cortex_integrations.deployment_gate import (
    DeploymentSecurityGate,  # noqa: E402 - deliberate late import (avoids an import cycle)
)

_deployment_gate = DeploymentSecurityGate(sentinel_listener=_sentinel_listener)
_baseline_tracker = SecurityBaselineTracker()


class DeploymentEvaluateRequest(BaseModel):
    deployment_id: str
    asset_id: str
    endpoints: list[str]
    simulated_findings: list[dict[str, Any]] | None = None


@router.post("/v1/security/deployment-gate/evaluate")
async def evaluate_deployment_gate(
    req: DeploymentEvaluateRequest,
    auth: dict[str, Any] = Depends(verify_friday_token),
):
    """Evaluates candidate deployment against Sentinel security gates."""
    result = await _deployment_gate.evaluate_deployment(
        deployment_id=req.deployment_id,
        asset_id=req.asset_id,
        endpoints=req.endpoints,
        simulated_findings=req.simulated_findings,
    )
    return result.model_dump()


@router.get("/v1/security/compliance-report")
async def get_security_compliance_report(auth: dict[str, Any] = Depends(require_role(Role.CORTEX_PLATFORM_ADMIN))):
    """Generates weekly compliance report (SOC2 Type II, ISO 27001, SLA compliance)."""
    return _baseline_tracker.generate_compliance_report()


# ── 8. FUTURIS PREDICTIVE OPERATIONS & CAPACITY PLANNING ──────────────────────

from cortex_integrations.futuris_client import (
    FuturisClient,  # noqa: E402 - deliberate late import (avoids an import cycle)
)
from cortex_intelligence.predictive_personalization import (
    PredictionInformedPersonalization,  # noqa: E402 - deliberate late import (avoids an import cycle)
)
from cortex_workflow_engine.capacity_planning import (
    CapacityPlanningWorkflow,  # noqa: E402 - deliberate late import (avoids an import cycle)
)

_futuris_client = FuturisClient()
_capacity_workflow = CapacityPlanningWorkflow(futuris_client=_futuris_client)
_pred_personalization = PredictionInformedPersonalization(futuris_client=_futuris_client)


@router.get("/v1/predictive/traffic-forecast")
async def get_traffic_forecast(
    site_id: str = "site_main",
    horizon_hours: int = 24,
    auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER)),
    db: AsyncSession = Depends(get_db_session),
):
    """Returns 24h/7d traffic forecast with 95% confidence intervals.

    The forecast is driven by this deployment's own ingested traffic for the site. Without
    current traffic there is nothing honest to calibrate on, so the request goes out with no
    telemetry and Futuris (and Cortex's own gate) answer with the documented fallback.
    """
    from cortex_api.traffic_telemetry import average_rps, observed_traffic_telemetry

    tenant_id = auth.get("tenant_id", "tenant_default")
    telemetry = await observed_traffic_telemetry(db, tenant_id=tenant_id, site_id=site_id, window_hours=48)
    forecast = await _futuris_client.predict_traffic(
        site_id=site_id, horizon_hours=horizon_hours, telemetry=telemetry or None
    )
    payload = forecast.model_dump()
    payload["telemetry"] = {
        "source": "cortex_event_store" if telemetry else "none",
        "buckets": len(telemetry),
        "observed_average_rps": average_rps(telemetry) if telemetry else None,
        "window_hours": 48 if telemetry else 0,
    }
    return payload


@router.get("/v1/predictive/capacity-plan")
async def evaluate_capacity_plan(
    site_id: str = "site_main", auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER))
):
    """Evaluates upcoming traffic against provisioned infrastructure thresholds."""
    plan = await _capacity_workflow.evaluate_capacity(site_id=site_id)
    return plan.model_dump()


@router.get("/v1/predictive/conversion-trends")
async def get_conversion_trends(
    segment_id: str = "enterprise_leads", auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER))
):
    """Forecasts conversion rate trajectory and bottleneck steps."""
    trend = await _futuris_client.predict_conversion_trends(segment_id=segment_id)
    return trend.model_dump()


@router.get("/v1/predictive/churn-risk")
async def get_churn_risk_forecast(
    tenant_id: str = "default", auth: dict[str, Any] = Depends(require_role(Role.CORTEX_VIEWER))
):
    """Predicts high-risk customer segments and primary churn drivers."""
    segments = await _futuris_client.predict_churn_risk(tenant_id=tenant_id)
    return [s.model_dump() for s in segments]
