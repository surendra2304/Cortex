# Build the browser workspace inside the image. The checked-in export is ignored
# by .dockerignore so Render and CI must produce it from the dashboard source.
FROM node:20-alpine AS dashboard-builder

WORKDIR /dashboard
# Copy the root workspace manifests (npm workspaces — lock lives at the root)
COPY package.json package-lock.json ./
# Copy the dashboard source and any other workspace packages referenced
COPY apps/dashboard/ ./apps/dashboard/
# Install only dashboard deps (workspace install from root)
RUN npm ci --workspace=apps/dashboard
WORKDIR /dashboard/apps/dashboard
RUN npm run build

# Multi-stage Dockerfile for CORTEX Operations Platform
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && pip install --no-cache-dir -r requirements.txt

# Production Runner
FROM python:3.11-slim AS runner

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl sqlite3 tini && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app:/app/apps/api/src:/app/apps/worker/src:/app/packages/core/src:/app/packages/event_schema/src:/app/packages/agents/src:/app/packages/ai_universe_adapter/src:/app/packages/tool_runtime/src:/app/packages/integrations/src:/app/packages/policy_engine/src:/app/packages/workflow_engine/src:/app/packages/identity/src:/app/packages/analytics/src:/app/packages/intelligence/src:/app/packages/memory/src"

RUN mkdir -p /app/data

COPY packages/ ./packages/
COPY apps/ ./apps/
COPY --from=dashboard-builder /dashboard/apps/dashboard/out ./apps/dashboard/out
COPY infra/ ./infra/
COPY cortex_upgrade/ ./cortex_upgrade/

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

ENTRYPOINT ["tini", "--"]
CMD ["sh", "-c", "uvicorn cortex_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
