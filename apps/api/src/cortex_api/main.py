from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime
import sys
import os

from cortex_api.landing_page import FALLBACK_WEBSITE_HTML

# Add local packages to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../packages/core/src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../packages/event_schema/src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../packages/agents/src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../packages/ai_universe_adapter/src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../packages/tool_runtime/src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../packages/policy_engine/src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../packages/workflow_engine/src")))

from cortex_api.config import settings
from cortex_api.tracing import TracingMiddleware
from cortex_api.events_router import router as events_router
from cortex_api.webhooks_router import router as webhooks_router
from cortex_api.stripe_webhook_router import router as stripe_webhook_router
from cortex_api.friday_router import router as friday_router
from cortex_api.public_gateway import router as public_gateway_router
from cortex_api.understand_router import router as understand_router
from cortex_api.production_router import router as production_router
from cortex_api.streaming_router import router as streaming_router

app = FastAPI(
    title=settings.app_name,
    description="CORTEX Autonomous Web Operations Intelligence Platform API",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(TracingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
app.include_router(public_gateway_router)
app.include_router(events_router)
app.include_router(webhooks_router)
app.include_router(stripe_webhook_router)
app.include_router(friday_router)
app.include_router(understand_router)
app.include_router(production_router)
app.include_router(streaming_router)

# Resolve Dashboard static export directory
DASHBOARD_CANDIDATES = [
    os.getenv("DASHBOARD_DIR", ""),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../dashboard/out")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../apps/dashboard/out")),
    os.path.abspath(os.path.join(os.getcwd(), "apps/dashboard/out")),
    os.path.abspath(os.path.join(os.getcwd(), "dashboard/out")),
]

DASHBOARD_DIR = ""
for candidate in DASHBOARD_CANDIDATES:
    if candidate and os.path.isdir(candidate):
        DASHBOARD_DIR = candidate
        break

# Mount static build assets (_next) if available
if DASHBOARD_DIR:
    next_static_dir = os.path.join(DASHBOARD_DIR, "_next")
    if os.path.isdir(next_static_dir):
        app.mount("/_next", StaticFiles(directory=next_static_dir), name="dashboard_next")


@app.api_route("/health", methods=["GET", "HEAD"], tags=["System"])
@app.api_route("/v1/health", methods=["GET", "HEAD"], tags=["System"])
async def health_check():
    """Health check endpoint returning JSON status for probes, load balancers, and orchestrators."""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.app_env,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.api_route("/", methods=["GET", "HEAD"], tags=["System"])
async def root(request: Request):
    """
    Root endpoint serving the interactive CORTEX Operations Portal to browsers,
    or JSON health status to API clients sending Accept: application/json.
    """
    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return JSONResponse({
            "status": "healthy",
            "service": settings.app_name,
            "environment": settings.app_env,
            "timestamp": datetime.utcnow().isoformat()
        })

    if DASHBOARD_DIR:
        index_file = os.path.join(DASHBOARD_DIR, "index.html")
        if os.path.isfile(index_file):
            return FileResponse(index_file, media_type="text/html")

    return HTMLResponse(content=FALLBACK_WEBSITE_HTML, status_code=200)


@app.get("/dashboard", include_in_schema=False)
@app.get("/dashboard/", include_in_schema=False)
async def dashboard_redirect():
    if DASHBOARD_DIR:
        index_file = os.path.join(DASHBOARD_DIR, "index.html")
        if os.path.isfile(index_file):
            return FileResponse(index_file, media_type="text/html")
    return HTMLResponse(content=FALLBACK_WEBSITE_HTML, status_code=200)


@app.get("/{file_name:path}", include_in_schema=False)
async def serve_static_or_spa(request: Request, file_name: str):
    """Serves static files, exported Next.js subpages, or SPA fallbacks."""
    # Never shadow API, telemetry, or documentation paths
    if file_name.startswith(("v1", "api", "docs", "redoc", "openapi.json", "health", "metrics", "ws", "_next")):
        raise HTTPException(status_code=404, detail="Not Found")

    if DASHBOARD_DIR:
        clean = file_name.strip("/")
        # 1. Direct file match (e.g., favicon.ico, images)
        direct_file = os.path.join(DASHBOARD_DIR, clean)
        if os.path.isfile(direct_file):
            return FileResponse(direct_file)

        # 2. Exported page index.html (e.g., /agents -> out/agents/index.html)
        subpage_index = os.path.join(DASHBOARD_DIR, clean, "index.html")
        if os.path.isfile(subpage_index):
            return FileResponse(subpage_index, media_type="text/html")

        # 3. Fallback to main index.html for client-side routing
        index_file = os.path.join(DASHBOARD_DIR, "index.html")
        if os.path.isfile(index_file):
            return FileResponse(index_file, media_type="text/html")

    return HTMLResponse(content=FALLBACK_WEBSITE_HTML, status_code=200)



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("cortex_api.main:app", host=settings.host, port=settings.port, reload=settings.debug)
