from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import sys
import os

# Add local packages to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../packages/core/src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../packages/event_schema/src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../packages/agents/src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../packages/ai_universe_adapter/src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../packages/tool_runtime/src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../packages/policy_engine/src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../packages/workflow_engine/src")))

from nexus_api.config import settings
from nexus_api.tracing import TracingMiddleware
from nexus_api.events_router import router as events_router
from nexus_api.webhooks_router import router as webhooks_router
from nexus_api.stripe_webhook_router import router as stripe_webhook_router
from nexus_api.friday_router import router as friday_router
from nexus_api.public_gateway import router as public_gateway_router
from nexus_api.understand_router import router as understand_router
from nexus_api.production_router import router as production_router
from nexus_api.streaming_router import router as streaming_router

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

app.include_router(public_gateway_router)
app.include_router(events_router)
app.include_router(webhooks_router)
app.include_router(stripe_webhook_router)
app.include_router(friday_router)
app.include_router(understand_router)
app.include_router(production_router)
app.include_router(streaming_router)


@app.api_route("/", methods=["GET", "HEAD"], tags=["System"])
async def root():
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.app_env,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.api_route("/health", methods=["GET", "HEAD"], tags=["System"])
@app.api_route("/v1/health", methods=["GET", "HEAD"], tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.app_env,
        "timestamp": datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("nexus_api.main:app", host=settings.host, port=settings.port, reload=settings.debug)
