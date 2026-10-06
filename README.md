# CORTEX — Autonomous Website & Web App Operations Intelligence

## 1. Definition
CORTEX is a standalone autonomous operations platform for an existing website or web application. It is not a website builder or deployment platform. After integration, CORTEX observes digital activity, understands what is happening, reasons over the state of the property, executes approved actions, measures outcomes, and continuously improves operations.

---

## 2. What CORTEX IS / IS NOT

| What CORTEX IS | What CORTEX IS NOT |
| :--- | :--- |
| **Autonomous Operations Platform** for live digital properties | **Not a website builder** (Wix, Webflow, WordPress) |
| **Unified Intelligence Layer** (events, visitors, leads, telemetry) | **Not a hosting or deployment provider** (Vercel, AWS) |
| **Agent Runtime with Governed Tools** (human-in-the-loop policies) | **Not a simple passive analytics dashboard** (GA4, Mixpanel) |
| **Multi-Agent Orchestrator** (Growth, Sales, Support, Reliability, Competitive) | **Not a fixed three-agent demo script** |
| **AI Universe Intelligence Consumer** (structured cognitive engine) | **Not an AI Universe replacement** |
| **Specialist Operator Capability** consumable by FRIDAY OS | **Not a FRIDAY OS duplicate or clone** |

---

## 3. Core Product Promise
> *"Connect CORTEX to an existing website or web app once, give it the required permissions and integrations, and it becomes an intelligent operations layer that monitors health, captures and qualifies intent, coordinates support, orchestrates growth experiments, routes high-value opportunities, and continuously optimizes digital operations under strict policy controls."*

---

## 4. Design Principles
1. **Autonomy with Boundaries**: Agents can act autonomously within strictly defined policy constraints; high-impact mutations require operator approval.
2. **AI-First, Not AI-Only**: Deterministic logic handles standard routing; AI Universe deliberation is reserved for ambiguous or strategic goals.
3. **Provider Independence**: Pluggable integrations (SendGrid, Twilio, HubSpot, Stripe, Zendesk, Calendly, Sentinel, IntelX, Futuris) behind the Universal Tool Contract.
4. **Everything is an Event**: All telemetry, user actions, system signals, and agent decisions flow through canonical event schemas.
5. **Everything is Auditable**: Immutable audit records for every action, decision, approval, and state mutation.
6. **Composability**: Modular architecture allowing independent scaling of API, background workers, and dashboard.
7. **Human Control**: Comprehensive human-in-the-loop approval queues with safe-by-default auto-expiry.
8. **Privacy by Design**: Strict consent gating; pseudonymous visitors are never stitched into profiles without explicit consent.
9. **Graceful Degradation**: Deterministic fallbacks ensure zero downtime even if AI providers or external APIs become unavailable.

---

## 5. System Context & Peer Separation
```
+-------------------------------------------------------------------+
|                        AI UNIVERSE                                |
|         (Foundation Intelligence & Multi-Agent Deliberation)      |
+---------------------------------+---------------------------------+
                                  |
               +------------------+------------------+
               |                                     |
               v                                     v
+-----------------------------+       +-----------------------------+
|           CORTEX            |       |           FRIDAY            |
| (Web Operations Specialist) |<=====>|   (General OS Operator)     |
+-----------------------------+       +-----------------------------+
```

### Critical Separation Rule
> **"CORTEX should not become a hidden FRIDAY module. AI Universe should not become a hidden CORTEX module. Each repository must be independently runnable, testable, and deployable."**

---

## 6. The 10-Phase Cognitive Loop
Every ingested event is processed through a strict closed-loop cognitive state machine:
```
1. Observe      --> Ingest canonical EventSchema via SDK/Webhooks
2. Contextualize--> Assemble session, visitor profile, history, and site metrics
3. Understand   --> Classify intent, score leads, detect drop-off anomalies
4. Plan         --> Specialist agents propose actions with rationale and confidence
5. Authorize    --> Policy Engine evaluates side effects (READ/SENSITIVE/HIGH_IMPACT)
6. Execute      --> ToolBus executes tools with idempotency & rate limits
7. Verify       --> Assert expected outcome criteria were met
8. Measure      --> Track downstream events in a 48h attribution window
9. Learn        --> Update strategy win-rates (Auto-promote >60%, Auto-demote <30%)
10. Continue    --> Yield control or chain downstream workflow transitions
```

---

## 7. Capability Surface
- **Visitor & Behavior Intelligence**: SDK auto-capture, session replay signals, exit intent, rage-click detection.
- **Identity & Profiles**: Resolution graph linking anonymous IDs to leads and customers with strict consent controls.
- **Lead & Revenue Operations**: Explainable 4-factor scoring (Behavior 40%, Firmographic 30%, Engagement 20%, Source 10%).
- **Communication & CRM**: Automated email sequences (SendGrid), SMS/Voice (Twilio), CRM synchronization (HubSpot).
- **Calendar & Scheduling**: Dynamic sales rep availability checks and demo bookings (Calendly / Google Calendar).
- **Support & Ticketing**: Automated triage and ticket escalation (Zendesk / Intercom).
- **Website Health & Reliability**: P99 latency tracking, error spike detection, and incident root-cause hypotheses.
- **A/B Experimentation**: Two-proportion z-test statistical significance (p < 0.05 / z >= 1.96) with sticky variant hashing.
- **Sentinel Security & DevSecOps**: Continuous vulnerability ingestion, attack surface exposure mapping, and pre-flight deployment gates.
- **IntelX Competitive & Market Intelligence**: Automated feature gap extraction, competitive sales battlecards, and market trend tracking.
- **Futuris Predictive Web Operations**: 24h traffic forecasting with 95% CI, capacity auto-scaling, and conversion drop mitigation.
- **Governance & Security**: OIDC RS256 JWT RBAC, Prometheus metrics (`/metrics`), and distributed `trace_id` correlation.
- **Multi-Agent Collaboration**: specialists request help from each other (`HandoffRequest`), peers receive the accumulated findings blackboard, and every session closes with an explicit consensus that names dissent instead of averaging it away. Bounded on purpose: one visit per agent, a hard round cap, cycles refused, and one failing agent recorded as `AGENT_ERROR` rather than sinking the session. Lives in `packages/agents/src/cortex_agents/collaboration.py` and runs inside the loop as phase `4a.Collaborate`.
- **Self-Healing**: per-subsystem circuit breakers (3 consecutive failures or a 0.6 failure ratio over 5+ samples), real probes, bounded repairs with a cooldown, escalation when repairs do not work, and a background loop whose cadence and on/off switch are runtime knobs. A repair only counts when a follow-up probe verifies it — health is measured, never asserted. Lives in `packages/core/src/cortex_core/resilience.py` and `apps/api/src/cortex_api/self_healing.py`.
- **Self-Model ("self brain")**: reports capabilities from observed evidence only (`operational` / `degraded` / `unverified` + explicit gaps), diagnoses its own weak spots, and can change a small allow-list of low-impact, reversible runtime knobs — with refusal reasons, conflict detection (409) and rollback. Nothing outside the allow-list, no environment or file writes. Lives in `packages/core/src/cortex_core/self_model.py`.

---

## 8. Architecture Overview
```
+---------------------------------------------------------------------------------------+
|                                  CONNECTED PROPERTY                                   |
|                        (Web App, Marketing Site, E-Commerce)                          |
+-------------------------------------------+-------------------------------------------+
                                            | (Browser SDK / Server API / Webhooks)
                                            v
+---------------------------------------------------------------------------------------+
|                                 INGESTION GATEWAY                                     |
|             (FastAPI /v1/events, /v1/events/batch, Sliding-Window Rate Limiting)      |
+---------------------+---------------------------------------------+-------------------+
                      |                                             |
                      v                                             v
        +---------------------------+                 +---------------------------+
        |   POSTGRESQL EVENT STORE  |                 |     REDIS EVENT STREAM    |
        | (Partitioned, Indexed DB) |                 | (xadd / Consumer Groups)  |
        +---------------------------+                 +-------------+-------------+
                                                                    |
                                                                    v
+-------------------------------------------------------------------+-------------------+
|                                     CORTEX CORE WORKER                                |
|                                                                                       |
|   +-------------------+     +---------------------+     +-------------------------+   |
|   |  Context Engine   | --> | Dynamic Agents (7+) | --> |      Policy Engine      |   |
|   +-------------------+     +----------+----------+     +------------+------------+   |
|                                        |                             |                |
|                                        v                             v                |
|                             +--------------------+       +-----------------------+    |
|                             | AI Universe Client |       | Universal Tool Bus    |    |
|                             | (FAST/REVIEW/DEBATE|       | (SendGrid, Stripe...) |    |
|                             +--------------------+       +-----------+-----------+    |
|                                                                      |                |
|                                                                      v                |
|   +------------------------------------------------------------------+------------+   |
|   |         Outcome Measurement & Strategy Learning (PROVEN / DEMOTED)           |   |
|   +-------------------------------------------------------------------------------+   |
+---------------------------------------------------------------------------------------+
```

---

## 9. AI Universe Integration & Routing

| Request Classification | AI Deliberation Mode | Latency Budget | Action & Use Case |
| :--- | :--- | :--- | :--- |
| **TRIVIAL** | *None (Deterministic)* | < 50ms | Page views, clicks, heartbeats, score refreshes |
| **ROUTINE** | `FAST` (Single Agent) | ~3,000ms | Email copy optimization, minor notifications |
| **AMBIGUOUS** | `REVIEW` (Agent + Critic) | ~8,000ms | Unclear lead qualification, low confidence triggers |
| **STRATEGIC** | `DEBATE` (Adversarial Multi-Round)| ~20,000ms | Funnel drop diagnosis, high-risk churn intervention |

---

## 10. Integration Tiers

| Tier | Capabilities Included | Integration Requirements |
| :--- | :--- | :--- |
| **Lite** | Telemetry capture, visitor tracking, funnel analysis | Browser SDK script tag |
| **Standard** | Identity resolution, lead scoring, context assembly | SDK + Server-side Event API |
| **Advanced** | CRM sync, automated email, SMS, payments webhooks | Standard + Connector API Keys |
| **Autonomous** | Automated closed-loop actions, A/B experiments, workflows | Advanced + Action Execution Policies |
| **FRIDAY Connected** | Bidirectional OS capability delegation and summary sync | Autonomous + FRIDAY Service API Key |

---

## 11. Technology Stack
- **API & Backend**: Python 3.11, FastAPI, SQLAlchemy 2.0 (asyncio), Pydantic v2
- **Worker & Storage**: Redis Streams (aioredis), PostgreSQL 15 (asyncpg), Prometheus metrics
- **Frontend & Dashboard**: Next.js 14, React 18, TailwindCSS, TypeScript, SWR, Axios
- **Browser SDK**: TypeScript standalone browser bundle with session & consent management
- **Containerization**: Multi-stage production Dockerfiles, Docker Compose, GitHub Actions CI/CD

---

## 12. Subsystem Architecture Status

| Operational Subsystem | Core Capabilities | Status |
| :--- | :--- | :--- |
| **Ingestion Gateway & Event Store** | TypeScript SDK, Webhooks, Partitioned Postgres, Redis Streams | ✅ Operational |
| **Understand Intelligence Layer** | Identity Resolution Graph, 4-Factor Lead Scoring, Funnel Anomalies | ✅ Operational |
| **Specialist Agent Ecosystem** | 7 Input-Driven Specialist Agents (Growth, Sales, Support, Reliability, Competitive...) | ✅ Operational |
| **AI Universe Deliberation Engine** | FAST, REVIEW, DEBATE Deliberation Modes & Deterministic Fallbacks | ✅ Operational |
| **Action & Workflow Engine** | Operational Workflows, Human-in-the-Loop Approvals | ✅ Operational |
| **Universal Tool & Connector Bus** | Connectors (SendGrid, Twilio, HubSpot, Calendly, Stripe, Zendesk...) | ✅ Operational |
| **Closed-Loop Learning Layer** | 48h Outcome Attribution, Strategy Promotion (>60%) & Demotion (<30%) | ✅ Operational |
| **A/B Testing & Personalization** | Two-Proportion Z-Test Significance, Sticky Hashing, Dynamic Rules | ✅ Operational |
| **FRIDAY Integration Bridge** | Bidirectional Gateway, Inbound Commands, Outbound FridayClient | ✅ Operational |
| **Real-Time Streaming Hub** | Multiplexed WebSocket Hub (`/ws/v1/live`), Sub-100ms Push, Ring Buffers | ✅ Operational |
| **Advanced Analytics & NL Query** | Conversational SQL Parser, Multi-Touch Attribution (Time-Decay 7d) | ✅ Operational |
| **Privacy, Governance & SaaS** | GDPR/CCPA Exports & Deletions, PII Scrubber, Multi-Tenant Isolation | ✅ Operational |
| **Sentinel & Forge DevSecOps** | Vulnerability Intake, Live Exposure Map, Pre-Flight Deployment Gates | ✅ Operational |
| **IntelX & Futuris Operations** | Competitive Intelligence Battlecards, 24h Traffic Capacity Forecasting | ✅ Operational |

**Evidence basis.** The statuses above say what is implemented and covered by this
repository's test suite, not that every subsystem has been exercised end to end here.
Concretely verified in this environment: `pytest tests` (307 tests), `scripts/pressure_test.py`
(9/9 scenarios, 5000 events at concurrency 200, 60 s soak, zero 5xx) against a live API plus
the development Redis double, `scripts/self_healing_live_test.py` (a real Redis outage:
detected, bounded repair, verified recovery) and `scripts/self_integrity_live_test.py`
(52/52 checks: collaboration, refusals, self-model honesty, self-modification + rollback,
and a FRIDAY command that drives the cognitive loop until peers actually join in).
**CONFIGURED-BUT-UNVERIFIED** without third-party credentials or services: outbound
connectors (SendGrid, Twilio, HubSpot, Calendly, Stripe, Zendesk), Postgres persistence,
a production Redis, and the AI Universe deliberation service — those paths are covered by
mocked tests and deterministic fallbacks only.

---

## 13. Quick Start

### 1. Launch Services via Docker Compose
```bash
docker-compose up -d
```

### 2. Or run the API locally (no Docker)
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# Terminal 1 — Redis (use a real server in production; this is a development double)
python scripts/dev_redis.py --host 0.0.0.0 --port 6379

# Terminal 2 — API (adds apps/*/src and packages/*/src to sys.path, creates data/cortex.db)
REDIS_URL=redis://127.0.0.1:6379/0 APP_ENV=development \
  python scripts/run_api.py --port 8000
```
`APP_ENV=production` refuses to start when the database schema cannot be created, and no
development API key is provisioned outside development.

### 3. Verify Health Probes
- **API Health Check**: `http://localhost:8000/v1/health`
- **Readiness Probe**: `http://localhost:8000/health/ready`
- **Prometheus Metrics**: `http://localhost:8000/metrics`
- **Dashboard UI**: `http://localhost:3000` (or served by the API at `http://localhost:8000/`)

### 4. Run Test Suite
```bash
pytest tests -v          # full suite (unit + integration + upgrade)
```

### 5. Press it against a live server
```bash
python scripts/pressure_test.py \
  --jwt-secret "$JWT_SECRET" \
  --concurrency 200 --events 5000 --soak-seconds 60 --api-pid "$(pgrep -f run_api.py)"
```
Exercises ingest throughput, idempotency races, cross-tenant attacks, rate limiting,
hostile input, a paced soak with RSS sampling, and read-back consistency. It exits
non-zero when an invariant is violated.
