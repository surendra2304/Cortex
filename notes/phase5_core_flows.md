# Phase 5 — Core-Flow Deep Reads

Date: 2026-10-07

## 5.1 Ingestion pipeline (`events_router.py`) [FACT]

`POST /v1/events` (single, :186) and `POST /v1/events/batch` (:245):
1. Public key via `X-Cortex-Public-Key` header → SHA-256 lookup in `api_keys`; unknown/inactive → 401; lookup failure → fail-closed 503.
2. **Tenant derived only from the credential** (:196-202); payload tenant rejected unless neutral (`_assert_tenant_authority` :167-181; neutral values :43-46 = `""`, `default`, `tenant_default`, `unknown`, `self`).
3. Redis sliding-window rate limit (1000/60s per key+site) → 429.
4. Dedupe (`EventDedupeStore.claim` + DB IntegrityError backstop) → `{"status":"duplicate"}` (idempotent 200).
5. `EventModel` insert; prod fails closed on DB error (:215, :293).
6. `XADD` to `cortex:events:stream` for the worker (:145-163, :235, :320).
Payload cap 256 KiB → 413; schema validation → 422. Live-verified this session: accepted / duplicate / tenant-mismatch 403 / no-key 401 / batch OK.

## 5.2 Cognitive loop (`packages/core/src/cortex_core/orchestrator.py`) [FACT]

10 phases, executed per event by the worker: **Observe → Contextualize → Understand → Plan → 4a Collaborate → Authorize → Execute → Verify → Measure → Learn → Continue**.
- Plan: deterministic agent first; AI Universe only for AMBIGUOUS/STRATEGIC intents; context firewall sanitizes; honest `NOOP_FALLBACK` when nothing qualifies.
- Collaborate: bounded handoff session seeded with the lead agent's output (`agents/collaboration.py:161-175`, max_rounds/max_agents, cycle refusal, AGENT_ERROR isolation).
- Authorize: PolicyEngine — 5 high-impact categories need approval; DANGEROUS always blocked.
- Execute: ToolBus with Redis `SET NX EX 86400` idempotency; HIGH_IMPACT/DANGEROUS fail closed on Redis error.
- Verify: honest "executed" unless executor returns `verified:true`.
- Learn: redacted audit record + tenant-scoped strategy memory.
- Live-verified: `POST /v1/friday/command` ran the full loop (agent_growth, intent LOW 0.3, NO_ACTION, ai NOOP_FALLBAC… provenance `deterministic_fallback_policy`).
- **Gap [FACT]**: Contextualize resolves VisitorModel/ProfileModel/LeadModel by id **without a tenant filter** (memory read IS tenant-scoped) — same class as the Phase-10 IDOR.

## 5.3 Agents (`packages/agents`) [FACT]

7 specialists, deterministic formulas over real event/profile/lead data: growth, sales, support, reliability, qualification, churn_risk, competitive (`competitive_agent.py` — IntelX battlecards + comparison banner proposals, confidence 0.92 hardcoded). Registry exposes them at `GET /v1/agents`; `POST /v1/agents/{id}/run` executes one. Collaboration adds handoffs/consensus/verification (confidence-weighted, dissent recorded, never averaged away).

## 5.4 Policy engine (`packages/policy_engine`) [FACT]

- 5 high-impact categories (billing, customer comms, production config, content publishing, account permissions per diary Day 9-12); DANGEROUS always blocked.
- Approval queue lifecycle: recommend → approve/reject → terminal (409 on re-decide).
- **Findings [FACT]**: SENSITIVE auto-approved; an explicit approval dict bypasses category checks; mock connector results claim `verified:true`.
- `SecretScrubber` + GDPR export/erasure (see Phase 4).

## 5.5 ToolBus (`packages/tool_runtime`) [FACT]

Registry of tools with capability + side-effect level + auth scope + rate limit + idempotency strategy; execution records carry honest verification. Connectors (7) register tools: email (SendGrid), SMS (Twilio), CRM (HubSpot), payments (Stripe), ticketing (Zendesk), calendar (Calendly), webhook. Mock mode returns `verified:true` fixtures; live mode makes real HTTP calls via httpx with short timeouts.

## 5.6 Self-healing / self-model (`cortex_core/resilience.py`, `self_model.py`, `apps/api/self_healing.py`) [FACT]

- Circuit breakers CLOSED→OPEN→HALF_OPEN (3 consecutive failures or ≥0.6 ratio over ≥5 samples, 15s recovery); HealthRegistry probes; SelfHealingSupervisor (one repair/subsystem/30s cooldown, escalate after 3 attempts); wired subsystems: database, schema, redis, agents, ai_universe + traffic-fed circuits for ingestion/tools.
- SelfModel builds capabilities from registration + **observed** health + real DB counts; unobserved ⇒ `unverified` + explicit gap. Live-verified: `/v1/friday/self_model` reported `tool_execution: unverified` (gap), `ai_universe_deliberation: degraded`, usage counted from DB.
- SelfModificationEngine: allow-list of 3 knobs (self_healing_enabled, self_healing_interval_seconds 1-3600, max_collaboration_rounds 1-5), reversible, history + rollback, re-apply refused.

## 5.7 Workflows, identity, analytics, intelligence, memory [FACT]

- `workflow_engine`: state machine + lead-nurture, security-incident, capacity-planning workflows; runs persisted in `workflow_runs`; trigger API `POST /v1/workflows/{name}/run`.
- `identity`: visitor↔profile↔lead resolution via `identity_links`; `POST /v1/identify`.
- `analytics`: funnel, cohorts, experiments (two-proportion z-test, p<0.05, sticky variant hashing), attribution, outcome tracking with PROVEN/PROBATION/DEMOTED promotion (>60% over n≥20 / <30% over n≥10), NL query (timezone-normalizing), security baseline, traffic telemetry, landing_page (a 797-line static HTML/JS constant — marketing page + cognitive-loop simulator, no Python logic).
- `intelligence`: exposure monitor (attack-surface registry), market signals (IntelX), predictive personalization (Futuris forecasts → proactive actions).
- `memory`: tenant-scoped strategy memory entries (`/v1/memory/{scope}/{scope_id}`).
- Peer integrations (`intelx_client` 393 L, `futuris_client` 342 L, `sentinel_client` 221 L, `sentinel_listener`, `deployment_gate`, `peer_transport`): opt-in HTTP via `*_BASE_URL`; results carry `source: peer|fallback` and `degraded` reasons; read-only by construction (never asks peers to execute); DeploymentSecurityGate blocks CRITICAL / needs-approval HIGH findings.

## 5.8 cortex_upgrade (hardening layer) [FACT]

23 modules (policy, toolbus, approval, memory, persistence, runtime_knobs, context_firewall, learning, decision, models, memora_client/cloud_fallback, …) + `tests/upgrade/` (19 unittest-style files). Parallel to the packages/* implementations — see Phase 13 tech debt.
