# Multi-stage Dockerfile for NEXUS API & Worker Services
FROM python:3.11-slim as builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir --user .

# Runtime image
FROM python:3.11-slim as runner

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:$PATH" \
    PYTHONPATH="/app/apps/api/src:/app/packages/core/src:/app/packages/event_schema/src:/app/packages/agents/src:/app/packages/ai_universe_adapter/src:/app/packages/tool_runtime/src:/app/packages/integrations/src:/app/packages/policy_engine/src:/app/packages/workflow_engine/src:/app/packages/identity/src"

COPY --from=builder /root/.local /root/.local

COPY pyproject.toml .
COPY packages/ ./packages/
COPY apps/ ./apps/
COPY infra/ ./infra/

EXPOSE 8000

CMD ["uvicorn", "nexus_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
