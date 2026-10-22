# CORTEX Production Architecture & Hardening Guide

## 1. Authentication & Security Tiers
- **Public SDK Endpoint (`/v1/events`, `/v1/events/batch`)**:
  - Authenticated via `X-Cortex-Public-Key` validated against hashed `api_keys` records in PostgreSQL.
  - Rate limited to **1,000 events/minute** per site key using Redis sliding-window buckets.
- **Operator Dashboard Gateway (`/v1/*`)**:
  - Authenticated via OIDC RS256 JWT tokens.
  - Strict Role-Based Access Control (RBAC): `cortex_viewer`, `cortex_operator`, `cortex_admin`.
- **FRIDAY & Internal Services Gateway (`/v1/friday/*`, `/v1/identity/resolve`)**:
  - Authenticated via `X-Friday-Api-Key` using constant-time `hmac.compare_digest()`.

---

## 2. Observability & Telemetry
- **Prometheus Metrics (`GET /metrics`)**:
  - `events_ingested_total`: Ingestion counter across all streams.
  - `cognitive_loop_duration_seconds`: Execution duration summary.
  - `ai_universe_calls_total` & `ai_universe_fallback_total`: AI usage and resilience telemetry.
  - `workflow_runs_total`: State machine execution counter.
  - `approval_queue_depth`: Pending sensitive actions gauge.
  - `strategy_performance_gauge`: Aggregated strategy success rate.
- **Health Probes**:
  - `GET /health`: Liveness probe for container orchestrators (Kubernetes/Docker).
  - `GET /health/ready`: Readiness probe actively verifying PostgreSQL, Redis, and AI Universe connectivity.
- **Structured Tracing**:
  - Distributed `trace_id` correlation across headers (`X-Cortex-Trace-Id`), database records, and logs.
- **Live Event Stream**:
  - `ws://host:8000/v1/ws/events`: WebSocket live event broadcast for dashboard real-time view.

---

## 3. Storage & High-Performance Indexing
- **Database Connection Pooling**:
  - `asyncpg` connection pool with `pool_size=20`, `max_overflow=10`, `pool_pre_ping=True`.
- **Event Store Composite Indexing**:
  - `idx_events_site_type_occurred` (`site_id`, `type`, `occurred_at`)
  - `idx_events_actor_occurred` (`actor_id`, `occurred_at`)
  - `idx_events_session` (`session_id`)
- **Query Performance**:
  - Optimized sub-100ms context queries using indexed session and actor history queries.

---

## 4. Graceful Shutdown & Maintenance
- **Safe-by-Default Approvals**:
  - Background maintenance task automatically expires and rejects overdue approvals (>24h).
- **Graceful Termination**:
  - Workers and API intercept `SIGTERM`/`SIGINT`, completing inflight events before closing connection pools.
