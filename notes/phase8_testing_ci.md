# Phase 8 — Testing & CI

Date: 2026-10-07

## Test suite [FACT, executed]

- `pytest tests -q` → **339 passed, 1 failed, 3 skipped in 26.30s** (343 collected).
- Layout: `tests/unit/` 45 files / 248 test funcs · `tests/integration/` 19 files / 36 · `tests/upgrade/` 19 files / 37 (unittest.TestCase style, targets `cortex_upgrade`) · `tests/test_prompt9_cortex.py` 18 (governed-operations invariant suite). Total **339 `def test_`** (218 sync + 121 async), 1 parametrize expansion → 343 items.
- `tests/conftest.py`: real **file-backed SQLite** + **FakeRedis** + FastAPI dependency overrides; an autouse fixture forces `DEV_AUTH_BYPASS=False`; fixtures provision keys, auth headers, event payloads.
- **The 1 failure**: `tests/unit/test_futuris_predictive_operations.py::test_futuris_predictive_api_endpoints` — `sqlite3.OperationalError: no such table: events`. It builds `TestClient(app)` **without** the conftest overrides, so it hits the module-level engine at repo `data/cortex.db`, which is empty on a fresh checkout. Proven order/environment-dependent this session: passes after the API has booted once (schema created), fails again after `rm data/cortex.db`. Not a code regression; a test-isolation defect (and it writes into the repo's `data/` directory).
- 3 skipped: optional-dependency / environment-gated tests (exact markers: not enumerated this session — minor gap).
- Quality spot-check [FACT]: regression suites are behavior-locked with docstrings naming the audit defect they guard (`test_ingestion_security.py` C1/C5/H3, `test_websocket_auth.py` C3, `test_toolbus_honesty.py` H7, `test_no_fabricated_data.py` H8, `test_auth_and_rbac.py` role matrix). 5 files sampled in depth — high quality, no placeholder tests found.

## Lint/format [FACT, executed]

- `ruff check apps packages cortex_upgrade scripts tests` → **All checks passed** (config: line-length 120, select E,F,W,I,B,UP).
- `flake8` over the same targets → **clean**.
- `black` is a dev dependency but not enforced in CI.

## CI (`.github/workflows/ci.yml`, `deploy.yml`) [FACT]

- `ci.yml` job "Python Lint, Invariant & Unit Tests": installs `pip install . pytest pytest-asyncio pytest-mock flake8 respx httpx`, runs `python scripts/validate_diary.py` then `pytest tests --verbose`. **No ruff/flake8 step despite the job name** [FACT — name/implementation mismatch].
- `ci.yml` "TypeScript Build & Lint": `npm install` + `npm run build` for SDK and dashboard (no `npm ci`, no lint step despite the name).
- `ci.yml` "Security Vulnerability Scan": `pip-audit || true` and `npm audit --audit-level=high || true` — **both non-blocking**: known CVEs never fail CI [FACT]. This session's scans found 3 Python + 9 Node advisories (Phase 1).
- `deploy.yml`: on main — test job (same pytest + diary gate), then build-and-push GHCR images `…-api` and `…-worker` from `apps/api/Dockerfile` / `apps/worker/Dockerfile`; comment notes Render deploys from `render.yaml` (the workflow is not the production rollout).
- `scripts/validate_diary.py` is a real CI gate: diary files must be 51-99 lines with 16-29 summary bullets (documentation-size discipline from the diary convention).

## Verdict [INFERENCE]

Test culture is unusually good for a repo this size (regression-locked invariants, honest-failure tests, ~26 s full suite). Gaps: the order-dependent futuris test, no lint actually running in CI despite the names, security scans advisory-only, no coverage measurement anywhere (no coverage config, no codecov).
