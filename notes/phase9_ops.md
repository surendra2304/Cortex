# Phase 9 — Operations & Deployment

Date: 2026-10-07

## Processes [FACT]

- **API**: uvicorn, `cortex_api.main:app`, port `${PORT:-8000}`; `/health` (liveness), `/health/ready` (deep: postgres/schema/redis required; ai_universe/sentinel/intelx/futuris degraded-tolerant), `/metrics` (Prometheus).
- **Worker**: `python -m cortex_worker.main` — creates consumer group `cortex-worker-group`, registers 11 tools, XREADGROUP loop. [FACT, booted this session] **Broken against the bundled dev double**: redis-py 8.1.0 defaults to RESP3 (`redis/utils.py:283`), the double speaks RESP2, and the XREADGROUP reply shape (array-of-pairs) hits the RESP3 parser expecting a map → `AttributeError: 'list' object has no attribute 'items'` every cycle; events are never processed and pile up in the double's PEL. Works against a real Redis 7 (RESP3 maps). Root cause: unpinned `redis>=5.0.0` floor → dependency drift.
- **Dashboard**: static export served by the API (see Phase 7); its own Dockerfile CMD is broken (`next start` vs `output: export`, executed this session).

## Container & orchestration [FACT]

- Root `Dockerfile`: multi-stage `python:3.11-slim`, `pip install --user -r requirements.txt`, copies packages/apps/infra/cortex_upgrade, `ENV PYTHONPATH` covering all src dirs, `tini` entrypoint, HEALTHCHECK on `/health`. **Runs as root** (no USER). Builds the dashboard and serves `out/` via the API.
- `apps/api/Dockerfile` / `apps/worker/Dockerfile`: same shape, also **root**, `curl+sqlite3+tini` in runtime.
- `docker-compose.yml`: postgres:15 + redis:7 + api + worker + dashboard. **Stale `nexus_*` naming throughout** (container names, postgres user/db `nexus`/`nexus_db`) — the project was renamed to Cortex (diary Day 4) but compose wasn't. Worker service builds from `apps/api/Dockerfile` with a command override. Dashboard service inherits the broken CMD and a stale `NEXT_PUBLIC_NEXUS_API_URL`.
- `infra/k8s/deployment.yaml` and `infra/terraform/main.tf` also still use `nexus_*` resource names [FACT, heads read].
- `render.yaml`: web service, docker runtime, **plan: free**, region singapore, healthCheckPath `/health`, `APP_ENV=production`, `MOCK_MODE=false`, `POSTGRES_DSN=sqlite+aiosqlite:////app/data/cortex.db` (absolute path, with an explanatory comment about the dead `DATABASE_URL`), all FRIDAY-Universe peer URLs (render.com) with `sync: false` secrets. [INFERENCE] Free tier + SQLite on container disk ⇒ **data resets on restart/redeploy**; not a production data store.

## Observability & tooling [FACT]

- Prometheus `/metrics` (counters/gauges for ingestion, tools, workflows, approvals — per diary Day 2); structured logging with trace ids; `tracing.py` (API) + `packages/*/tracing.py`.
- `scripts/`: `run_api.py` (dev runner), `dev_redis.py` (RESP2 double), `pressure_test.py` (9-scenario live harness — **9/9 PASS this session**, see Phase 11), `validate_diary.py` (CI doc gate), `self_healing_live_test.py`, `self_integrity_live_test.py`, `run_e2e_system_test.py`, `escalation_delivery_live_test.py`, `dev_redis.py --host 0.0.0.0` used for live verification.
- No log aggregation, no APM, no alerting config in-repo; self-healing escalates in-process (`self_model` `pending_escalations`) but there is no pager/hook wired by default [INFERENCE].

## Backup/DR [FACT/ABSENCE]

No backup, migration-runbook, or DR documentation beyond alembic. `migrations/001_*.sql` is a raw single migration. Nothing in CI exercises alembic upgrade on Postgres (no Postgres service in CI) [FACT — ci.yml has no services block].
