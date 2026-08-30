FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY README.md pyproject.toml ./
COPY packages/ ./packages/
COPY apps/ ./apps/
RUN pip install --no-cache-dir --user .

# Runtime image
FROM python:3.11-slim AS runner

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:$PATH" \
    PYTHONPATH="/app/apps/api/src:/app/packages/core/src:/app/packages/event_schema/src:/app/packages/agents/src:/app/packages/ai_universe_adapter/src:/app/packages/tool_runtime/src:/app/packages/integrations/src:/app/packages/policy_engine/src:/app/packages/workflow_engine/src:/app/packages/identity/src"

COPY --from=builder /root/.local /root/.local

COPY pyproject.toml .
COPY packages/ ./packages/
COPY apps/ ./apps/
COPY infra/ ./infra/

CMD ["python", "-m", "nexus_worker.main"]
