# Phase 3 — Entry Points & Configuration Inventory

Date: 2026-10-07

## Entry points [FACT]

| Entry | Command | Where |
| :--- | :--- | :--- |
| API server (dev) | `python scripts/run_api.py --port 8000` | `scripts/run_api.py` |
| API server (prod/container) | `uvicorn cortex_api.main:app --host 0.0.0.0 --port ${PORT:-8000}` | root `Dockerfile` CMD, `apps/api/Dockerfile` CMD (identical) |
| Worker | `python -m cortex_worker.main` | `apps/worker/Dockerfile` CMD, docker-compose worker service |
| Dashboard (static) | served by the API at `/` and `/dashboard` from `apps/dashboard/out` | `main.py:278-345` (path-traversal-contained, `_safe_dashboard_path`) |
| Dashboard (dev) | `npm run dev` (Next 14) — works | `apps/dashboard/package.json` |
| Dashboard (container) | `npm start` → **`next start` fails: 'does not work with output: export'** [FACT, executed this session] | `apps/dashboard/Dockerfile` CMD — the compose `dashboard` service would crash-loop |
| SDK | tsup build → CJS/ESM/IIFE + d.ts [FACT, built clean] | `packages/sdk` |
| CI | `pytest tests --verbose`, `npm run build` ×2, `pip-audit \|\| true`, `npm audit \|\| true` | `.github/workflows/ci.yml` |
| Deploy | GHCR image build/push (api + worker) on main; Render deploys from `render.yaml` | `.github/workflows/deploy.yml`, `render.yaml` |

Gotcha [FACT]: running the worker (or anything importing `cortex_*`) from a fresh shell needs `PYTHONPATH` covering `apps/*/src` + `packages/*/src` — the Docker images set `ENV PYTHONPATH` (root `Dockerfile`, `apps/api/Dockerfile`, `apps/worker/Dockerfile`), a bare `python -m cortex_worker.main` fails with ModuleNotFoundError.

## Configuration inventory [FACT]

Settings live in `apps/api/src/cortex_api/config.py` (pydantic-settings) + `.env.example`. Notable:

| Variable | Default / behavior | Notes |
| :--- | :--- | --- |
| `APP_ENV` | `development` | `production` or `RENDER=1` disables dev bypass & forces secret checks |
| `MOCK_MODE` | **`true`** | non-prod + MOCK_MODE=true ⇒ `DEV_AUTH_BYPASS` active: unauthenticated requests get a synthetic `cortex_admin`/`tenant_default` identity (`auth.py:31-44,120`) |
| `CORTEX_DEV_AUTH_BYPASS` | unset | explicit override of the bypass |
| `POSTGRES_DSN` | `sqlite+aiosqlite:///./data/cortex.db` | **the variable the code reads**; `DATABASE_URL` is documented in `.env.example` and used by docker-compose/alembic but is dead config for the app (comment in `render.yaml` documents this fix) |
| `REDIS_URL` | `redis://localhost:6379/0` | stream `cortex:events:stream`, group `cortex-worker-group` |
| `JWT_SECRET` | empty in dev | HS256 with **empty secret** verifies in dev [FACT, live: my IDOR exploit token was signed with `""`]; prod fails closed unless ≥32 chars and not in `INSECURE_DEFAULTS` |
| `OIDC_JWKS_URL` / `OIDC_ISSUER` / `OIDC_AUDIENCE` | unset | RS256/JWKS path when configured (`auth.py:169`) |
| `FRIDAY_API_KEY` | — | `X-Friday-Api-Key` header, `hmac.compare_digest` (`auth.py`) |
| `CORTEX_PII_SALT` | **required** for `hash_pii` (raises without it) | `policy_engine/privacy.py:75-84` |
| `RATE_LIMIT_MAX_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS` | 1000 / 60s | per key+site sliding window, Redis; `AtomicSlidingWindow` fallback |
| Connector creds | `SENDGRID_API_KEY`, `TWILIO_ACCOUNT_SID/AUTH_TOKEN/FROM_NUMBER`, `HUBSPOT_API_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `ZENDESK_SUBDOMAIN/API_TOKEN/EMAIL`, `CALENDLY_API_KEY` | absent ⇒ MOCK mode in dev, DISABLED (fail-closed) in prod (`connector_manager.resolve_connector_mode`) |
| Peer URLs | `INTELX_BASE_URL`, `FUTURIS_BASE_URL`, `SENTINEL_BASE_URL`, `AI_UNIVERSE_BASE_URL` | opt-in: unset ⇒ documented deterministic fallback (`peer_transport.py:47-50`) |
| `DASHBOARD_DIR` | auto-detected | overrides static-export location |
| `NEXT_PUBLIC_CORTEX_API_URL`, `NEXT_PUBLIC_OPERATOR_TOKEN` | — | dashboard build-time env; `.env.example` ships `mock_operator_jwt_token_123` as the example operator token |

Committed-credential hygiene [FACT]: no `.env` or key material is tracked (`git ls-files` shows only `.env.example`). But `.env.example` ships literal-looking defaults: `CORTEX_API_KEY=cortex_api`, `FRIDAY_API_KEY=friday_api`, peer keys `intelx_api`/`futuris_api`/`sentinel_api`/`memora_api`/`stratex_api`/`forge_api`/`inference_api`, plus live Render URLs (`https://intelx-mygl.onrender.com` etc.) — example values, but the pattern teaches operators to commit real keys in this slot, and `CORTEX_API_KEY=cortex_api` matches the diary's "master API key standardization" (`CORTEX_DIARY.md` Day 3).
