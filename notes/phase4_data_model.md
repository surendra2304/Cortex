# Phase 4 — Data Model

Date: 2026-10-07

## ORM schema [FACT]

`apps/api/src/cortex_api/db_models.py` — **13 tables / 13 model classes** (SQLAlchemy 2.0 async, `Base`):

| # | Table (line) | Model | Purpose |
| :--- | :--- | :--- | :--- |
| 1 | `profiles` (:21) | ProfileModel | visitor profile attributes (email, name, …) |
| 2 | `visitors` (:36) | VisitorModel | anonymous/persistent visitor, FK → profile |
| 3 | `sessions` (:50) | SessionModel | session windows |
| 4 | `events` (:67) | EventModel | raw telemetry (tenant_id, actor_id, site_id, occurred_at, data JSON) |
| 5 | `leads` (:95) | LeadModel | leads, FK → profile |
| 6 | `audit_records` (:110) | AuditRecordModel | redacted audit trail (trace_id, action, target) |
| 7 | `api_keys` (:124) | ApiKeyModel | public ingestion keys (SHA-256 hash + prefix stored, never plaintext) |
| 8 | `identity_links` (:138) | IdentityLinkModel | cross-identity resolution links |
| 9 | `lead_scores` (:152) | LeadScoreHistoryModel | lead scoring history |
| 10 | `memory_entries` (:168) | MemoryEntryModel | strategy memory (tenant + scope) |
| 11 | `workflow_runs` (:183) | WorkflowRunModel | workflow executions |
| 12 | `approval_queue` (:197) | ApprovalQueueModel | pending/decided approvals |
| 13 | `strategy_performance` (:217) | StrategyPerformanceModel | outcome learning per strategy |

Tenant scoping [FACT]: every table carries `tenant_id`; reads in the routers filter by it (with the exceptions catalogued in Phase 10).

## Schema management [FACT]

- **Dev bootstrap**: on startup in non-production, the app runs `Base.metadata.create_all` and provisions a dev key (`pk_live_…` for `tenant_default`/`site_demo`) — this is why a fresh checkout "just works" and why `data/cortex.db` appears (`main.py` startup; `config.py`).
- **Prod**: alembic — `infra/alembic/` with `env.py` reading `DATABASE_URL`/`POSTGRES_DSN` env and `Base.metadata`; **5 version files** (`001_create_events_and_sessions` … `005_create_cognition_tables`) that together cover the 13 tables.
- `migrations/001_create_events_and_sessions.sql` — one raw SQL file (events + sessions only; superseded by alembic for prod).
- Default DSN is **SQLite** (`sqlite+aiosqlite:///./data/cortex.db`); Postgres via asyncpg when `POSTGRES_DSN` is set. `render.yaml` runs the **free tier with SQLite on ephemeral container disk** → data loss on restart/redeploy [INFERENCE from render.yaml `plan: free` + sqlite DSN].

## Redis usage [FACT]

- Stream `cortex:events:stream` (XADD on ingest, XREADGROUP by worker group `cortex-worker-group`).
- Sliding-window rate limiter per key+site (1000/60s), with an atomic Lua/`AtomicSlidingWindow` fallback.
- ToolBus idempotency: `SET NX EX 86400` per idempotency key.
- Dedupe store for event ids (plus DB `IntegrityError` backstop).

## Data-flow notes [FACT/INFERENCE]

- Ingestion is the only write path for events; everything else (profiles, visitors, leads, scores, memory, approvals, workflows, audit) is derived server-side.
- `SecretScrubber` (email/card/SSN/API-key/phone regexes) masks PII before logs/AI/exports (`policy_engine/privacy.py:22-64`); `hash_pii` is salted SHA-256 and **requires** an explicit salt or `CORTEX_PII_SALT`.
- GDPR Art. 15 export + Art. 17 cascading hard erasure implemented for real (8 tables purged, tenant-scoped, actual row counts returned) — `privacy.py:96-213`.
- Audit records are written by the Learn phase with redaction; `/audit/export` is hash-chained per the diary.
