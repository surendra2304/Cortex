# Phase 13 — Conventions & Technical Debt

Date: 2026-10-07

## Conventions [FACT]

- **Docstring-first honesty culture**: modules carry long docstrings explaining what was fabricated before and why the current version is honest ("audit defect H7/H8", "this is worse than no self-model"). Defects are referenced by ID (C1-C5, H1-H9, M4…) across code, tests, and root reports.
- Lint: ruff (E,F,W,I,B,UP, line-length 120) + flake8 — both clean this session. No `TODO`/`FIXME`/`HACK`/`XXX` anywhere in apps/packages/cortex_upgrade/scripts/tests [FACT: grep count 0]. No `@deprecated` markers.
- Timezone discipline: `_utcnow()` = `datetime.now(UTC)` everywhere (naive-datetime fixes referenced in patches/peer_fixes).
- Tests: pytest, `tests/conftest.py` shared fixtures (FakeRedis, file-backed SQLite, dependency overrides, autouse DEV_AUTH_BYPASS=False); `tests/upgrade/` in unittest style for the hardening layer.
- Diary discipline: `scripts/validate_diary.py` enforces 51-99 lines / 16-29 bullets per diary file — CI gate.
- Naming: `cortex_*` package dirs, `*_router.py` per API area, `Model` suffix for ORM, `Tool`/`Execution`/`SideEffectLevel` in tool runtime.

## Technical debt [FACT/INFERENCE, ranked]

1. **Unpinned dependency floors** (`requirements.txt`: 21 × `>=`) — already bitten once: redis-py 8.1.0 breaks the worker against the bundled RESP2 double (Phase 9/14). No lockfile for Python (no pip-tools/uv lock, no hashes).
2. **Two parallel hardening stacks**: `cortex_upgrade/` (23 modules + `tests/upgrade/`) vs `packages/*` implementations of the same concepts (policy, toolbus, approval, memory). The API mostly wires the `packages/*` ones; the duplication invites drift ("which policy is real?").
3. **Package→app import inversion**: `cortex_analytics/outcomes.py:6` imports `cortex_api.db_models` (a library importing the app); policy_engine carefully avoids this with lazy imports — the convention is not applied uniformly.
4. **Committed build artifacts**: `apps/dashboard/out/` (17 pages, ~81 files churn per rebuild) tracked in git and served by the API — regenerate-on-deploy would be cleaner; risk of stale exports (the committed export's chunk hashes differ from a fresh build of the same source).
5. **Broken dashboard container**: `next start` vs `output: export` (executed this session) + stale `NEXT_PUBLIC_NEXUS_API_URL` in compose.
6. **Stale naming/docs**: `nexus_*` in compose/k8s/terraform; README 307 tests / DEPLOYMENT.md 128 tests vs 339 actual; `DATABASE_URL` documented but dead (code reads `POSTGRES_DSN`); prior-agent root reports partially stale.
7. **Test isolation defect**: `test_futuris_predictive_api_endpoints` builds `TestClient(app)` without conftest overrides → depends on `data/cortex.db` schema existing (order/environment-dependent; fails on fresh checkout). Also writes into the repo's `data/` dir.
8. **CI name/implementation mismatches**: "Lint" jobs run no linter; security scans are `|| true` (advisory only); `npm install` instead of `npm ci` in CI.
9. **Unauthenticated-by-default dev mode** (`MOCK_MODE=true` ⇒ DEV_AUTH_BYPASS, empty JWT secret) — the single biggest operational footgun (S6).
10. **Cross-tenant read gaps** in public_gateway/friday_router/orchestrator (S1-S3, S9) — the multi-tenant tests don't cover them.
11. **Fabricated-health surface**: static `CONNECTOR_HEALTH` registry served at `/connectors` (S10).
12. **No coverage measurement** (no coverage config/codecov), no Postgres in CI (alembic never exercised end-to-end), no load test in CI (pressure harness is manual).
13. **Minor**: `.python-version` garbled (likely UTF-16); duplicate FastAPI operation IDs; alembic `env.py` reads `DATABASE_URL` while the app reads `POSTGRES_DSN` (works because both are set in compose/render, but it's a second source of truth); `jinja2` in requirements but unused (landing page is a static string).

## What's genuinely good [FACT]

- Regression tests that lock every fixed defect by ID; honest-failure design (fail-closed prod paths, honest fallbacks, no fabricated data); ruff+flake8 clean; 26 s full suite; deterministic agents (no LLM in the loop by default); bounded everything (rounds, agents, payload 256 KiB, rate limits, timeouts on all outbound calls).
