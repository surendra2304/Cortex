-- Migration: 001_create_events_and_sessions.sql
-- Description: Create sessions and events tables for multi-tenant telemetry and session replay

CREATE TABLE IF NOT EXISTS sessions (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    site_id VARCHAR(64) NOT NULL,
    visitor_id VARCHAR(64) NOT NULL,
    user_agent TEXT,
    ip_address VARCHAR(45),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_tenant_site ON sessions (tenant_id, site_id);
CREATE INDEX IF NOT EXISTS idx_sessions_visitor ON sessions (visitor_id);
CREATE INDEX IF NOT EXISTS idx_sessions_started_at ON sessions (started_at DESC);

CREATE TABLE IF NOT EXISTS events (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    site_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) REFERENCES sessions(id) ON DELETE SET NULL,
    type VARCHAR(128) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    actor_type VARCHAR(32) NOT NULL DEFAULT 'visitor',
    actor_id VARCHAR(64) NOT NULL,
    source VARCHAR(64) NOT NULL DEFAULT 'web-sdk',
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    consent JSONB,
    trace_id VARCHAR(64),
    server_received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    client_ip VARCHAR(45),
    user_agent TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_tenant_site_time ON events (tenant_id, site_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_type ON events (type);
CREATE INDEX IF NOT EXISTS idx_events_actor ON events (actor_type, actor_id);
CREATE INDEX IF NOT EXISTS idx_events_session ON events (session_id);
