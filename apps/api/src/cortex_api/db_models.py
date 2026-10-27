from datetime import UTC, datetime

import json

from sqlalchemy import (
    CLOB,
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.orm import relationship

from cortex_api.config import Base


def _utcnow() -> datetime:
    """Timezone-aware UTC now (never a naive timestamp)."""
    return datetime.now(UTC)


class OracleJSON(TypeDecorator):
    """JSON stored as CLOB text on Oracle.

    Oracle's async dialect does not expose ``_json_serializer`` /
    ``_json_deserializer``, which SQLAlchemy's generic ``JSON`` type reads during
    bind processing. Serialising in Python keeps JSON columns working on every
    engine (SQLite, PostgreSQL and Oracle) without touching dialect internals.
    """

    impl = CLOB
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, (dict, list, bool, int, float)):
            return value
        return json.loads(value)


# Universal JSON type: native JSONB on PostgreSQL, JSON on SQLite, CLOB text on
# Oracle (whose async dialect cannot drive the generic JSON bind processor).
JSONB = JSON().with_variant(PG_JSONB, "postgresql").with_variant(OracleJSON(), "oracle")


class ProfileModel(Base):
    __tablename__ = "profiles"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    primary_email = Column(String(255), nullable=True, index=True)
    identities = Column(JSONB, default=list, nullable=False)
    traits = Column(JSONB, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    visitors = relationship("VisitorModel", back_populates="profile")
    leads = relationship("LeadModel", back_populates="profile")


class VisitorModel(Base):
    __tablename__ = "visitors"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    site_id = Column(String(64), nullable=False, index=True)
    profile_id = Column(String(64), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    first_seen_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    last_seen_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)
    attributes = Column(JSONB, default=dict, nullable=False)

    profile = relationship("ProfileModel", back_populates="visitors")


class SessionModel(Base):
    __tablename__ = "sessions"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    site_id = Column(String(64), nullable=False, index=True)
    visitor_id = Column(String(64), nullable=False, index=True)
    user_agent = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    started_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    session_metadata = Column("metadata", JSONB, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    events = relationship("EventModel", back_populates="session", cascade="all, delete-orphan")


class EventModel(Base):
    __tablename__ = "events"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    site_id = Column(String(64), nullable=False, index=True)
    session_id = Column(String(64), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    type = Column(String(128), nullable=False, index=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, index=True)
    actor_type = Column(String(32), default="visitor", nullable=False)
    actor_id = Column(String(64), nullable=False, index=True)
    source = Column(String(64), default="web-sdk", nullable=False)
    data = Column(JSONB, default=dict, nullable=False)
    consent = Column(JSONB, nullable=True)
    trace_id = Column(String(64), nullable=True)
    server_received_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    client_ip = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)

    session = relationship("SessionModel", back_populates="events")

    __table_args__ = (
        Index("idx_events_site_type_occurred", "site_id", "type", "occurred_at"),
        Index("idx_events_actor_occurred", "actor_id", "occurred_at"),
    )


class LeadModel(Base):
    __tablename__ = "leads"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    profile_id = Column(String(64), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    score = Column(Float, default=0.0, nullable=False)
    status = Column(String(32), default="new", nullable=False)
    source = Column(String(64), nullable=True)
    lead_metadata = Column("metadata", JSONB, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    profile = relationship("ProfileModel", back_populates="leads")


class AuditRecordModel(Base):
    __tablename__ = "audit_records"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    actor_id = Column(String(64), nullable=False)
    action = Column(String(128), nullable=False, index=True)
    target_resource = Column(String(255), nullable=False)
    changes = Column(JSONB, default=dict, nullable=False)
    verification_status = Column(String(32), default="verified", nullable=False)
    trace_id = Column(String(64), nullable=True, index=True)
    timestamp = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class TenantModel(Base):
    """Durable tenant registry record for onboarding and tenant settings."""

    __tablename__ = "tenants"
    __table_args__ = (UniqueConstraint("primary_site_id", name="uq_tenants_primary_site_id"),)

    id = Column(String(64), primary_key=True)
    name = Column(String(255), nullable=False)
    admin_email = Column(String(254), nullable=False)
    plan = Column(String(32), nullable=False)
    primary_site_id = Column(String(64), nullable=False)
    created_by = Column(String(128), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class ApiKeyModel(Base):
    __tablename__ = "api_keys"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    site_id = Column(String(64), nullable=False, index=True)
    key_hash = Column(String(128), unique=True, nullable=False, index=True)
    key_prefix = Column(String(16), nullable=False)
    name = Column(String(128), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)


class SentinelScanModel(Base):
    """Durable scan-level posture summary, including clean scans with zero findings."""

    __tablename__ = "sentinel_scans"
    __table_args__ = (
        UniqueConstraint("tenant_id", "site_id", "sentinel_task_id", name="uq_sentinel_scan_tenant_site_task"),
        Index("idx_sentinel_scans_tenant_site_received", "tenant_id", "site_id", "received_at"),
    )

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    site_id = Column(String(64), nullable=False, index=True)
    sentinel_task_id = Column(String(128), nullable=False)
    posture_score = Column(Float, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    received_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)

    findings = relationship("SentinelFindingModel", back_populates="scan", cascade="all, delete-orphan")


class SentinelFindingModel(Base):
    """Tenant/site-scoped security finding records associated with a Sentinel scan."""

    __tablename__ = "sentinel_findings"
    __table_args__ = (
        UniqueConstraint("scan_id", "finding_id", name="uq_sentinel_finding_scan_finding"),
        Index("idx_sentinel_findings_tenant_site_received", "tenant_id", "site_id", "received_at"),
    )

    id = Column(String(64), primary_key=True)
    scan_id = Column(String(64), ForeignKey("sentinel_scans.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    site_id = Column(String(64), nullable=False, index=True)
    finding_id = Column(String(128), nullable=False)
    severity = Column(String(16), nullable=False, index=True)
    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=False)
    evidence_ref = Column(Text, nullable=True)
    attack_vector = Column(String(128), nullable=True)
    affected_endpoint = Column(Text, nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    received_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)

    scan = relationship("SentinelScanModel", back_populates="findings")


class IdentityLinkModel(Base):
    __tablename__ = "identity_links"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    source_type = Column(String(32), nullable=False)  # anonymous_id, email, user_id, device_fingerprint
    source_value = Column(String(255), nullable=False, index=True)
    target_type = Column(String(32), nullable=False)  # profile_id, lead_id, customer_id
    target_id = Column(String(64), nullable=False, index=True)
    confidence = Column(Float, default=1.0, nullable=False)
    link_metadata = Column("metadata", JSONB, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class LeadScoreHistoryModel(Base):
    __tablename__ = "lead_scores"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    lead_id = Column(String(64), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    total_score = Column(Float, nullable=False)
    behavior_score = Column(Float, default=0.0, nullable=False)
    firmographic_score = Column(Float, default=0.0, nullable=False)
    engagement_score = Column(Float, default=0.0, nullable=False)
    source_score = Column(Float, default=0.0, nullable=False)
    score_breakdown = Column(JSONB, default=dict, nullable=False)
    triggered_by = Column(String(64), default="event", nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class MemoryEntryModel(Base):
    __tablename__ = "memory_entries"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    scope = Column(String(32), nullable=False, index=True)  # visitor, lead, customer, site, strategy
    scope_id = Column(String(64), nullable=False, index=True)
    key = Column(String(128), nullable=False, index=True)
    content = Column(JSONB, default=dict, nullable=False)
    trust_label = Column(String(32), default="verified_telemetry", nullable=False)
    source = Column(String(64), default="cognitive_loop", nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)


class WorkflowRunModel(Base):
    __tablename__ = "workflow_runs"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    workflow_name = Column(String(64), nullable=False, index=True)
    trigger_event = Column(String(128), nullable=False)
    state = Column(String(32), nullable=False, index=True)  # TRIGGERED, PLANNING, EXECUTING, COMPLETED, etc.
    steps = Column(JSONB, default=list, nullable=False)
    context_data = Column("context", JSONB, default=dict, nullable=False)
    started_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class ApprovalQueueModel(Base):
    __tablename__ = "approval_queue"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    workflow_run_id = Column(String(64), nullable=True, index=True)
    action_type = Column(String(64), nullable=False)
    target = Column(String(128), nullable=False)
    params = Column(JSONB, default=dict, nullable=False)
    rationale = Column(Text, nullable=False)
    evidence_refs = Column(JSONB, default=list, nullable=False)
    risk_score = Column(Float, default=0.5, nullable=False)
    status = Column(String(32), default="pending", nullable=False)  # pending, approved, rejected, expired
    decision_by = Column(String(128), nullable=True)
    decision_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    # Filled when an approved action is executed through the tool bus on approval.
    execution_status = Column(String(32), nullable=True)  # executed | failed | blocked | skipped
    execution_result = Column(JSONB, nullable=True)


class StrategyPerformanceModel(Base):
    __tablename__ = "strategy_performance"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    strategy_key = Column(String(128), nullable=False, index=True)
    status = Column(String(32), default="PROBATION", nullable=False)  # PROVEN, PROBATION, DEMOTED
    total_executions = Column(Integer, default=0, nullable=False)
    successes = Column(Integer, default=0, nullable=False)
    failures = Column(Integer, default=0, nullable=False)
    success_rate = Column(Float, default=0.0, nullable=False)
    confidence = Column(Float, default=0.0, nullable=False)
    recent_outcomes = Column(JSONB, default=list, nullable=False)
    last_updated_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
