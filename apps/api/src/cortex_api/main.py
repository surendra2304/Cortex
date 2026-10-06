"""CORTEX API composition root.

Responsibilities
----------------
* Workspace path bootstrap (independent of the process CWD — audit defect H5).
* Schema bootstrap/verification on startup (audit defect C5).
* Router registration in an order that prevents route shadowing (audit defect C2).
* Static dashboard/SPA serving with path-traversal containment.
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ── Workspace paths (repo-root relative, never CWD relative) ─────────────────


def _locate_repo_root() -> Path | None:
    """Find the monorepo root by walking up from this file.

    Returns ``None`` when the package is installed as a wheel, in which case the
    dependencies it needs are already importable and no path surgery is required.
    """
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "packages").is_dir() and (candidate / "apps").is_dir():
            return candidate
    return None


_REPO_ROOT = _locate_repo_root()
if _REPO_ROOT is not None:
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    try:
        from cortex_upgrade.paths import ensure_workspace_paths  # noqa: E402

        ensure_workspace_paths(_REPO_ROOT)
    except ImportError:  # pragma: no cover - wheel layout without cortex_upgrade
        pass

from cortex_api.api_keys import provision_api_key  # noqa: E402
from cortex_api.auth import Role, require_role, verify_friday_token  # noqa: E402
from cortex_api.config import (  # noqa: E402 - deliberate late import (avoids an import cycle)
    AsyncSessionLocal,
    close_resources,
    engine,
    get_db_session,
    settings,
)  # noqa: E402
from cortex_api.db_models import ApiKeyModel  # noqa: E402
from cortex_api.events_router import router as events_router  # noqa: E402
from cortex_api.friday_router import FridayTaskEnvelope, process_task_envelope  # noqa: E402
from cortex_api.friday_router import router as friday_router  # noqa: E402
from cortex_api.landing_page import FALLBACK_WEBSITE_HTML  # noqa: E402
from cortex_api.production_router import router as production_router  # noqa: E402
from cortex_api.public_gateway import router as public_gateway_router  # noqa: E402
from cortex_api.schema import ensure_schema, missing_tables  # noqa: E402
from cortex_api.streaming_router import router as streaming_router  # noqa: E402
from cortex_api.stripe_webhook_router import router as stripe_webhook_router  # noqa: E402
from cortex_api.tracing import TracingMiddleware  # noqa: E402
from cortex_api.understand_router import router as understand_router  # noqa: E402
from cortex_api.webhooks_router import router as webhooks_router  # noqa: E402

logger = logging.getLogger("cortex-api")

BOOTSTRAP_KEY_TENANT = os.getenv("CORTEX_BOOTSTRAP_TENANT", "tenant_default")
BOOTSTRAP_KEY_SITE = os.getenv("CORTEX_BOOTSTRAP_SITE", "site_demo")


async def _bootstrap_development_key() -> None:
    """Create a first public key in non-production so the SDK works out of the box.

    Never runs in production (``app_env == "production"`` or ``RENDER`` set) and
    only when the key table is empty.  The plaintext key is logged exactly once.
    """
    if settings.app_env == "production" or not settings.bootstrap_dev_api_key:
        return
    try:
        async with AsyncSessionLocal() as session:
            from sqlalchemy import func, select

            existing = await session.execute(select(func.count()).select_from(ApiKeyModel))
            if (existing.scalar() or 0) > 0 or len(await missing_tables(engine)) > 0:
                return
            plaintext, record = await provision_api_key(
                db=session,
                tenant_id=BOOTSTRAP_KEY_TENANT,
                site_id=BOOTSTRAP_KEY_SITE,
                name="development-bootstrap",
            )
            logger.warning(
                "[DEV BOOTSTRAP] Provisioned a development public API key for tenant '%s' / site '%s': %s\n"
                "              (development only — never created when APP_ENV=production)",
                record.tenant_id,
                record.site_id,
                plaintext,
            )
    except Exception as exc:  # pragma: no cover - bootstrap must never block boot
        logger.warning("Development API key bootstrap skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s (env=%s, dsn=%s)", settings.app_name, settings.app_env, settings.postgres_dsn)
    try:
        result = await ensure_schema(engine)
        if result.get("missing"):
            logger.error("Schema is incomplete after startup check: %s", result["missing"])
    except Exception as exc:
        logger.error("Schema bootstrap failed: %s", exc)
    await _bootstrap_development_key()
    healing_loop = None
    try:
        from cortex_core.resilience import SelfHealingLoop

        from cortex_api.friday_router import _self_state
        from cortex_api.self_healing import build_settings_provider

        knobs, supervisor, _model = _self_state()
        healing_loop = SelfHealingLoop(supervisor, settings_provider=build_settings_provider(knobs))
        healing_loop.start()
        from cortex_api.friday_router import set_healing_loop

        set_healing_loop(healing_loop)
        logger.info(
            "Background self-healing started (enabled=%s, interval=%ss)",
            knobs.get("self_healing_enabled", True),
            knobs.get("self_healing_interval_seconds", 30),
        )
    except Exception as exc:  # pragma: no cover - healing must never block boot
        logger.warning("Background self-healing not started: %s", exc)
    try:
        yield
    finally:
        if healing_loop is not None:
            await healing_loop.stop()
            from cortex_api.friday_router import set_healing_loop

            set_healing_loop(None)
        await close_resources()


app = FastAPI(
    title=settings.app_name,
    description=(
        "CORTEX Autonomous Web Operations Intelligence Platform API. "
        "Ingestion requires a provisioned public API key; operator endpoints require OIDC/JWT RBAC."
    ),
    version="2.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(TracingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Router registration order matters ────────────────────────────────────────
# Specific paths must be registered before catch-all/parameterised paths so that
# e.g. POST /v1/webhooks/stripe reaches the signature-verifying handler instead
# of the generic /v1/webhooks/{provider} gateway.
app.include_router(stripe_webhook_router)
app.include_router(friday_router)
app.include_router(public_gateway_router)
app.include_router(events_router)
app.include_router(understand_router)
app.include_router(production_router)
app.include_router(webhooks_router)
app.include_router(streaming_router)


@app.post("/v1/task/execute", tags=["Universal Task Protocol"])
async def execute_task(body: dict, auth: dict = Depends(verify_friday_token)):
    """Universal Task Protocol endpoint for Cortex with governed operations."""
    import time

    task_id = body.get("task_id", f"cortex_{int(time.time())}")
    action = body.get("action", "command")
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else body
    idempotency_key = body.get("idempotency_key")
    dry_run = body.get("dry_run", False) or payload.get("dry_run", False)

    envelope = FridayTaskEnvelope(
        task_id=task_id,
        source_agent=body.get("source_agent", auth.get("sub", "friday")),
        target_agent="cortex",
        action=action,
        payload=payload,
        priority=body.get("priority", "NORMAL"),
        idempotency_key=idempotency_key,
        dry_run=dry_run,
    )
    resp = await process_task_envelope(envelope)
    return resp.model_dump()


@app.post("/v1/api-keys", status_code=201, tags=["Administration"])
async def create_api_key(
    body: dict,
    auth: dict = Depends(require_role(Role.CORTEX_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Provision a public ingestion key. The plaintext value is returned exactly once."""
    tenant_id = body.get("tenant_id") or auth.get("tenant_id")
    site_id = body.get("site_id")
    name = body.get("name", "operator-issued")
    if not tenant_id or not site_id:
        raise HTTPException(status_code=400, detail="both 'tenant_id' and 'site_id' are required")

    plaintext, record = await provision_api_key(db, tenant_id=tenant_id, site_id=site_id, name=name)
    return {
        "id": record.id,
        "tenant_id": record.tenant_id,
        "site_id": record.site_id,
        "name": record.name,
        "api_key": plaintext,
        "warning": "Store this key securely; it cannot be retrieved again.",
    }


@app.get("/v1/api-keys", tags=["Administration"])
async def list_api_keys(
    auth: dict = Depends(require_role(Role.CORTEX_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """List provisioned public keys for the authenticated tenant (never returns secrets)."""
    rows = (await db.execute(select(ApiKeyModel).where(ApiKeyModel.tenant_id == auth.get("tenant_id")))).scalars().all()
    return {
        "keys": [
            {
                "id": row.id,
                "site_id": row.site_id,
                "key_prefix": row.key_prefix,
                "name": row.name,
                "is_active": row.is_active,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
            }
            for row in rows
        ],
        "total": len(rows),
    }


@app.api_route("/v1/health", methods=["GET", "HEAD"], tags=["System"])
async def health_check():
    """Versioned health check for probes, load balancers and orchestrators."""
    observed_at = datetime.now(UTC).isoformat()
    return {
        "status": "healthy",
        "evidence_class": "process_liveness",
        "observed_at": observed_at,
        "service": settings.app_name,
        "environment": settings.app_env,
        "timestamp": observed_at,
    }


# ── Dashboard static export ──────────────────────────────────────────────────
# Runners control the dashboard location in an installed deployment; the repo
# layout is only consulted when the monorepo root could be located.
DASHBOARD_CANDIDATES = [os.getenv("DASHBOARD_DIR", "")]
if _REPO_ROOT is not None:
    DASHBOARD_CANDIDATES += [
        str(_REPO_ROOT / "apps" / "dashboard" / "out"),
        str(_REPO_ROOT / "dashboard" / "out"),
        os.path.abspath(os.path.join(os.getcwd(), "apps/dashboard/out")),
    ]

DASHBOARD_DIR = ""
for candidate in DASHBOARD_CANDIDATES:
    if candidate and os.path.isdir(candidate):
        DASHBOARD_DIR = os.path.realpath(candidate)
        break

if DASHBOARD_DIR:
    next_static_dir = os.path.join(DASHBOARD_DIR, "_next")
    if os.path.isdir(next_static_dir):
        app.mount("/_next", StaticFiles(directory=next_static_dir), name="dashboard_next")


def _safe_dashboard_path(relative: str) -> str | None:
    """Resolve a dashboard file path, refusing anything outside the export dir."""
    if not DASHBOARD_DIR or not relative:
        return None
    resolved = os.path.realpath(os.path.join(DASHBOARD_DIR, relative.strip("/")))
    if resolved != DASHBOARD_DIR and not resolved.startswith(DASHBOARD_DIR + os.sep):
        logger.warning("Blocked dashboard path traversal attempt: %s", relative)
        return None
    return resolved


def _dashboard_index() -> str | None:
    index_file = os.path.join(DASHBOARD_DIR, "index.html") if DASHBOARD_DIR else ""
    return index_file if index_file and os.path.isfile(index_file) else None


@app.api_route("/", methods=["GET", "HEAD"], tags=["System"])
async def root(request: Request):
    """Serve the operations portal to browsers, or JSON health to API clients."""
    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        observed_at = datetime.now(UTC).isoformat()
        return JSONResponse(
            {
                "status": "healthy",
                "evidence_class": "process_liveness",
                "observed_at": observed_at,
                "service": settings.app_name,
                "environment": settings.app_env,
                "timestamp": observed_at,
            }
        )

    index_file = _dashboard_index()
    if index_file:
        return FileResponse(index_file, media_type="text/html")

    return HTMLResponse(content=FALLBACK_WEBSITE_HTML, status_code=200)


@app.api_route("/dashboard", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route("/dashboard/", methods=["GET", "HEAD"], include_in_schema=False)
async def dashboard_redirect():
    index_file = _dashboard_index()
    if index_file:
        return FileResponse(index_file, media_type="text/html")
    return HTMLResponse(content=FALLBACK_WEBSITE_HTML, status_code=200)


@app.get("/{file_name:path}", include_in_schema=False)
async def serve_static_or_spa(request: Request, file_name: str):
    """Serve static files, exported Next.js subpages, or SPA fallbacks."""
    if file_name.startswith(("v1", "api", "docs", "redoc", "openapi.json", "health", "metrics", "ws", "_next")):
        raise HTTPException(status_code=404, detail="Not Found")

    resolved = _safe_dashboard_path(file_name)
    if resolved:
        if os.path.isfile(resolved):
            media_type = "text/html" if resolved.endswith(".html") else None
            return FileResponse(resolved, media_type=media_type)

        subpage_index = _safe_dashboard_path(os.path.join(file_name.rstrip("/"), "index.html"))
        if subpage_index and os.path.isfile(subpage_index):
            return FileResponse(subpage_index, media_type="text/html")

        index_file = _dashboard_index()
        if index_file:
            return FileResponse(index_file, media_type="text/html")

    return HTMLResponse(content=FALLBACK_WEBSITE_HTML, status_code=200)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("cortex_api.main:app", host=settings.host, port=settings.port, reload=settings.debug)
