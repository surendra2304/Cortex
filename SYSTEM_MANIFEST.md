# CORTEX System Manifest

## Identity

| Field | Value |
|---|---|
| **Service Name** | Cortex |
| **Role** | Autonomous Web Operations Intelligence — Reasoning, Task Decomposition, Logic Execution |
| **Version** | 2.1.0 |
| **Production Gateway** | https://friday-universe.duckdns.org/cortex |
| **Internal Docker Mesh URL** | http://cortex:8000 |
| **Container Port** | 8000 |
| **Host Port** | 8001 |
| **Docker Network** | friday_mesh |
| **Health Endpoint** | https://friday-universe.duckdns.org/cortex/health |
| **Docs (Swagger)** | https://friday-universe.duckdns.org/cortex/docs |

## FRIDAY Universe Peer Mesh

All peer communication uses Docker internal DNS — no public internet hops.

| Service | Internal URL | Role |
|---|---|---|
| FRIDAY Core | http://friday:10000 | Gateway & orchestrator |
| Memora | http://memora:8000 | Episodic memory backend |
| IntelX | http://intelx:8000 | Competitive intelligence |
| Futuris | http://futuris:8000 | Predictive analytics |
| Stratex | http://stratex:8000 | Growth strategy |
| Forge | http://forge:8000 | Content generation |
| Sentinel | http://sentinel:8000 | Security monitoring |
| Inference | http://inference:8000 | LLM deliberation |

## Environment Variables (Production)

```env
APP_ENV=production
PORT=8000
POSTGRES_DSN=postgresql+asyncpg://cortex:password@db:5432/cortex_db
REDIS_URL=redis://redis:6379/0
CORTEX_API_KEY=<64-char hex>
JWT_SECRET=<64-char hex>
FRIDAY_API_URL=http://friday:10000
FRIDAY_API_KEY=<shared-mesh-key>
MEMORA_URL=http://memora:8000
MEMORA_API_KEY=<memora-key>
MOCK_MODE=false
ALLOWED_ORIGINS=https://friday-universe.duckdns.org
```

## Deployment

- **Infrastructure:** Oracle Cloud Always Free (2 OCPUs, 12 GB RAM, ARM64/amd64)
- **Container runtime:** Docker with `friday_mesh` bridge network
- **TLS termination:** Caddy reverse proxy (auto-HTTPS via DuckDNS)
- **Image registry:** GHCR (`ghcr.io/surendra2304/cortex:latest`)
- **CI/CD:** GitHub Actions → GHCR push → Oracle Cloud pull + restart
