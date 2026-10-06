# CORTEX — Phase 5 Handoff Report

**Session branch:** `arena/01a10cc3-cortex` · **Date:** 2026-10-05 · **Last commit:** `4ec9835`

Everything below is backed by a command that ran in this session. Where a claim was not
verified, it is labelled **CONFIGURED-BUT-UNVERIFIED** with the reason.

---

## 1. Final verification gauntlet (actual results)

| Check | Command | Result |
| :--- | :--- | :--- |
| Full test suite | `pytest tests -q` | **278 passed, 1 warning in 15.56s** |
| Lint (ruff) | `ruff check .` | **All checks passed** (was 1448 findings at session start) |
| Lint (flake8) | `flake8 .` | **clean** (was 972) |
| Format | `black --check --line-length 120 .` | **173 files unchanged** |
| SDK typecheck | `cd packages/sdk && npm test` | **clean** (`tsc --noEmit`; no tsconfig existed before this session) |
| SDK build | `cd packages/sdk && npm run build` | **CJS/ESM/IIFE + d.ts success** |
| Dashboard build | `cd apps/dashboard && npm run build` | **18 routes prerendered, success** |
| Cold boot from an empty tree | `rm -rf data && scripts/run_api.py` | bootstrap key provisioned, `/v1/health` 200, `/health/ready` **200 READY**, `/metrics` 200 |
| Pressure harness (rate-limited config) | `scripts/pressure_test.py --concurrency 200 --events 5000 --soak-seconds 60` | **9/9 scenarios PASS**, exit 0 |
| Pressure harness (capacity config, `RATE_LIMIT_MAX_REQUESTS=100000`) | `--concurrency 200 --events 20000 --soak-seconds 90` | **20 000/20 000 accepted, 0 5xx, 0 dropped connections, RSS +0.1 %** |
| Independent DB read-back | `sqlite3` counts after the capacity run | 30 391 rows, **0 duplicate ids**, 0 null `occurred_at`, all tenant-scoped |

Environment honesty: Redis here is `scripts/dev_redis.py` (a development RESP double written
in this session), not a production Redis. Postgres, outbound connectors and the AI Universe
service are unavailable in this sandbox (`AI Universe request failed ... Name or service not
known` → deterministic fallback engaged, and the response labels itself
`ai_provenance.source = deterministic_fallback_policy`).

---

## 2. Defects found by real-world exercise (not by reading code)

| # | Severity | Defect | Evidence | Status |
| :-- | :-- | :--- | :--- | :--- |
| 1 | **CRITICAL** | `POST /v1/friday/task` with an action the property allows but the router does not implement (e.g. `action=banner_injection`) replied `status=SUCCESS, state=COMPLETED, classification=REAL` **while doing nothing** — no observation, recommendation, approval or execution. A supervisor would believe a change had been applied. | live HTTP probe; response body captured | **FIXED** — fails closed with 422 + supported-action list; `classification` no longer defaults to `REAL` (`test_friday_task_routing.py`) |
| 2 | **HIGH** | `POST /v1/friday/approvals/{id}/decide` with `approved=false` returned **HTTP 400 `'GovernedOperationsEngine' object has no attribute 'reject'`** — the rejection branch had never existed, and internals leaked to the caller. | live HTTP probe | **FIXED** — real `reject()`, terminal decisions (409 on re-decide), 404 unknown id, 500 without internals (`test_approval_decisions.py`) |
| 3 | **HIGH** | Fabricated compliance/telemetry data: `/v1/audit/{resource}` invented an `aud_sample_1` row stamped at request time; `/audit/export` injected three hardcoded records when the DB was empty; `/v1/tenant/usage` reported fixed `184500` events / `850` workflows / `1240` AI calls while the tenant had 30 391 rows; `/analytics/{metric}` returned the same three `2026-08-27` points for every metric name. | live probes before/after | **FIXED** — real queries; unsupported metrics report `supported=false` with an explanatory note (`test_no_fabricated_data.py`, 6 tests) |
| 4 | **HIGH** | `GET /v1/events` clamped `limit` to 200 and had **no `offset`**: every accepted event older than the newest 200 was unreadable, and a failing query returned HTTP 200 `[]` (a DB error looked like "no data"). | pressure harness consistency scenario: `accepted=1970, readable=199` | **FIXED** — `offset` + stable `(occurred_at, id)` ordering; DB failures are 5xx (`test_ingestion_security.py`) |
| 5 | **HIGH** | `/health/ready` returned **503 NOT_READY with postgres, schema and redis all UP**, because four optional integrations have no live probe (`UNKNOWN`) and every value had to be `UP`. A readiness gate that can never pass pulls a healthy service out of rotation. | live cold-boot probe | **FIXED** — required vs degraded dependencies; missing schema / dead Redis still 503 |
| 6 | MEDIUM | Harness-visible client defect: 200 concurrent requests produced `httpx.ReadError` on keep-alive reuse; the run died with a traceback instead of reporting. | pressure run 1 | **FIXED (harness)** — retries + classified `dropped-connections` counts; 0 since |
| 7 | MEDIUM | `scripts/dev_redis.py` sprayed tracebacks for port probes/aborted connections. | process log | **FIXED** |
| 8 | MEDIUM | `cortex_upgrade.ApprovalQueue.decide` allowed a decided approval to be **flipped** (approved → rejected → approved). | code + test | **FIXED** — terminal, idempotent replay, conflict refused |
| 9 | LOW | `/v1/friday/command` executed a full cognitive loop even when the AI Universe service is unreachable, silently using the deterministic fallback (it does label the provenance, but nothing surfaces it in the top-level response). | server log + audit record | **OPEN** — honest-labelled but surfaced only in the audit payload |
| 10 | LOW | Fabricated sample series also exist for `predictive/*`, `sentinel/findings` (`posture_score=95`), `security/compliance-report` (canned framework scores), `strategies/performance`. | live probes | **OPEN** — same class as #3; out of this batch's scope |
| 11 | LOW | FastAPI emits duplicate-operation-ID warnings (`approve_action`, health HEAD handlers), which breaks generated SDK clients. | server startup log | **OPEN** |

Earlier session batches (already committed): unauthenticated cross-tenant injection,
schema bootstrap swallowing failures, webhooks accepting unsigned bodies, missing route
authorisation, WebSocket token verification, in-memory/unsafe privacy erasure, and ~2 400
lint findings.

---

## 3. What is REAL vs CONFIGURED-BUT-UNVERIFIED

**REAL (executed here, evidence above):** ingestion gateway + tenant-scoped credentials,
idempotency (1 accepted / 199 duplicate on a 200-way race), rate limiting (429, no 5xx),
256 KiB payload cap → 413, event read pagination, workflow trigger API, approvals lifecycle
(recommend → reject/approve → 409), agent registry + agent run, lead/usage/audit/analytics
reads, privacy export/erase routes, WebSocket auth, cold boot on SQLite, SDK and dashboard
builds.

**CONFIGURED-BUT-UNVERIFIED (reason):** Postgres persistence (no Postgres in the sandbox —
SQLite only), production Redis (a dev double was used), outbound connectors
(SendGrid/Twilio/HubSpot/Calendly/Stripe/Zendesk — no credentials, mocked in tests), the AI
Universe deliberation service (no network: DNS failure → fallback), Sentinel/IntelX/Futuris
integration handshakes, and the docker-compose deployment (no Docker daemon here).

**Capacity reality (measured, not claimed):** with SQLite and a single uvicorn worker the
ingest path sustains ~93–112 req/s at concurrency 200; p50 ≈ 1.1 s, p95 ≈ 5.3 s, p99 ≈ 6.9 s
at saturation. The rate limiter (1 000/60 s default) is the binding constraint in the
default configuration; with it raised, 20 000/20 000 events were accepted with 0 5xx and flat
RSS over a 90 s soak (10 383 accepted ingestions). This is the honest ceiling of the
development backend, not of a Postgres deployment.

---

## 4. Harness you can re-run

`scripts/pressure_test.py` (new) — live HTTP: baseline latency, throughput at concurrency,
200-way idempotency race, cross-tenant write attacks, anonymous flood, rate-limit burst,
18-case hostile-input battery (oversize/deep-nest/unicode/SQL-injection/null bytes/bad
schemas/malformed JSON/path traversal), paced soak with RSS leak heuristic, and full read-back
consistency. It retries transient transport failures, classifies dropped connections, uses a
per-run event-id nonce, reports `SKIP` instead of pretending, and exits non-zero on any
invariant violation.

`scripts/run_api.py` + `scripts/dev_redis.py` (new) — a fresh clone can now actually boot
(`python scripts/run_api.py`) with no Docker, and the dev Redis double removes the
"needs a real Redis" barrier for local development.

---

## 5. Next five things (prioritised)

1. **Finish the fabrication sweep** (#10): predictive, sentinel posture score, compliance
   report and strategy-performance values are still canned. Either compute them from stored
   state or return `supported: false` with a note.
2. **Move rate limiting and idempotency out of process memory** for multi-worker
   deployments, and add a Postgres-backed capacity run — the measured SQLite ceiling
   (~100 req/s) is a development limit that must not become a production surprise.
3. **Surface AI-Universe fallback provenance at the top level** (#9) — a caller should see
   "decided by deterministic fallback" without reading the audit payload.
4. **Duplicate operation IDs** (#11) — give the duplicate handlers explicit
   `operation_id`s so generated clients work.
5. **Consolidate the remaining global mutable state** (task manager, connector registry,
   action store) behind the database so restarts and horizontal scale do not lose state;
   then re-run the pressure harness with two API workers.

---

## 6. Definition-of-done checklist

- ✅ Tests green (278), lint clean (ruff/flake8/black), typecheck (SDK tsc) and builds (SDK + dashboard) pass.
- ✅ No known secrets in the tree (scan run; the `JWT_SECRET`/`FRIDAY_API_KEY` values used in
  this session are throwaway local values, never committed).
- ✅ No known false doc claims: README §12/§13 corrected, stale "128/128 tests green" removed,
  verified-vs-unverified evidence basis stated.
- ✅ Every fix in this report is proven by a test that fails without it (12 new tests added
  across 4 new/updated files) **and** by a live HTTP run.
- ⚠️ Project is visibly closer to the dream state, but the dream state is not reached:
  items 1–5 above remain, and the capacity figure is a development backend measurement.
