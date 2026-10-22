# CORTEX Test Infrastructure & Opaque-Box Testing Framework

## 1. Overview & Architectural Principles

The Cortex Testing Infrastructure implements an **Opaque-Box (Black-Box) Testing Framework** designed for enterprise-grade reliability, hermetic execution, and deterministic CI/CD validation. 

In accordance with **R4 (Bulletproof Testing & High Coverage)** and the **17-Feature Project Architecture (PROJECT.md)**, testing validates external observable behaviors, HTTP/WebSocket interface contracts, schema enforcement, resilience policies, and system configuration without relying on fragile internal implementation details.

### Core Testing Invariants
1. **100% Hermetic & Offline**: Zero network sockets are opened to external providers or unmocked networks during test runs. All peer services (IntelX, Futuris, Memora, Sentinel, AI Universe) are mocked with authoritative payload schemas.
2. **Deterministic & Fast**: Entire test suite executes in < 15 seconds without sleep races or flakiness.
3. **Multi-Tenant & Security-Enforced**: Real SQLite WAL-mode sessions and fake Redis instances validate tenant boundary enforcement, RBAC, and zero secret leakage.
4. **Authoritative Output Derivation**: Every test assertion is derived strictly from `ORIGINAL_REQUEST.md`, `PROJECT.md`, and OpenAPI specifications.

---

## 2. Test Suite Architecture: 4-Tier Hierarchy

The test suite is structured across four distinct tiers of validation:

```
tests/e2e/
├── test_e2e_tier1.py  # Tier 1: Feature Coverage (>=5 tests per feature for F1-F17; >=85 tests)
├── test_e2e_tier2.py  # Tier 2: Boundary & Corner Cases (>=5 tests per feature for F1-F17; >=85 tests)
├── test_e2e_tier3.py  # Tier 3: Cross-Feature Combinations (Pairwise & System Interactions)
└── test_e2e_tier4.py  # Tier 4: Real-World Scenarios (End-to-End Operational Workflows)
```

### Tier Breakdown

| Tier | Focus | Scope | Volume |
|------|-------|-------|--------|
| **Tier 1: Feature Coverage** | Happy path and baseline functional contracts for every feature | Features F1 through F17 | >= 85 tests (>= 5 per feature) |
| **Tier 2: Boundary & Corner Cases** | Edge cases, extreme payloads, malformed inputs, timeouts, boundary states | Features F1 through F17 | >= 85 tests (>= 5 per feature) |
| **Tier 3: Cross-Feature Combinations** | Subsystem interoperability, circuit breakers + fallbacks, auth + caching, probes + SPA | Feature Pairs & Triads | >= 10 tests |
| **Tier 4: Real-World Scenarios** | End-to-end task decomposition, multi-phase cognitive loop, peer failure recovery | Full System Workflows | >= 7 tests |

---

## 3. Feature Mapping Matrix (F1 – F17)

Every feature defined in `PROJECT.md` is covered across all tiers:

| Feature ID | Feature Name | Primary Contract / Interface | Tier 1 Happy Paths | Tier 2 Boundaries |
|------------|--------------|------------------------------|--------------------|-------------------|
| **F1** | Non-blocking Async Network Migration | `httpx.AsyncClient`, `memora_cloud_fallback.arequest`, `self_healing.probe_ai_universe` | Async client execution, async getaddrinfo, non-blocking HTTP requests | Connection timeout, DNS failure, empty response, connection refused |
| **F2** | Connection Pooling | `get_shared_client()`, connection limits (20 keepalive, 50 max) | Shared client reuse, persistent connection limits, graceful close | Burst requests, pool saturation, client reopening after close |
| **F3** | Circuit Breakers & Backoff with Jitter | `SubsystemCircuit`, `PeerTransport`, exponential backoff | Circuit CLOSED execution, success tracking, fallback invocation | Threshold tripping (OPEN), fast-fail on OPEN, half-open probe recovery |
| **F4** | SQLite WAL Mode & Busy Timeout | `PRAGMA journal_mode=WAL;`, `PRAGMA busy_timeout=5000;` | Connect event hook, WAL mode verification, concurrent transactions | High-contention concurrency, busy timeout handling, lock clearing |
| **F5** | Thread-Safe In-Memory Cache | `TTLCache[K, V]`, TTL expiry, LRU eviction | Set, get, size, delete, clear operations | Expiry boundary, maxsize eviction, zero/negative TTL, multithreaded contention |
| **F6** | Probes Standardization | `GET /health`, `GET /ready`, `GET /health/ready`, `GET /status` | Liveness 200, Readiness 200 (db+redis UP), Status 200 with uptime | Database DOWN during ready, Redis DOWN, HEAD requests, rapid polling |
| **F7** | Route Unmasking in SPA Catch-All | `serve_static_or_spa` prefix exclusions | `/ready`, `/status`, `/plan`, `/decompose`, `/execute` bypass SPA | Deep nested paths, query string unmasking, percent-encoded traversal |
| **F8** | Strict Pydantic Schemas | `CognitivePlanRequest`, `TaskDecompositionRequest`, models | Valid plan, valid decomposition, execution envelope | Max subtasks boundaries (1, 20), empty goal, missing fields, invalid types |
| **F9** | Standardized Error Envelope | Custom exception handlers (`HTTPException`, `RequestValidationError`) | 400, 401, 403, 404, 422 standard envelope structure | Error code consistency, detail propagation, backwards compatibility |
| **F10** | Port Configuration & Dynamic Healthcheck | `PORT` env var, `Settings.port`, Dockerfile healthcheck | Default 8000, custom port env override, settings exposure | Invalid port strings, empty strings, boundary ports (1024-65535) |
| **F11** | Startup Env Validation | `validate_production_secrets`, `Settings` validation | Dev mode default pass, valid production keys pass | Insecure defaults rejection, short secrets (<32 chars) rejection, fail fast |
| **F12** | Container Security & Clean Signal Handling | Root & sub-Dockerfiles, non-root `appuser` (1000), `tini` | Dockerfile non-root spec, uvicorn graceful shutdown flag, tini entrypoint | SIGTERM signal handler, 5-second deadline enforcement, data dir ownership |
| **F13** | Zero Secret/Stack Leakage | Error handlers, logging sanitization, header redaction | Clean error envelopes without traces, masked API key logs | Exception traceback masking, credential omission in 422/500 responses |
| **F14** | Comprehensive Testing & Mocking | Hermetic pytest fixtures, `FakeRedis`, mocked peer transport | 100% test pass rate, mocked network isolation, clean execution | Zero unmocked socket calls, warning elimination, reproducible seed |
| **F15** | CI/CD Workflow Verification | `.github/workflows/ci.yml` | Lint job, test job, docker build job, security scan step | Action versions, trigger branches, fail-fast step ordering |
| **F16** | Documentation Overhaul | `README.md`, `.env.example` | Mermaid diagram presence, curl contract specs, env var table | Default env values, contract schema sync, architecture completeness |
| **F17** | Git Synchronization | Repo cleanliness, commit conventions, `.gitignore` rules | Conventional commit format, git status tracking, gitignore rules | Ignored `.env` and `.db`, clean tree verification, no untracked secrets |

---

## 4. Test Infrastructure Components & Fixtures

### 4.1 FastAPI TestClient & Lifespan Isolation
Tests use FastAPI's `TestClient` initialized against `cortex_api.main.app`. To prevent background loops or unmocked resources from interfering:
- `get_db_session` is overridden with an in-memory/isolated SQLite session factory.
- `get_redis_client` is overridden with `FakeRedis`.
- `app.dependency_overrides` is cleanly reset after every test via pytest autouse fixture.

### 4.2 Mocking Peer Transports & External Sockets
- All peer calls through `PeerTransport` use in-memory stubs or mocked `httpx.AsyncClient`.
- DNS resolution in `self_healing.py` is tested using mocked event loops or loopback addresses.
- Cloud Memora fallback is exercised with custom transport adapters returning structured responses (`cloud: True`).

### 4.3 Concurrency & Lock Testing
- SQLite WAL mode and busy timeout are verified using real SQLite database files with multi-threaded concurrent connection workers to confirm non-blocking reads during writes.
- Thread-safe `TTLCache` is stress-tested with `ThreadPoolExecutor` workers performing concurrent insertions, reads, and evictions.

---

## 5. Test Runner & Verification Commands

To run the entire test suite or individual tiers:

```bash
# Run all E2E test tiers
python -m pytest tests/e2e -v

# Run individual tiers
python -m pytest tests/e2e/test_e2e_tier1.py -v
python -m pytest tests/e2e/test_e2e_tier2.py -v
python -m pytest tests/e2e/test_e2e_tier3.py -v
python -m pytest tests/e2e/test_e2e_tier4.py -v

# Run full project suite (unit, integration, upgrade, e2e)
python -m pytest tests -v
```

---

## 6. Flakiness & Non-Determinism Control

- **Timeouts**: Fixed mock delays instead of real wall-clock sleeps whenever testing backoff logic.
- **Clock**: Monotonic clock simulation for TTL cache testing where instantaneous expiration is tested.
- **Portability**: All path operations utilize `cortex_upgrade.paths` for CWD-independent workspace root resolution across Windows and Linux.
