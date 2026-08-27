# NEXUS — Autonomous Website & Web App Operations Intelligence

## 1. Definition
NEXUS is a standalone autonomous operations platform for an existing website or web application. It is not a website builder or deployment platform. After integration, NEXUS observes digital activity, understands what is happening, reasons over the state of the property, executes approved actions, measures outcomes, and continuously improves operations.

---

## 2. What NEXUS IS / IS NOT

| What NEXUS IS | What NEXUS IS NOT |
| :--- | :--- |
| **Autonomous Operations Platform** for live digital properties | **Not a website builder** (Wix, Webflow, WordPress) |
| **Unified Intelligence Layer** (events, visitors, leads, telemetry) | **Not a hosting or deployment provider** (Vercel, AWS) |
| **Agent Runtime with Governed Tools** (human-in-the-loop policies) | **Not a simple passive analytics dashboard** (GA4, Mixpanel) |
| **Multi-Agent Orchestrator** (Growth, Sales, Support, Reliability) | **Not a fixed three-agent demo script** |
| **AI Universe Intelligence Consumer** (structured cognitive engine) | **Not an AI Universe replacement** |
| **Specialist Operator Capability** consumable by FRIDAY OS | **Not a FRIDAY OS duplicate or clone** |

---

## 3. Core Product Promise
> *"Connect NEXUS to an existing website or web app once, give it the required permissions and integrations, and it becomes an intelligent operations layer that monitors health, captures and qualifies intent, coordinates support, orchestrates growth experiments, routes high-value opportunities, and continuously optimizes digital operations under strict policy controls."*

---

## 4. Design Principles
1. **Autonomy with Boundaries**: Agents can act autonomously within strictly defined policy constraints; high-impact mutations require operator approval.
2. **AI-First, Not AI-Only**: Deterministic logic handles standard routing; AI Universe deliberation is reserved for ambiguous or strategic goals.
3. **Provider Independence**: Pluggable integrations (SendGrid, Twilio, HubSpot, Stripe, Zendesk, Calendly) behind the Universal Tool Contract.
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
|           NEXUS             |       |           FRIDAY            |
| (Web Operations Specialist) |<=====>|   (General OS Operator)     |
+-----------------------------+       +-----------------------------+
```

### Critical Separation Rule
> **"NEXUS should not become a hidden FRIDAY module. AI Universe should not become a hidden NEXUS module. Each repository must be independently runnable, testable, and deployable."**

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
|                                     NEXUS CORE WORKER                                 |
|                                                                                       |
|   +-------------------+     +---------------------+     +-------------------------+   |
|   |  Context Engine   | --> | Dynamic Agents (4+) | --> |      Policy Engine      |   |
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

## 12. Implementation Status (Build Phases)

| Phase | Milestone | Status |
| :--- | :--- | :--- |
| **Phase 0** | Repository & Architecture Foundation | ✅ Complete |
| **Phase 1** | Ingestion, Event Gateway & Storage Engine | ✅ Complete |
| **Phase 2** | Understand Layer (Identity, Scoring, Funnels, Memory) | ✅ Complete |
| **Phase 3** | Act Layer (Workflow Engine, Human-in-the-Loop Approvals) | ✅ Complete |
| **Phase 4** | Universal Tool Bus & Deep Integrations (7 Connectors) | ✅ Complete |
| **Phase 5** | AI Universe Deliberation Adapter (FAST, REVIEW, DEBATE) | ✅ Complete |
| **Phase 6** | Closed-Loop Outcome Measurement & Strategy Learning | ✅ Complete |
| **Phase 7** | A/B Experimentation Engine & Personalization | ✅ Complete |
| **Phase 8** | FRIDAY Cross-System Integration Bridge & Outbound Client | ✅ Complete |
| **Phase 9** | Production Hardening, Metrics, Indexing & Verification | ✅ Complete (85/85 tests green) |

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
pytest tests/unit -v
```
