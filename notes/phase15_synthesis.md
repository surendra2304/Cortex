# Phase 15 — Synthesis

Date: 2026-10-07

## What this repo actually is [FACT]

CORTEX v2.0.0 — a ~6-week-old, actively hardened **autonomous web-operations intelligence platform**: a FastAPI ingestion + operator API, a Redis-stream worker running a 10-phase cognitive loop over 7 deterministic specialist agents, a policy/approval gate for high-impact actions, 7 outbound business connectors, opt-in peer integrations (IntelX/Futuris/Sentinel/AI Universe), a Next.js operator dashboard (static export served by the API), a browser SDK, and a 23-module `cortex_upgrade` hardening layer with its own test suite. It positions itself as the governed web-ops specialist under the FRIDAY multi-agent OS.

## Maturity assessment [INFERENCE]

- **Engineering culture: strong.** Defect-ID-referenced regression tests, honest-failure design (fail-closed prod, honest fallbacks, no fabricated data), clean lint, fast suite, a real pressure harness, a diary CI gate. The prior agent's audit→fix arc visibly improved the code (all sampled prior defects are fixed in HEAD).
- **Security posture: mixed.** The ingestion/auth core is genuinely hardened (credential-derived tenancy, idempotency, rate limiting, RBAC, WS auth, prod secret checks — all live-verified). But the **read APIs have systematic cross-tenant gaps** (S1-S3, S9: visitors/leads/priority_leads/incidents/orchestrator-contextualize), `POST /v1/api-keys` lets any tenant admin mint keys for any tenant (S5), and dev mode is unauthenticated-admin by default (S6). Multi-tenant tests cover only 2 of the affected surfaces. **The IDOR is live-confirmed and production-reachable.**
- **Operational readiness: partial.** Dev/zero-config path works (SQLite + dev key + static dashboard). Production path is plausible but unexercised here (no Postgres/Redis/Docker in sandbox); render.yaml runs free-tier SQLite (ephemeral data); the dashboard container CMD is broken; compose/k8s/terraform carry stale `nexus_*` naming; the worker breaks against the bundled Redis double under the unpinned redis-py 8.x.
- **Maintenance risk: moderate.** Unpinned Python deps (already bitten once), duplicated hardening stacks, package→app import inversion, committed build artifacts, stale docs, CI lint/scan jobs that don't do what their names say.

## Top risks (ranked) [INFERENCE from Phase 10]

1. **S1 cross-tenant IDOR** on `GET /v1/visitors/{id}` / `GET /v1/leads/{id}` (live-confirmed PII exposure) — fix: tenant filter + regression test.
2. **S6 dev-auth default** — any `APP_ENV != production` deployment is unauthenticated admin; make bypass opt-in, never default.
3. **S2/S3 friday_router** cross-tenant PII (`priority_leads` emails, `incidents` raw_data).
4. **S5 api-keys** cross-tenant minting + **S9** orchestrator contextualize.
5. **Dependency drift** (unpinned floors; redis-py 8.x vs bundled double; python-jose/ecdsa advisories; 9 npm advisories).
6. **Fabricated-health surface** (`/connectors` static HEALTHY) — operators can be misled during an outage.
7. **Ops**: broken dashboard Dockerfile; free-tier SQLite on Render; stale infra naming; no coverage/load gates in CI.

## Recommendations (short) [INFERENCE]

1. Add `tenant_id == auth.tenant` filters to the four unscoped read paths + multi-tenant regression tests for every `/v1/visitors`, `/v1/leads`, `/v1/friday/*` read endpoint.
2. Make `DEV_AUTH_BYPASS` opt-in (`CORTEX_DEV_AUTH_BYPASS=true`), require non-empty `JWT_SECRET` whenever the API is network-reachable, and refuse to start in dev mode on a public bind address.
3. Pin Python deps (lockfile + hashes) — at minimum `redis>=5,<8` until the worker is verified RESP3-clean, and `python-jose>=3.5.1`/`ecdsa` review; make `pip-audit`/`npm audit` blocking in CI.
4. Fix the dashboard Dockerfile (`npx serve out` or drop the service; the API already serves the export) and the compose env var name.
5. Replace the static `CONNECTOR_HEALTH` at `/connectors` with `ConnectorManager.check_all()` output (or label it "configured connectors").
6. Delete `apps/dashboard/out/` from git; build it in CI/deploy. Refresh README/DEPLOYMENT test counts and `nexus_*` names.
7. Fix `test_futuris_predictive_api_endpoints` to use the conftest overrides (or a temp DB) so the suite is order-independent on fresh checkouts.
8. De-duplicate `cortex_upgrade` vs `packages/*` (pick one policy/toolbus implementation) or document which is authoritative at runtime.

## Self-check (15 questions) — condensed answers

1. Did I run the tests? Yes — 339/1/3, failure root-caused. 2. Did I boot the API? Yes, live probes incl. IDOR. 3. Are claims cited? Yes, path:line + labels. 4. Facts vs inference separated? Yes. 5. Secrets flagged? Yes — none tracked; `.env.example` defaults flagged (S15). 6. Coverage honest? Yes — see REPO_ANALYSIS.md self-assessment. 7. Non-destructive? Yes — tree clean, out/ restored. 8. Nothing pushed/committed? Correct. 9. Stale prior claims identified? Yes (test counts, npm ci, nexus_*, DATABASE_URL). 10. Worker verified? Yes — boots, broken vs double, root-caused. 11. Frontend verified? Yes — builds; container CMD broken. 12. Deps audited? Yes — pip-audit + npm audit with mitigations. 13. Performance measured? Yes — 9/9 harness + timings. 14. Git archaeology? Shallow, 1 merge commit, diary is the history. 15. Deliverables written? `REPO_ANALYSIS.md` + `notes/phase0..15`.
