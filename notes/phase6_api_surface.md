# Phase 6 — API Surface

Date: 2026-10-07 · Counts verified live against the running server (`/openapi.json`).

## Summary [FACT]

- **75 paths** in OpenAPI, 1 WebSocket (`/v1/ws/events`), plus non-schema routes `/`, `/dashboard`, `/dashboard/`, `/docs`.
- Routers registered in `main.py:183+` in an order that prevents route shadowing (prior defect C2 fixed).

## Route groups [FACT, live OpenAPI dump]

| Tag | Paths | Auth | Highlights |
| :--- | :--- | :--- | :--- |
| Event Gateway | 2 | public key | `POST /v1/events`, `POST /v1/events/batch` |
| Public API Gateway | 9 | operator JWT | `GET /v1/leads`, `GET /v1/leads/{id}` ⚠, `GET /v1/visitors/{id}` ⚠, `GET /v1/analytics/{metric}`, `GET /v1/audit/{resource}`, `GET /v1/agents`, `POST /v1/agents/{id}/run`, `POST /v1/identify`, `GET /v1/intelligence/requests`, `GET /v1/workflows` |
| Understand Layer | 14 | operator JWT | leads score, visitors profile, memory, identity resolve, approvals, workflows run, strategies, analytics (funnel/cohorts/attribution), actions approve/reject |
| FRIDAY Integration | 22 | FRIDAY key | `command`, `task`, `collaborate`, `self_model` (+diagnose/modify), `self_healing` (+run), `priority_leads` ⚠, `incidents` ⚠, `connectors/health`, `properties`(+register), `outbound/request`, `market_trends`, `competitive_summary`, `health_summary`, approvals decide, task status/cancel/rollback |
| Production & Observability | 22 | mixed | `/health`, `/health/ready`, `/metrics`, `POST /v1/tenants` ⚠ (returns `operator_jwt_secret` plaintext, `production_router.py:582-592`), `GET /v1/tenant/usage`, `/v1/tenant/settings`, `/connectors` ⚠ (hardcoded HEALTHY), `/v1/sentinel/*`, `/v1/predictive/*`, `/v1/security/*`, `/privacy/export|delete/{visitor_id}`, `/analytics/query`, `/audit/export`, `/experiments`, `/personalization/match` |
| Stripe Webhooks | 1 | signature | `POST /v1/webhooks/stripe` |
| Webhooks | 1 | provider secret | `POST /v1/webhooks/{provider}` ⚠ (missing secret accepted with `signature_verified:false` in dev) |
| Administration | 1 | admin JWT | `POST/GET /v1/api-keys` ⚠ (tenant_id from body, no caller-tenant check, `main.py:215-238`) |
| System | 2 | none | `/`, `/v1/health` |
| Universal Task Protocol | 1 | FRIDAY | `POST /v1/task/execute` |

⚠ = security-relevant, see Phase 10 ledger.

## Auth model [FACT]

- **Operator JWT**: RS256 via OIDC JWKS when configured, else HS256 with `JWT_SECRET`; roles `cortex_viewer < cortex_operator < cortex_admin`, plus `friday_system`; enforced per-route via `require_role` (`auth.py`).
- **FRIDAY**: `X-Friday-Api-Key` compared with `hmac.compare_digest`.
- **Public ingestion**: `X-Cortex-Public-Key` (SHA-256 lookup).
- **WebSocket**: `ws_auth.py` mirrors JWT verification, closes 1008 on failure (regression tests `tests/unit/test_websocket_auth.py`).
- **DEV_AUTH_BYPASS**: non-prod + `MOCK_MODE=true` (default) ⇒ unauthenticated requests become synthetic `cortex_admin`/`tenant_default` (`auth.py:31-44`). The mock token `mock_operator_jwt_token_123` is accepted in dev [FACT, live]. In dev, HS256 with an **empty** `JWT_SECRET` verifies [FACT, live — used for the IDOR reproduction].

## Cross-cutting behavior [FACT, live]

- `/health` → UP (process liveness); `/health/ready` → READY with per-dependency detail (postgres/schema/redis required; ai_universe/sentinel/intelx/futuris may degrade without failing readiness — the fix for prior defect "readiness can never pass").
- `/metrics` → Prometheus text format.
- `GET /` → dashboard HTML for browsers, JSON health for `Accept: application/json` (`main.py:313-338`).
- Ingestion edge cases live-verified: 401 no key / unknown key, 403 tenant mismatch, `{"status":"duplicate"}` on re-ingest, 413 oversized (256 KiB cap), 429 rate limit, batch accepted.
- Pagination: `GET /v1/events?limit&offset` (limit clamped 200, offset stable, DB errors → 5xx) — prior defect fixed (`events_router.py:351-393`).
