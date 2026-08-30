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
| **IntelX & Futuris Operations** | Competitive Intelligence Battlecards, 24h Traffic Capacity Forecasting | ✅ Operational (128/128 tests green) |

---

## 13. Quick Start

### 1. Launch Services via Docker Compose
```bash
docker-compose up -d
```

### 2. Verify Health Probes
- **API Health Check**: `http://localhost:8000/v1/health`
- **Readiness Probe**: `http://localhost:8000/health/ready`
- **Prometheus Metrics**: `http://localhost:8000/metrics`
- **Dashboard UI**: `http://localhost:3000`

### 3. Run Test Suite
```bash
pytest -v
```
