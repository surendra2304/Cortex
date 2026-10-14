# CORTEX — Autonomous Web Operations Intelligence

> **Role in the FRIDAY Universe:** Cortex is the high-order cognitive reasoning, task decomposition, and logic execution specialist. It ingests, interprets, and acts on structured signals from the web — visitor journeys, conversion patterns, lead scoring, A/B experiments, and security events — decomposing complex operational goals into governed, audited actions.

**Production Gateway:** `https://friday-universe.duckdns.org/cortex/*`  
**Internal Docker Mesh:** `http://cortex:8000` (network: `friday_mesh`)  
**Host Port:** `8001` | **Container Port:** `8000`

---

## Topology

```
Internet
  │
  ▼
Caddy Reverse Proxy (HTTPS, friday-universe.duckdns.org)
  │
  ├──/cortex/*──► Cortex  (http://cortex:8000,  host 8001)
  ├──/friday/*──► FRIDAY  (http://friday:10000, host 10000)
  ├──/memora/*──► Memora  (http://memora:8000,  host 8002)
  └──/* ...other agents in friday_mesh ...
```

All inter-agent calls use Docker internal DNS — `http://friday:10000`, `http://memora:8000`, etc. No public URLs are used inside the mesh.

---

## API Specification

### Authentication

All operator endpoints require a JWT Bearer token or the `X-Cortex-Api-Key` header.  
Public ingestion endpoints accept a provisioned site API key.

### Core Endpoints

#### `GET /health`
Liveness probe. Used by Docker HEALTHCHECK and the Caddy gateway.

```bash
curl https://friday-universe.duckdns.org/cortex/health
```
```json
{
  "status": "ok",
  "service": "cortex",
  "evidence_class": "process_liveness",
  "observed_at": "2026-10-14T16:00:00.000000+00:00"
}
```

#### `GET /health/ready`
Readiness probe. Checks Redis and database connectivity.

```bash
curl https://friday-universe.duckdns.org/cortex/health/ready
```

#### `GET /v1/health`
Versioned health check including environment metadata.

```bash
curl https://friday-universe.duckdns.org/cortex/v1/health
```
```json
{
  "status": "ok",
  "service": "cortex",
  "evidence_class": "process_liveness",
  "observed_at": "2026-10-14T16:00:00.000000+00:00",
  "environment": "production"
}
```

#### `POST /v1/friday/command`
Execute an autonomous FRIDAY command through Cortex's governance layer.

```bash
curl -X POST https://friday-universe.duckdns.org/cortex/v1/friday/command \
  -H "X-Friday-Api-Key: $FRIDAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Convert high-intent visitor on /pricing page",
    "required_capability": "sales",
    "requested_action": "high_intent.detected",
    "context": {
      "visitor_id": "v_abc123",
      "page": "/pricing",
      "time_on_page": 120
    }
  }'
```

#### `POST /v1/task/execute`
Universal Task Protocol — direct task envelope for agent-to-agent calls.

```bash
curl -X POST https://friday-universe.duckdns.org/cortex/v1/task/execute \
  -H "X-Friday-Api-Key: $FRIDAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task_001",
    "source_agent": "friday",
    "action": "analyze_conversion_drop",
    "payload": { "segment": "enterprise", "window_hours": 24 }
  }'
```

#### `POST /v1/track`
Ingest a visitor/product event (public ingestion key required).

```bash
curl -X POST https://friday-universe.duckdns.org/cortex/v1/track \
  -H "X-Api-Key: $SITE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "page_view",
    "page_url": "https://example.com/pricing",
    "visitor_id": "v_abc123",
    "session_id": "s_xyz789"
  }'
```

#### `GET /docs`
Interactive Swagger UI — `https://friday-universe.duckdns.org/cortex/docs`

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `APP_ENV` | `development` | `production` or `development` |
| `PORT` | `8000` | Internal container port |
| `POSTGRES_DSN` | SQLite local | PostgreSQL or SQLite DSN |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `CORTEX_API_KEY` | — | Master operator API key (≥32 chars) |
| `JWT_SECRET` | — | JWT signing secret (≥32 chars) |
| `FRIDAY_API_URL` | `http://friday:10000` | FRIDAY Core gateway URL |
| `FRIDAY_API_KEY` | — | Shared FRIDAY mesh key |
| `MEMORA_URL` | `http://memora:8000` | Episodic memory backend |
| `MEMORA_API_KEY` | — | Memora auth key |
| `MOCK_MODE` | `true` | Mock external side-effects |
| `ALLOWED_ORIGINS` | See config | CORS whitelist (comma-separated) |
| `CORTEX_DEV_AUTH_BYPASS` | `false` | Dev-only auth bypass (never in prod) |

See [`.env.example`](.env.example) for the full list.

---

## Deployment

### Run Locally (Uvicorn)

```bash
# 1. Clone and install
git clone https://github.com/surendra2304/Cortex.git
cd Cortex
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 2. Configure
cp .env.example .env
# Edit .env with your values

# 3. Start
uvicorn cortex_api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Run with Docker

```bash
# Build
docker build -t cortex:latest .

# Run standalone (dev)
docker run -d \
  --name cortex \
  -p 8001:8000 \
  -e APP_ENV=production \
  -e CORTEX_API_KEY=your_key_here \
  -e JWT_SECRET=your_secret_here \
  cortex:latest

# Run in Oracle Cloud mesh
docker run -d \
  --name cortex \
  --network friday_mesh \
  -p 8001:8000 \
  --env-file .env \
  ghcr.io/surendra2304/cortex:latest
```

### Run Tests

```bash
pytest tests --verbose
```

---

## Package Structure

```
Cortex/
├── apps/
│   ├── api/src/cortex_api/     # FastAPI application
│   │   ├── main.py             # App composition & router registration
│   │   ├── config.py           # Settings, DB engine, Redis pool
│   │   ├── friday_router.py    # FRIDAY command/task routing (1400+ lines)
│   │   ├── auth.py             # JWT/RBAC verification
│   │   └── ...                 # 15+ additional routers
│   ├── worker/                 # Redis Streams event processor
│   └── dashboard/              # Next.js control centre UI
├── packages/
│   ├── core/                   # Shared data models, resilience
│   ├── integrations/           # SendGrid, Twilio, HubSpot, Stripe connectors
│   ├── policy_engine/          # Privacy & compliance enforcement
│   ├── agents/                 # Intelligent agent primitives
│   ├── workflow_engine/        # Capacity planning, security incidents
│   └── intelligence/           # Market signals, predictive personalization
├── cortex_upgrade/             # Context firewall, memory, auth upgrade layer
├── tests/                      # 192+ unit, integration & upgrade tests
├── scripts/                    # Developer utilities
├── Dockerfile                  # Production multi-stage build
├── .github/workflows/          # CI (test + Docker build) & deploy (GHCR push)
└── requirements.txt            # Pinned Python dependencies
```

---

## Architecture Decisions

- **No Render.com**: Fully migrated to Oracle Cloud Always Free. All `*.onrender.com` URLs are permanently removed.
- **Internal mesh only**: Agent-to-agent calls use Docker DNS (`http://service:port`), never public internet routes.
- **SQLite default**: Ideal for Oracle's free tier. Switch to `POSTGRES_DSN=postgresql+asyncpg://...` for high-write workloads.
- **Non-root container**: Runs as `appuser` (UID 1000) for security hardening.
- **Tini init**: Proper signal propagation ensures clean `SIGTERM` shutdown within 5 seconds.
