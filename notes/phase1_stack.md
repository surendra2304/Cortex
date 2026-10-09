# Phase 1 — Stack & Dependency Fingerprint

Date: 2026-10-07 · All versions verified by execution in this session unless noted.

## Runtime & toolchain [FACT]

- Python **3.11.2** (sandbox), pinned 3.11 in CI (`.github/workflows/ci.yml`, `deploy.yml`) and `pyproject.toml` (`requires-python = ">=3.11"`). `.python-version` file is garbled (likely UTF-16) — unverified, cosmetic.
- Node **v22.22.3** / npm **10.9.8** (sandbox); CI uses Node 20; dashboard Dockerfile uses `node:20-alpine`.
- Build backend: **hatchling** (`pyproject.toml`), wheel packages = the 12 `packages/*/src/cortex_*` dirs. Lint: **ruff** (line-length 120, select E,F,W,I,B,UP) + **flake8** (`.flake8`); **black** in dev deps but not enforced in CI.
- No `redis-server` binary in the sandbox → `scripts/dev_redis.py`, an in-process RESP double (RESP2).

## Python dependencies [FACT]

`requirements.txt` = **21 packages, every one an unpinned floor** (`>=`): fastapi, uvicorn[standard], pydantic, pydantic-settings, **redis>=5.0.0**, asyncpg, sqlalchemy[asyncio], aiosqlite, alembic, httpx, sendgrid, twilio, hubspot-api-client, stripe, python-jose[cryptography], aiohttp, python-dotenv, prometheus-client, jinja2. Resolved in this session's venv to redis-py **8.1.0** (drift — see Phase 13/14: it breaks the worker against the bundled RESP2 double).

**pip-audit -r requirements.txt → 3 known vulnerabilities in 2 packages [FACT, this session]:**

| Package | Version | Advisory | Detail | Mitigation in this codebase |
| :--- | :--- | :-- | :--- | :--- |
| python-jose | 3.5.0 | CVE-2026-85394 | Incomplete fix for CVE-2024-33663: accepts DER-encoded public keys lacking PEM/SSH prefixes in HMAC init → HS256 forgery if algorithms not restricted | **Mitigated**: `auth.py:169` pins `algorithms=["RS256"]`, `auth.py:183` and `ws_auth.py:87` pin `algorithms=["HS256"]` — no algorithm confusion possible |
| ecdsa | 0.19.2 | PYSEC-2026-1325 (×2) | Minerva timing attack on P-256 via `sign_digest()`; project considers side channels out of scope, no fix planned | Low: jose uses it only for ECDSA verify paths; signing happens provider-side. Still: unpinned floor |

## TypeScript dependencies [FACT]

- Root `package.json` = npm workspaces (`apps/*`, `packages/*`). `package-lock.json` lockfileVersion 3, pins **next 14.2.35**, react 18.3.1, includes 17 platform-specific optional deps (the prior audit's "npm ci cannot install" claim is **not reproducible** — `npm ci` at root and `--workspace=apps/dashboard` both exit 0 this session).
- `npm audit` (dashboard, `--audit-level=high`) → **9 vulnerabilities: 1 critical, 6 high, 2 moderate [FACT, this session]**: next 14.2.35 (critical: image-optimizer AVIF RCE + many RSC/DoS/SSRF/cache-poisoning advisories), braces, chokidar, fast-glob, micromatch, postcss, tailwindcss (high), postcss-nested, postcss-selector-parser (moderate).
  - **Mitigations [FACT]**: `next.config.js` sets `output: 'export'` + `images.unoptimized: true`, and the app is a fully static export with no Server Actions/middleware/rewrites — the server-side Next.js CVE classes (RSC, Server Actions, middleware, rewrites, image optimizer) are not reachable in the shipped artifact. The critical rating is a version-range flag, not a demonstrated exposure. The build-time deps (postcss/tailwind/braces/micromatch) are dev-only.

## Service dependency versions [FACT, live]

FastAPI + uvicorn (ASGI), SQLAlchemy 2.0 async (aiosqlite default / asyncpg for Postgres), Redis (streams + sliding-window rate limit + idempotency), Prometheus client (`/metrics`), python-jose (JWT), httpx (outbound connectors + peer transport), stripe/twilio/sendgrid/hubspot-api-client SDKs, jinja2 (present in requirements; landing page is a static string instead), aiohttp.
