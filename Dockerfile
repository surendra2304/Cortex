# Multi-stage Dockerfile for CORTEX Operations Platform
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim AS runner

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl sqlite3 tini && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app/apps/api/src:/app/packages/core/src:/app/packages/event_schema/src:/app/packages/agents/src:/app/packages/ai_universe_adapter/src:/app/packages/tool_runtime/src:/app/packages/integrations/src:/app/packages/policy_engine/src:/app/packages/workflow_engine/src:/app/packages/identity/src"

RUN mkdir -p /app/data

COPY packages/ ./packages/
COPY apps/ ./apps/
COPY infra/ ./infra/

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["tini", "--"]
CMD ["sh", "-c", "uvicorn nexus_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
