FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --user -r requirements.txt

# Runtime image
FROM python:3.11-slim AS runner

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:$PATH" \
    PYTHONPATH="/app:/app/apps/api/src:/app/packages/core/src:/app/packages/event_schema/src:/app/packages/agents/src:/app/packages/ai_universe_adapter/src:/app/packages/tool_runtime/src:/app/packages/integrations/src:/app/packages/policy_engine/src:/app/packages/workflow_engine/src:/app/packages/identity/src"

RUN apt-get update && apt-get install -y --no-install-recommends curl sqlite3 tini && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local

COPY packages/ ./packages/
COPY apps/ ./apps/
COPY infra/ ./infra/
COPY cortex_upgrade/ ./cortex_upgrade/

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["tini", "--"]
CMD ["sh", "-c", "uvicorn cortex_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
