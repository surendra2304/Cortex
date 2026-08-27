# NEXUS Core Data Model & Schema Reference

## 1. Relational Entities (PostgreSQL)

| Table Name | Primary Key | Key Columns | Purpose |
| :--- | :--- | :--- | :--- |
| **`profiles`** | `id (VARCHAR)` | `tenant_id`, `primary_email`, `identities (JSONB)`, `traits (JSONB)` | Canonical unified profile stitching multiple visitor identities. |
| **`visitors`** | `id (VARCHAR)` | `tenant_id`, `site_id`, `profile_id (FK)`, `first_seen_at`, `attributes` | Persistent browser visitors tracked via SDK (`nexus_vid`). |
| **`sessions`** | `id (VARCHAR)` | `tenant_id`, `site_id`, `visitor_id (FK)`, `started_at`, `ended_at` | Individual visit sessions with 30-minute idle expiry. |
| **`events`** | `id (VARCHAR)` | `tenant_id`, `site_id`, `session_id (FK)`, `type`, `occurred_at`, `actor_id` | Canonical immutable telemetry store with composite indexes. |
| **`identity_links`** | `id (VARCHAR)` | `source_type`, `source_value`, `target_type`, `target_id`, `confidence` | Graph representation of identity linkages and mergers. |
| **`leads`** | `id (VARCHAR)` | `tenant_id`, `profile_id (FK)`, `score (FLOAT)`, `status`, `source` | Sales pipeline leads generated from identified high-intent visitors. |
| **`lead_scores`** | `id (VARCHAR)` | `lead_id (FK)`, `total_score`, `behavior_score`, `firmographic_score` | Historical trajectory of lead score calculations. |
| **`memory_entries`** | `id (VARCHAR)` | `scope`, `scope_id`, `key`, `content (JSONB)`, `trust_label` | Long-lived cognitive memory with trust classification labels. |
| **`workflow_runs`** | `id (VARCHAR)` | `workflow_name`, `trigger_event`, `state`, `steps (JSONB)` | Execution history and step timelines for automated workflows. |
| **`approval_queue`** | `id (VARCHAR)` | `action_type`, `target`, `params`, `risk_score`, `status`, `expires_at` | Human-in-the-loop pending approval actions. |
| **`strategy_performance`** | `id (VARCHAR)`| `strategy_key`, `status (PROVEN/DEMOTED)`, `success_rate`, `confidence` | Closed-loop outcome measurement and strategy win-rates. |
| **`audit_records`** | `id (VARCHAR)` | `actor_id`, `action`, `target_resource`, `trace_id`, `timestamp` | Immutable audit trail for all system and agent mutations. |
| **`api_keys`** | `id (VARCHAR)` | `site_id`, `key_hash`, `key_prefix`, `is_active` | Public SDK and service API keys. |

---

## 2. High-Performance Indexing Strategy
- `idx_events_site_type_occurred` on `events(site_id, type, occurred_at)`
- `idx_events_actor_occurred` on `events(actor_id, occurred_at)`
- `idx_events_session` on `events(session_id)`
