
### B1 — DONE (2026-10-07 ~15:45 UTC)
- **Worker was dead in real life**: redis-py 8.1 (unpinned `redis>=5.0.0` drift) speaks RESP3; dev double speaks RESP2 → XREADGROUP parse crash every cycle, zero events processed.
- Fixes: `requirements.txt` pins `redis>=5.0.0,<8.0.0`; worker pins `protocol=2` explicitly (`REDIS_PROTOCOL` env); API `config.py` redis pool pins `protocol=2`.
- **Silent event drop fixed**: worker acked messages even when the cognitive loop failed. Now: ack only on success/poison; loop errors stay pending; PEL recovery loop (XCLAIM/XPENDING, 30s cadence, 60s min-idle) reprocesses stranded messages; poison (unparseable) acked + logged; after 5 failed deliveries a message is acked so one bad event can't wedge the stream.
- **NOGROUP self-heal fixed**: after a Redis restart the group vanished and the worker spun on NOGROUP forever (found live: events piled up unconsumed). Worker now re-creates the group on NOGROUP.
- **dev_redis.py upgraded**: pending entries now track consumer/delivered_at/delivery_count; added XPENDING (summary + both range syntaxes — redis-py 7.4 sends the legacy positional form, caught by live test) and XCLAIM.
- Verified live: 3 events ingested → loop ran (NO_ACTION ×2, NURTURE_LEAD); poison message dropped+acked; stranded event reclaimed by PEL recovery and processed; double restart survived by API+worker; PEL ends empty; audit records written per loop.
- Tests: `tests/unit/test_worker_delivery.py` (12 tests) — all pass. Full suite: **352 passed, 3 skipped**.
- Files: requirements.txt, apps/worker/src/cortex_worker/main.py, apps/api/src/cortex_api/config.py, scripts/dev_redis.py, tests/unit/test_worker_delivery.py

### B2 — DONE (2026-10-07 ~16:20 UTC): the autonomous loop is closed end-to-end
Dead ends found by driving the agent like the owner (identify → high-intent events → checkout):
1. **Identified visitors were invisible to the loop**: Contextualize looked up VisitorModel by actor.id only; identified users' events carry user_id, never the anonymous visitor id. Fixed: identity service now persists user_id/email→profile IdentityLinkModel rows (deduped; anonymous link dedup too), and the orchestrator resolves actors through the identity graph (`IdentityResolver.resolve_actor_profile`).
2. **Repeat research scored as zero intent**: ContextBuilder and the agent input used only the current event + session window, ignoring the actor's cross-session history. Fixed: full recent history (deduped by event_id) feeds intent/recency scoring.
3. **Gated actions vanished**: the loop proposed, the policy gated (HIGH_IMPACT → requires_human_approval), and nothing happened — no approval request, ever. Fixed: the loop now creates a tenant-scoped ApprovalQueueModel row (24h expiry, matches the worker's auto-expire) with params/rationale/evidence/risk; trace + audit + loop result carry `pending_approvals`.
4. **Approving did nothing**: the ORM approval queue was write-never, and `/v1/actions/{id}/approve` only flipped status. Fixed: approval now EXECUTES the action through the tool bus (idempotency key per approval id) and records execution_status/execution_result on the row (new columns + alembic 006); `/v1/approvals/pending` surfaces them.
5. **Route shadowing + fabricated data**: public_gateway registered a stub `POST /v1/actions/{id}/approve` (served a fake in-memory ACTIONS_DB, always 404 for real approvals) and a fabricated `GET /v1/workflows` list, both shadowing the real understand_router implementations. Removed both; the landing page's demo handler no longer renders "execution confirmed" regardless of the API response (it renders the real one).
Verified LIVE: identify enterprise visitor → 6 events → checkout → ROUTE_ENTERPRISE_LEAD (lead_score 0.95) → approval `appr_loop_bf803d34_account_update` (risk 0.8) → operator approves → account_update EXECUTED (enterprise_tier_1) → recorded → re-approve 409.
Tests: new approval-flow test in test_auth_and_rbac.py + rewritten stub test in test_public_gateway.py + identity-test query-count fix + ContextBuilder dedupe fix (key on event_id, never collapse id-less events). Full suite: **353 passed, 3 skipped**.
Files: packages/identity/.../service.py, packages/core/.../orchestrator.py, packages/intelligence/.../__init__.py, apps/api/.../db_models.py, apps/api/.../understand_router.py, apps/api/.../public_gateway.py, apps/api/.../landing_page.py, infra/alembic/versions/006_approval_execution_columns.py, tests/conftest.py, tests/unit/{test_auth_and_rbac,test_public_gateway,test_identity_service}.py

### B3 — DONE (2026-10-07 ~16:30 UTC): cross-tenant IDOR killed (live-verified)
- `GET /v1/visitors/{id}` and `GET /v1/leads/{id}` (public_gateway) looked records up by id alone — a tenant_attacker JWT read tenant_default's visitor profile incl. email and leads. Now tenant-scoped (404 cross-tenant); the profile lookup inside get_visitor is scoped too.
- Orchestrator Contextualize lookups (visitor/profile/lead/session/actor-history) are now tenant-scoped (done with B2).
- `/v1/friday/priority_leads` and `/v1/friday/incidents` (platform identity, tenant "system") gained an optional explicit `?tenant_id=` scope; the profile-email enrichment lookup is scoped to the lead's tenant.
- Live re-test of the original exploit: attacker JWT (cortex_viewer, tenant_attacker) → 404 on both endpoints; owner → 200.
- New `tests/unit/test_tenant_isolation_reads.py` (4 tests) locks: cross-tenant visitor/lead reads 404 (and no PII in the response), lead lists tenant-scoped, understand-router scoped reads stay scoped.
- Full suite: **353 passed, 3 skipped** (then 357 with the new file).
Files: apps/api/src/cortex_api/public_gateway.py, apps/api/src/cortex_api/friday_router.py, tests/unit/test_tenant_isolation_reads.py

### B4 — DONE (2026-10-07 ~16:50 UTC): operator gauntlet — all live scripts green
- `scripts/self_integrity_live_test.py`: 55/55 (was 52/53 — see the command-loop fix below).
- `scripts/self_healing_live_test.py`: full pass — real Redis outage induced (pkill), circuit OPEN (4 consecutive failures), self-model honestly degraded, Redis restored, breaker self-healed CLOSED, API healthy throughout. Script fixed: hardcoded FRIDAY key (rejected by the API) replaced with probe + dev-bypass resolution; dev_redis restart path made absolute.
- `scripts/run_e2e_system_test.py`: converted from TestClient+mocked DB/Redis (which let auth/ingestion checks pass against fixtures) to a TRUE live suite: real JWTs, provisioned ingestion key (public-key auth, not Bearer), FRIDAY probe/fallback, live WebSocket via websockets lib, honest WS failure reporting. 35/35 HEALTHY.
- `scripts/escalation_delivery_live_test.py`: 14/14.
- Dead ends found & fixed while driving the agent:
  1. **`/v1/friday/command` saw no history**: my B2 history dicts referenced `EventModel.event_id` (column doesn't exist — PK is `id`), which the Contextualize try/except swallowed, silently dropping session/actor/memory lookups for EVERY loop (worker included). Fixed (`r.id`); the command loop now sees full session history, intent 1.0, and 4a.Collaborate runs (agent_growth + agent_sales, consensus recorded).
  2. **`scripts/self_healing_live_test.py` auth**: stale hardcoded FRIDAY key (same pattern as .env.example defaults).
  3. **`run_e2e_system_test.py` was not live**: mocked harness + Bearer-token ingestion against the public-key endpoint + GDPR export of a never-created visitor + a WS except-branch that recorded PASS on any exception.
  4. **`POST /privacy/export/{visitor_id}` looked up `ProfileModel.id == visitor_id`** — profiles have their own `prof_*` ids, so the Art. 15 export 404'd for every real data subject. Now resolves visitor → profile (tenant-scoped), matching the erasure path.
- Full suite: **357 passed, 3 skipped**.
Files: scripts/{self_healing_live_test,run_e2e_system_test}.py, apps/api/src/cortex_api/production_router.py, packages/core/src/cortex_core/orchestrator.py
