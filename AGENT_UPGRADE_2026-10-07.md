# CORTEX Agent Upgrade — 2026-10-07/08

Campaign: make the agent work in real life, drive it like its owner, push it to
dead ends and extreme pressure, find and fix every error, and leave real-life
tests that lock every fix. Branch `arena/998f44c2-cortex`.

The baseline analysis is `REPO_ANALYSIS.md` (repo comprehension report); the
running work log is `notes/UPGRADE_PLAN.md`; the checklist is `AGENT_PROGRESS.md`.

---

## 1. Before / after

| | Before (83e6f9a) | After |
|---|---|---|
| Worker processes events | **No** — redis-py 8 RESP3 vs RESP2 double crashed every read | **Yes** — processes, recovers, drains (32k events verified live) |
| Event→loop→action closed loop | **No** — gated proposals vanished; approval queue write-never | **Yes** — propose → gate → approval → execute → record (live-verified) |
| Cross-tenant IDOR (visitors/leads) | **Yes, live-confirmed** (emails leaked) | **Fixed** — 404 cross-tenant (live-verified) |
| `/connectors` health | Hardcoded all-HEALTHY table | Real probes, honest UNVERIFIED/UNHEALTHY |
| Dev auth bypass | On by default (MOCK_MODE=true) | **Opt-in** (`CORTEX_DEV_AUTH_BYPASS=true`), off in production |
| API-key provisioning | Any admin, any tenant | Tenant-bound (403 cross-tenant) |
| GDPR Art. 15 export | 404 for real visitors; redacted own data | Resolves visitor→profile; subject's data unredacted |
| `/v1/friday/command` context | Event only (my history dict bug + actor mismatch) | Full session/actor history; collaboration fires |
| Worker drain rate | ~0.5 loops/s (dead AI peer burned 2s/loop) | Bounded-concurrent (4) + AI fail-fast cooldown |
| 5000@200/60s pressure | n/a | 9/9 PASS ×3, 20k capacity run 20000/20000, 0 5xx |
| Test suite | 339 passed, 1 order-dependent fail | **366 passed, 3 skipped** |
| Live scripts | integrity 52/53; e2e mocked-fixture "test" | integrity **55/55**; e2e **live 35/35**; self-healing outage→recovery pass; escalation 14/14; gauntlet **51/51**; operator load 102/102 |

---

## 2. Every bug found → fixed → test-locked

### B1 — the agent could not process events at all
1. **redis-py 8 RESP3 drift** (unpinned `redis>=5.0.0`): the RESP2 double's
   XREADGROUP reply crashed the worker every cycle (`AttributeError: 'list'
   object has no attribute 'items'`); zero events processed.
   Fix: `redis>=5.0.0,<8.0.0` pin + explicit `protocol=2` in worker and API.
   Tests: `tests/unit/test_worker_delivery.py`.
2. **Silent event drop**: the worker XACKed messages even when the cognitive
   loop failed. Fix: ack only on success/poison; loop errors stay pending;
   after 5 failed deliveries ack so one bad event can't wedge the stream.
   Tests: `test_worker_delivery.py` (4 ack-policy tests).
3. **No PEL recovery**: crashed worker's messages stranded forever.
   Fix: XPENDING/XCLAIM recovery loop (30s cadence, 60s min-idle).
   Tests: 2 PEL-recovery tests; live-verified (thief-consumer stranding →
   reclaimed → processed → acked).
4. **NOGROUP spin**: after a Redis restart the worker looped on NOGROUP forever
   (found live). Fix: `ensure_stream_group` self-heal. Tests: 2 self-heal tests.
5. **dev_redis double lacked XPENDING/XCLAIM** and mis-parsed redis-py's legacy
   positional XPENDING form (caught by live test). Fix: pending-entry tracking
   (consumer/idle/deliveries) + both XPENDING syntaxes + XCLAIM.

### B2 — the autonomous loop could not close
6. **Identified visitors invisible**: Contextualize looked up `VisitorModel.id ==
   actor.id`; identified users' events carry user_id → profile never resolved
   (`email_present=False` for every enterprise lead). Fix: identity service now
   persists user_id/email→profile `IdentityLinkModel` rows (deduped) and the
   orchestrator resolves actors through the identity graph
   (`IdentityResolver.resolve_actor_profile`). Tests:
   `test_identity_service.py` extended; live: `email_present=True`, lead_score
   0.39→0.95.
7. **Repeat research scored zero intent**: ContextBuilder + agent input used only
   the current event + session window. Fix: full cross-session history, deduped
   by `event_id` (id-less events never collapse). Tests:
   `test_understand_layer.py` kept honest.
8. **Gated proposals vanished** (dead end, live): policy gated HIGH_IMPACT →
   `requires_human_approval` → nothing happened — no approval request, ever.
   Fix: the loop creates a tenant-scoped `ApprovalQueueModel` row (24h expiry,
   params/rationale/evidence/risk) and records `pending_approvals` in the audit.
9. **Approving did nothing** (dead end, live): the approval queue was
   write-never; `POST /v1/actions/{id}/approve` only flipped status. Fix:
   approval now executes the action through the tool bus (idempotency key per
   approval id) and records `execution_status`/`execution_result` on the row
   (alembic 006). Test: `test_auth_and_rbac.py::test_approval_flow_executes_on_approval`
   (full flow incl. 409 re-decide).
10. **Route shadowing + fabricated data**: `public_gateway` served a fake
    in-memory `ACTIONS_DB` approve stub and a fabricated `/workflows` list,
    shadowing the real implementations (real approvals always 404'd). Fix:
    removed both; landing-page demo handler renders the real API response
    instead of "ToolBus execution confirmed" regardless of outcome.
    Test: `test_public_gateway.py` rewritten to the real flow.
11. **`EventModel.event_id` AttributeError (my bug, caught live)**: history dicts
    referenced a nonexistent column; the Contextualize try/except swallowed it,
    silently dropping session/actor/memory lookups for EVERY loop. Fix: `r.id`
    (the PK). Found because `/v1/friday/command` saw zero history.

### B3 — cross-tenant IDOR (live-confirmed CRITICAL)
12. **`GET /v1/visitors/{id}` / `GET /v1/leads/{id}`** had no tenant filter —
    tenant_attacker read tenant_default's profile incl. email and leads.
    Fix: tenant-scoped lookups (404 cross-tenant, no PII in responses) + the
    profile lookup inside get_visitor. Tests:
    `tests/unit/test_tenant_isolation_reads.py` (4 tests). Live re-test of the
    original exploit: 404/404.
13. **Orchestrator Contextualize lookups** unscoped (visitor/profile/lead/session/
    actor history) — tenant-scoped with B2.
14. **`/v1/friday/priority_leads` & `/v1/friday/incidents`** (platform identity):
    optional explicit `?tenant_id=` scope; profile-email enrichment scoped to
    the lead's tenant.

### B4 — operator gauntlet (driving the agent like its owner)
15. **`run_e2e_system_test.py` was not live**: TestClient + mocked DB/Redis let
    auth/ingestion checks pass against fixtures; Bearer token used against the
    public-key ingestion endpoint; GDPR export of a never-created visitor;
    WS "PASS" recorded on any exception. Fix: converted to a true live suite
    (real JWTs, provisioned key, FRIDAY probe/fallback, live WebSocket, honest
    failures). Result: 35/35 HEALTHY.
16. **`self_healing_live_test.py` auth**: stale hardcoded FRIDAY key crashed the
    script on the error body. Fix: probe + dev-bypass resolution (same pattern as
    the other live scripts); absolute dev_redis restart path.
17. **GDPR Art. 15 export 404 for every real visitor**: endpoint looked up
    `ProfileModel.id == visitor_id` (profiles have their own `prof_*` ids).
    Fix: resolve visitor → profile, tenant-scoped.
18. **GDPR Art. 15 export redacted the subject's own email**
    (`[REDACTED_EMAIL]`) — the log scrubber was over-applied to the access
    request itself, defeating the right of access. Fix: export carries the
    subject's own data unredacted (scrubber stays for logs/AI prompts). Tests:
    `test_privacy_and_compliance.py` + `test_privacy_flow.py` updated.
19. **`scripts/self_healing_live_test.py` / gauntlet contract drift** found by
    driving: the real `/v1/friday/task` envelope (actions:
    `health_summary|recommend_intervention|execute_operation|cancel|rollback`),
    recommend→approve→decide flow, nested `collaboration` response, rollback
    list syntax — all now exercised by
    `scripts/operator_gauntlet_live_test.py` (51/51) and
    `scripts/operator_load_live_test.py` (102/102, 0 5xx).

### B5 — extreme pressure
20. **Dead AI peer burned ~2s per event** (3 retries + backoff) — serial worker
    capped at <1 loop/s under load. Fix: fail-fast cooldown (3 consecutive
    server-side failures → 30s of immediate honest fallback; 4xx doesn't trip
    it). Tests: `tests/unit/test_ai_adapter_cooldown.py` (3).
21. **SQLite write contention**: no busy timeout, rollback journal → "database
    is locked" risk with API+worker+approval writers. Fix: WAL + 30s busy
    timeout (file-backed dev DBs).
22. **Serial worker delivery**: one event at a time. Fix: bounded-concurrent
    delivery (`WORKER_MAX_CONCURRENCY=4`, semaphore + task reaping; ack policy
    unchanged). Verified: 32k-event backlog drained to PEL=0.
23. **Unbounded in-memory audit list** (slow leak on long-running workers): now
    `deque(maxlen=1000)`; the DB row is the durable record.

Pressure results (live): 5000@200/60s **9/9 PASS** ×3 (idempotency race
accepted=1/duplicate=199; tenant isolation 200×403; unauth 300×401; rate-limit
burst 1120→120×429, 0 5xx; hostile input 0 5xx; 93–111 rps, 0 drops; soak 0 5xx;
consistency exact). 20k capacity run: **20000/20000 accepted, 0 5xx, 0 drops**.
Concurrent operator load: **102/102 OK** (20 full cognitive loops + workflows +
approvals + GDPR + sentinel + ingestion simultaneously), worker drained.

### B6 — remaining security ledger
24. **S5**: `POST /v1/api-keys` took `tenant_id` from the body — any admin minted
    keys for any tenant. Fix: tenant-bound (credential wins; mismatch → 403).
    Tests: `test_security_hardening_2026_10_07.py`. Live: 403 with detail.
25. **S6**: dev auth bypass implied by `MOCK_MODE=true` (the default) —
    unauthenticated cortex_admin on any non-prod box. Fix: opt-in
    (`CORTEX_DEV_AUTH_BYPASS=true`), off in production regardless. Tests:
    subprocess import-time tests (3).
26. **S7**: unsigned webhooks accepted whenever not production. Fix: fail closed
    unless a signing secret is configured OR the explicit dev bypass is on
    (503). Tests: 2 webhook tests (honest `signature_verified:false`).
27. **S10**: `/connectors` served a hardcoded all-HEALTHY static registry —
    fabricated health hiding real outages. Fix: real `ConnectorManager` checks;
    honest UNVERIFIED when no probe is configured; simulated outages surface.
    Test: `test_connectors_ecosystem.py` updated (incl. outage surfacing).

---

## 3. Verification (final state, all live)

- **pytest**: 366 passed, 3 skipped (341→366 this campaign; +27 new tests).
- **ruff + flake8**: clean across apps/packages/cortex_upgrade/scripts/tests.
- **Live scripts** (against the running stack):
  - `self_integrity_live_test.py` — **55/55**
  - `self_healing_live_test.py` — real outage → circuit OPEN → honest degraded
    self-model → restore → self-healed CLOSED → operational
  - `run_e2e_system_test.py` — **35/35 HEALTHY (live)**
  - `escalation_delivery_live_test.py` — **14/14**
  - `operator_gauntlet_live_test.py` — **51/51** (tasks, approvals,
    execute-on-approve, cancel/rollback, workflows, collaboration, self-mod
    refusals, GDPR round trip, dead ends)
  - `operator_load_live_test.py` — **102/102**, 0 5xx, PEL=0
  - `pressure_test.py` — **9/9** (5000@200/60s) and the 20k capacity run
- **Live security re-tests**: IDOR 404 cross-tenant; api-key minting 403
  cross-tenant; `/connectors` honest; unsigned webhook 200 only under the
  explicit bypass.

## 4. How to verify from scratch

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt \
  pytest pytest-asyncio pytest-mock respx httpx flake8 ruff
.venv/bin/python -m pytest tests -q                     # 366 passed, 3 skipped

# full stack (three processes; worker needs the monorepo PYTHONPATH)
.venv/bin/python scripts/dev_redis.py --host 0.0.0.0 --port 6379 &
REDIS_URL=redis://127.0.0.1:6379/0 APP_ENV=development \
  CORTEX_DEV_AUTH_BYPASS=true .venv/bin/python scripts/run_api.py --port 8000 &
REDIS_URL=redis://127.0.0.1:6379/0 PYTHONPATH=.:./*/*/src:./*/*/*/src \
  .venv/bin/python -m cortex_worker.main &              # see AGENT_PROGRESS for the exact PYTHONPATH

.venv/bin/python scripts/operator_gauntlet_live_test.py      # 51/51
.venv/bin/python scripts/run_e2e_system_test.py              # 35/35
.venv/bin/python scripts/self_integrity_live_test.py         # 55/55
.venv/bin/python scripts/pressure_test.py --concurrency 200 --events 5000 --soak-seconds 60 ...
```

## 5. Notes and honest caveats

- The dev auth bypass still exists (devs need it); it is now **explicitly
  opt-in** and loudly logged. Production refuses it unconditionally.
- AI Universe/Sentinel/Futuris peers are unreachable from this sandbox; their
  clients degrade honestly (deterministic fallback, honest UNKNOWN health,
  fail-fast cooldown). The `gap: tool_execution health has never been observed`
  in the self-model is honest — tools execute through the bus but the
  provider-side verification path is unobserved by design.
- `next start` for the dashboard remains broken by `output: 'export'` (serve
  `out/` instead) — documented in REPO_ANALYSIS, unchanged here (out of scope
  for the agent runtime).
- Single uvicorn worker + SQLite + dev-double pressure numbers are not
  production-representative; the fixes (WAL, concurrency, cooldown) are.
