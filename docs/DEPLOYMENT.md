# NEXUS Production Infrastructure, Deployment & Operations Manual

This document defines the deployment architecture, cloud infrastructure, Kubernetes manifests, CI/CD automation, monitoring stack, and disaster recovery procedures for **NEXUS — Autonomous Website & Web App Operations Intelligence**.

---

## 1. Cloud Architecture Overview (AWS)

```text
                                 +-------------------------+
                                 |  Cloudflare / Route 53  |
                                 +------------+------------+
                                              |
                                              v
                              +---------------+---------------+
                              | Application Load Balancer(ALB)|
                              |         HTTPS / TLS           |
                              +---------------+---------------+
                                              |
                     +------------------------+------------------------+
                     |                                                 |
                     v                                                 v
         +-----------------------+                         +-----------------------+
         |  ECS Fargate API Task |                         |  ECS Fargate API Task |
         |   (Auto-Scaling HPA)  |                         |   (Auto-Scaling HPA)  |
         +-----------+-----------+                         +-----------+-----------+
                     |                                                 |
                     +------------------------+------------------------+
                                              |
                         +--------------------+--------------------+
                         |                                         |
                         v                                         v
            +-------------------------+               +-------------------------+
            | RDS PostgreSQL Multi-AZ |               | ElastiCache Redis 7     |
            | (Partitioned Events)    |               | (Streams & Rate Limits) |
            +-------------------------+               +-------------------------+
                         ^                                         ^
                         |                                         |
                         +--------------------+--------------------+
                                              |
                                 +------------+------------+
                                 | ECS Fargate Worker Task |
                                 | (10-Phase Cognitive Loop|
                                 +-------------------------+
```

---

## 2. Infrastructure as Code: Terraform (`infra/terraform/`)

The Terraform module provisions a secure, multi-AZ deployment on AWS:
- **VPC & Subnets**: 3 Public Subnets (NAT Gateway, ALB) + 3 Private Subnets (ECS, RDS, Redis).
- **RDS PostgreSQL 15**: Multi-AZ standby replica, automated 7-day backup retention, gp3 storage auto-scaling up to 1TB, row-level security enabled.
- **ElastiCache Redis 7**: Managed cluster in private subnets with auto-failover for stream dispatch.
- **ECS Fargate Cluster**: Elastic CPU/Memory resource allocation for API and Worker services.
- **S3 Bucket**: Encrypted, versioned storage with cross-region replication for backups and exports.

---

## 3. Kubernetes Alternative: Manifests (`infra/k8s/`)

For self-hosted or cloud-native Kubernetes clusters:
- **`nexus-api` Deployment**: 3 initial replicas with CPU/Memory request limits.
- **Horizontal Pod Autoscaler (HPA)**: Scales `nexus-api` dynamically from **3 to 10 replicas** based on **70% target CPU utilization**.
- **`nexus-worker` Deployment**: 2 dedicated worker replicas processing Redis Streams.
- **cert-manager Ingress**: Automatic TLS certificate provisioning from Let's Encrypt.

---

## 4. Monitoring, Prometheus & AlertManager Stack

### Prometheus Scrape Configurations & Metrics
- Scrapes `http://nexus-api:8000/metrics` every 15s.
- **Core Tracked Metrics**:
  - `events_ingested_total` (counter)
  - `cognitive_loop_duration_seconds` (histogram & p99 summary)
  - `ai_universe_calls_total` & `ai_universe_fallback_total`
  - `workflow_runs_total` & `approval_queue_depth`
  - `security_findings_received_total` & `security_incidents_created_total`
  - `deployment_gates_evaluated_total` (DevSecOps gates)
  - `intelx_research_submitted_total` & `competitive_intelligence_findings_total`
  - `futuris_forecasts_requested_total`, `predictive_personalization_adjustments_total`, & `capacity_preparation_triggered_total`

### AlertManager Rules
- **Service Down**: Fires when `up{job="nexus-api"} == 0` for > 1m (Severity: Critical).
- **High Ingestion Error Rate**: Fires when `rate(events_ingested_errors[5m]) / rate(events_ingested_total[5m]) > 0.05` (Severity: High).
- **Cognitive Loop Latency Spike**: Fires when `histogram_quantile(0.99, rate(cognitive_loop_duration_seconds_bucket[5m])) > 2.0` (Severity: Warning).

---

## 5. Eight-System Integration Ecosystem

1. **Sentinel Security Integration**: Real-time vulnerability finding intake (`POST /v1/sentinel/findings`), live attack surface exposure mapping (`GET /v1/sentinel/exposure`), and automated incident triage.
2. **Forge DevSecOps Deployment Gates**: Pre-flight API security scan on candidate build endpoints; enforces `CRITICAL -> BLOCKED`, `HIGH -> HITL OVERRIDE`, and `LOW -> APPROVED`.
3. **IntelX Competitive & Market Intelligence**: Automated feature gap extraction, competitive sales battlecards, and market trend tracking.
4. **Futuris Predictive Web Operations**: 24h traffic forecasting with 95% CI, automated capacity scaling recommendations, and proactive conversion drop mitigation.
5. **AI Universe Multi-Agent Deliberation**: `FAST`, `REVIEW`, and `DEBATE` modes with deterministic fallback.
6. **Universal Tool Runtime**: Connectors for SendGrid, HubSpot, Stripe, Zendesk, Calendly, Twilio, and outbound HMAC signed webhooks.
7. **Reinforcement Strategy Learning**: Closed-loop outcome measurement with automated strategy promotion/demotion.
8. **FRIDAY Orchestration Bridge**: Executive voice summaries, priority leads stream, and bi-directional desktop/device action delegation.

---

## 6. Automated Backup & Disaster Recovery Procedure

### Automated Schedules
1. **PostgreSQL Automated Snapshots**: Continuous Write-Ahead Logging (WAL) archiving with daily automated snapshots stored across 7-day retention windows.
2. **Redis In-Memory State**: Snapshot RDB backups written to persistent volumes every 6 hours.
3. **S3 Artifacts & Exports**: Replicated across secondary AWS regions using S3 Cross-Region Replication (CRR).

### Point-in-Time Recovery (PITR) Execution
```bash
# 1. Restore RDS database instance to specific timestamp
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier nexus-db-production \
  --target-db-instance-identifier nexus-db-restored \
  --restore-time 2026-08-28T06:00:00Z \
  --db-subnet-group-name nexus-db-subnet-group-production

# 2. Update ECS task definition database endpoint to the restored instance
aws ecs update-service --cluster nexus-cluster-production \
  --service nexus-api --force-new-deployment
```

---

## 7. Continuous Deployment Workflow (.github/workflows/deploy.yml)

1. **Automated Testing**: Runs 128 tests in pytest and validates strict diary structural constraints.
2. **Container Build**: Multi-stage Docker builds push signed immutable images to GitHub Container Registry (`ghcr.io`).
3. **Staging Rollout & Smoke Tests**: Automatic rollout to Staging environment verifying `/v1/health` and `/health/ready` connectivity.
4. **Production Rolling Update**: Zero-downtime deployment replacing ECS Fargate tasks sequentially.
