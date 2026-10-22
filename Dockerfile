# ─────────────────────────────────────────────────────────────────────────────
# CORTEX — Production Dockerfile
# Oracle Cloud Always Free (ARM64 / amd64 compatible)
# Internal port: 8000 | Host port: 8001 | Mesh: friday_mesh
# Gateway: https://friday-universe.duckdns.org/cortex/*
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: frontend & SDK builder ───────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /build/packages/sdk
COPY packages/sdk/package.json ./
RUN npm install
COPY packages/sdk/ ./
RUN npm run build

WORKDIR /build/apps/dashboard
COPY apps/dashboard/package.json ./
RUN npm install
COPY apps/dashboard/ ./
RUN npm run build

# ── Stage 2: Python dependency builder ────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# ── Stage 3: Production runner ────────────────────────────────────────────────
FROM python:3.11-slim AS runner

# Security: non-root user
RUN useradd -m -u 1000 appuser

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl sqlite3 tini \
    && rm -rf /var/lib/apt/lists/*

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv

# Runtime environment
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8000
ENV PYTHONPATH="/app:/app/apps/api/src:/app/apps/worker/src:/app/packages/core/src:/app/packages/event_schema/src:/app/packages/agents/src:/app/packages/ai_universe_adapter/src:/app/packages/tool_runtime/src:/app/packages/integrations/src:/app/packages/policy_engine/src:/app/packages/workflow_engine/src:/app/packages/identity/src:/app/packages/analytics/src:/app/packages/intelligence/src:/app/packages/memory/src"

# Persistent data directory
RUN mkdir -p /app/data && chown -R appuser:appuser /app

# Copy application source
COPY --chown=appuser:appuser packages/ ./packages/
COPY --chown=appuser:appuser apps/ ./apps/
COPY --chown=appuser:appuser cortex_upgrade/ ./cortex_upgrade/
COPY --chown=appuser:appuser infra/ ./infra/

# Copy compiled SDK and dashboard static export from builder
COPY --from=frontend-builder --chown=appuser:appuser /build/packages/sdk/dist ./packages/sdk/dist
COPY --from=frontend-builder --chown=appuser:appuser /build/apps/dashboard/out ./apps/dashboard/out

# Switch to non-root user
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["tini", "--"]
CMD ["sh", "-c", "uvicorn cortex_api.main:app --host 0.0.0.0 --port ${PORT:-8000} --timeout-graceful-shutdown 5"]
