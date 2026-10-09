# Phase 11 — Performance

Date: 2026-10-07 · Environment: sandbox, SQLite (`data/cortex.db`), dev-redis double, uvicorn single process, API on 127.0.0.1:8000.

## Measured this session [FACT, live pressure harness `scripts/pressure_test.py`]

Run: `--concurrency 50 --events 500 --soak-seconds 10` against the live API → **9/9 scenarios PASS** (exit 0), 40 s wall:

| Scenario | Result |
| :--- | :--- |
| baseline latency | `/v1/health` ×5: mean 1.9 ms, p50 1.8 ms, p99 2.3 ms |
| idempotency race | 200 concurrent identical event_ids → **accepted=1, duplicate=199** |
| tenant isolation | 200 cross-tenant writes → 200×403 |
| unauthenticated flood | 300 anonymous writes → 300×401 |
| rate limit | burst 1120 vs configured 1000/60 s → 1000×200, **120×429, 0 5xx** |
| hostile input | 18 adversarial requests (oversized, deep-nested 80 levels, unicode, injection) → **0 5xx, 0 transport failures** |
| throughput | 500 events @ concurrency 50 → **95-111 req/s**, p50 ≈ 315 ms, p95 ≈ 1.4 s, p99 ≈ 2.1 s, 0 5xx, 0 dropped, all accepted |
| sustained soak | 10 s @ concurrency 16, ~13 rps paced → 149 requests, 130 accepted (rest 422/200), 0 5xx, 0 dropped |
| consistency | 630 accepted = **630 readable back**, 0 missing (offset-paged) |

Notes: throughput p95 ≈ 1.4 s under 50-way concurrency on SQLite + in-process Redis double is **not production-representative** [INFERENCE] (single uvicorn worker, SQLite file, dev double). The harness's consistency scenario reads `/v1/events` with the JWT's tenant — the operator JWT must match the load tenant or the read-back sees 0 rows (harness/operator mismatch I hit and fixed by minting a `tenant_load` JWT; not an API defect — the endpoint is correctly tenant-scoped, `events_router.py:369-370`).

## Prior-agent claims (not re-run at their scale) [from PHASE5_HANDOFF_2026-10-05.md]

- `pressure_test.py --concurrency 200 --events 5000 --soak-seconds 60` → "9/9 PASS"; capacity config (`RATE_LIMIT_MAX_REQUESTS=100000`) 20 000/20 000 accepted, 0 5xx, RSS +0.1 %; independent sqlite read-back 30 391 rows, 0 duplicate ids. Same environment caveats (dev double, SQLite). Consistent with this session's smaller run — plausible, not re-verified at that scale.

## Other measured timings [FACT, this session]

- Full pytest suite: **26.3 s** (343 tests).
- Dashboard `npm run build`: **~26 s** (17 static pages).
- SDK `npm run build`: seconds (tsup CJS/ESM/IIFE + d.ts).
- API cold boot (schema create + dev key provisioning): seconds (observed during restarts).

## Structural performance notes [FACT/INFERENCE]

- Async SQLAlchemy throughout; SQLite default (aiosqlite) — fine for dev/small tenants, a ceiling for write concurrency [INFERENCE]; Postgres supported via asyncpg.
- Redis sliding window per key+site with atomic fallback; stream fan-out to one consumer group (single worker group; horizontal worker scaling possible via the group).
- Idempotency via Redis `SET NX EX 86400` — one round trip per tool execution; dedupe store claim per event.
- No caching layer for reads (every operator read hits the DB) [FACT: routers query SQLAlchemy directly]; `/v1/events` pages of 200.
- No DB indexes declared beyond PKs/ uniques in `db_models.py` [FACT, from model definitions] — tenant_id-scoped queries on `events` will full-scan at volume [INFERENCE — worth verifying with EXPLAIN at scale; alembic versions may add indexes, not verified line-by-line].
- Dashboard: static export, ~87-116 kB first load JS/page — acceptable; 13 stub pages share one component.
