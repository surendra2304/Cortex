from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import sys
import os

# Add local packages to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../packages/core/src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../packages/event_schema/src")))

from nexus_api.config import settings
from nexus_api.events_router import router as events_router
from nexus_api.webhooks_router import router as webhooks_router

app = FastAPI(
    title=settings.app_name,
    description="Autonomous Website & Web App Operations Intelligence Platform API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events_router)
app.include_router(webhooks_router)


@app.get("/v1/health", tags=["System"])
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
