# Phase 0 — Orientation & Ground Truth

Date: 2026-10-07 · Analyst: Arena.ai Agent Mode · Branch: `arena/998f44c2-cortex` (session), repo HEAD `83e6f9a`

## What this repository is [FACT]

- `surendra2304/Cortex`, a Python/TypeScript **monorepo** for **CORTEX v2.0.0** (`pyproject.toml:1-3`, hatchling, `name = "cortex-monorepo"`).
- Self-description: an "autonomous web operations intelligence platform" — the governed website/web-app operations specialist of the **FRIDAY** multi-agent ecosystem (`packages/core/src/cortex_core/self_model.py:274-277` self-identifies as "autonomous operational intelligence substrate (FRIDAY is the general OS above it)").
- HEAD commit `83e6f9a7260743166c8477ea6a602929447149c1` = "Merge pull request #1 from surendra2304/arena/01a10cc3-cortex", author Surendra <surendrabtech12321@gmail.com>, 2026-10-07 00:46:04 +0530 (`git log`). The clone is **shallow** (`git rev-parse --is-shallow-repository` → true): exactly 1 commit, 482 objects in 1 pack. No older history is available locally.

## Top-level layout [FACT]

| Path | What it is |
| :--- | :--- |
| `apps/api/src/cortex_api/` | FastAPI service, 20 modules, ~6,901 LOC |
| `apps/worker/src/cortex_worker/` | Redis-stream consumer worker, 168 LOC |
| `apps/dashboard/` | Next.js 14 static-export ops dashboard (17 pages, `src/` ~649 LOC) + **committed build output** `out/` |
| `packages/*/src/cortex_*/` | 12 Python library packages (~10,285 LOC incl. TS SDK `packages/sdk`) |
| `cortex_upgrade/` | 23-module hardening layer (~1,833 LOC) with its own parallel test suite |
| `tests/` | 84 test files, 339 `def test_` (218 sync + 121 async), 343 collected items |
| `scripts/` | run_api.py, dev_redis.py (in-process Redis double), pressure_test.py, validate_diary.py, live-test harnesses |
| `infra/` | alembic (5 versions), k8s, terraform |
| `migrations/001_create_events_and_sessions.sql` | one raw SQL migration |
| `docs/`, `diary/` (10 dated files), `patches/peer_fixes/` (2), `examples/` | documentation & dev history |
| Root meta | `pyproject.toml`, `requirements.txt` (21 pkgs, all `>=` floors), `package.json` (npm workspaces), `Dockerfile`, `docker-compose.yml`, `render.yaml`, `.env.example`, `.github/workflows/{ci,deploy}.yml`, `.flake8` |

## Prior-agent artifacts in the repo root (treated as claims, not truth)

`AUDIT_REPORT.md`, `AGENT_BRAIN_2026-10-06.md`, `CORTEX_DIARY.md`, `PHASE0-2_AUDIT_2026-10-05.md`, `PHASE5_HANDOFF_2026-10-05.md`, `SYSTEM_MANIFEST.md`. These document a prior agent's audit+fix session on branch `arena/01a10cc3-cortex` (merged as PR #1). Their defect lists (fabricated data, missing WS auth, schema bootstrap, etc.) describe the **pre-fix** state; the current HEAD contains the fixes (verified: e.g. `events_router.py:362-393` real tenant-scoped query with offset + 5xx on DB error; `ws_auth.py` verifies tokens; `self_model.py` refuses unobserved claims). Their *quantitative* claims are stale in places: README says 307 tests, `docs/DEPLOYMENT.md` says 128, diary Day 2-4 says 128 — actual now **339 test functions / 343 collected** [FACT, this session].

## Method

Read-before-claim with `path:line` citations; every claim labeled [FACT] (read or executed), [INFERENCE] (reasoned from evidence), [HYPOTHESIS] (unverified guess). Execution over reading: venv built from `requirements.txt`, full pytest, ruff/flake8, pip-audit, npm audit, SDK + dashboard builds, live API + dev-redis boot, live HTTP probes (incl. a cross-tenant IDOR reproduction), worker boot, and the repo's own pressure harness (9/9 PASS). Non-destructive: no source files modified; the one accidental regeneration of the committed `apps/dashboard/out/` was restored with `git checkout` (repo is clean, `git status --porcelain` → empty).
