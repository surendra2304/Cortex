# Phase 2 — Architecture Mapping

Date: 2026-10-07 · Diagrams also embedded in REPO_ANALYSIS.md.

## Layer map [FACT]

```
Browser (SDK) ──public key──> FastAPI :8000 (apps/api)
                                   │  ├─ static dashboard export  (GET /)
                                   │  ├─ operator JWT (viewer<operator<admin, friday_system)
                                   │  └─ FRIDAY key (X-Friday-Api-Key, hmac.compare_digest)
                                   ├─ SQLite/Postgres (SQLAlchemy async, 13 tables)
                                   └─ Redis ──XADD──> cortex:events:stream
                                                          │ XREADGROUP
                                                          ▼
                                              cortex_worker (consumer group cortex-worker-group)
                                                          │
                                                          ▼
                                     CognitiveOrchestrator — 10-phase loop
                                     Observe→Contextualize→Understand→Plan→(4a Collaborate)
                                     →Authorize→Execute→Verify→Measure→Learn→Continue
                                                          │
                                     ┌────────┬─────────┴──────┬──────────┐
                                     ▼        ▼                ▼          ▼
                              AgentRegistry  PolicyEngine   ToolBus   connectors
                              (7 agents)     (5 high-impact (Redis    (email/SMS/CRM/
                                             categories)    NX EX     payments/tickets/
                                                            86400)    calendar/webhook)
                                                          │
                                     peers (opt-in HTTP): IntelX · Futuris · Sentinel · AI Universe
```

## Package responsibilities [FACT]

| Package | Role |
| :--- | :--- |
| `cortex_core` | orchestrator (10-phase loop), governed_operations (5-phase exec lifecycle), web_property registry, task_manager, resilience (circuit breakers + self-healing), self_model, models |
| `cortex_event_schema` | ingestion event schema/validation |
| `cortex_agents` | 7 specialist agents (growth, sales, support, reliability, qualification, churn_risk, competitive) + collaboration (handoffs, consensus, verification) |
| `cortex_ai_universe_adapter` | AI deliberation with honest deterministic fallback (NOOP_FALLBACK) |
| `cortex_tool_runtime` | ToolBus: registry, idempotency (Redis SET NX EX 86400), honest verification |
| `cortex_integrations` | 7 outbound connectors (sendgrid, twilio, hubspot, stripe, zendesk, calendly, webhook) + peer clients (intelx/futuris/sentinel via `peer_transport.py`) + CredentialManager (PBKDF2 310k) + DeploymentSecurityGate |
| `cortex_policy_engine` | 5 high-impact categories, approval gates, SecretScrubber, GDPR export/erasure |
| `cortex_workflow_engine` | workflow state machine, lead nurture, security incident, capacity planning |
| `cortex_identity` | identity resolution / identity_links |
| `cortex_analytics` | funnel, cohorts, experiments (two-proportion z-test), attribution, outcomes/strategy learning, NL query, security baseline, traffic telemetry, landing page (static HTML constant) |
| `cortex_intelligence` | exposure monitor, market signals, predictive personalization |
| `cortex_memory` | strategy memory (tenant-scoped) |
| `cortex_upgrade` (top-level) | 23-module hardening layer: policy, toolbus, approval, memory, persistence, runtime_knobs, context_firewall, ws protections, learning, decision, models, memora client/cloud fallback |

## Key architectural invariants [FACT, from code + docstrings + tests]

1. **Tenant identity comes only from the credential** — ingestion derives tenant from the public key; payload tenant claims are rejected unless neutral (`events_router.py:167-202`, NEUTRAL_TENANT_VALUES at :43-46).
2. **Recommendation ≠ authorization** — 5-phase governed operations lifecycle separates observation/recommendation/approval/execution/measurement (`cortex_core/governed_operations.py`); 5 high-impact categories require supervisor approval (`policy_engine`).
3. **Honest fallback** — AI Universe unavailable → deterministic fallback, labeled `NOOP_FALLBACK`/`deterministic_fallback_policy`; never laundered as AI output (`orchestrator.py`, `ai_universe_adapter`).
4. **Honest verification** — ToolBus reports "executed" unless the executor returns `verified:true` (regression tests `tests/unit/test_toolbus_honesty.py`).
5. **No fabricated data** — regression suite `tests/unit/test_no_fabricated_data.py` locks empty-when-empty for audit/usage/analytics.
6. **Bounded collaboration** — handoffs carry no capability and no execution authority; max_rounds/max_agents caps, cycle refusal (`agents/collaboration.py:161-175`).
7. **Self-modification is allow-listed** — 3 runtime knobs, reversible, with rollback + history (`self_model.py:70-113`).

## Notable architecture smells [INFERENCE]

- Two parallel "hardening" stacks: `cortex_upgrade/` (23 modules) and the same concepts re-implemented inside `packages/core` + `apps/api` (e.g. `cortex_upgrade/policy.py` vs `cortex_policy_engine`, `cortex_upgrade/toolbus.py` vs `cortex_tool_runtime`). `tests/upgrade/` (19 files, unittest style) tests the `cortex_upgrade` copy; `tests/unit|integration` test the packages copy. Which one the API actually uses at runtime is per-import (mostly the `packages/*` ones — see Phase 5) — a maintenance and "which policy is real?" hazard.
- `cortex_analytics/outcomes.py:6` imports `from cortex_api.db_models import StrategyPerformanceModel` — a **package importing from the app**, inverting the intended dependency direction (policy_engine does lazy imports to avoid exactly this; analytics does not).
- `apps/dashboard/out/` (committed static export, 17 pages, ~81 tracked files change on rebuild) is served by the API at `/` (`main.py:278-345`) — build artifacts in git.
