from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Float, Boolean, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from nexus_api.config import Base


class ProfileModel(Base):
    __tablename__ = "profiles"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    primary_email = Column(String(255), nullable=True, index=True)
    identities = Column(JSONB, default=list, nullable=False)
    traits = Column(JSONB, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    visitors = relationship("VisitorModel", back_populates="profile")
    leads = relationship("LeadModel", back_populates="profile")


class VisitorModel(Base):
    __tablename__ = "visitors"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    site_id = Column(String(64), nullable=False, index=True)
    profile_id = Column(String(64), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    first_seen_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
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
    started_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    session_metadata = Column("metadata", JSONB, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    events = relationship("EventModel", back_populates="session", cascade="all, delete-orphan")


class EventModel(Base):
    __tablename__ = "events"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    site_id = Column(String(64), nullable=False, index=True)
    session_id = Column(String(64), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    type = Column(String(128), nullable=False, index=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    actor_type = Column(String(32), default="visitor", nullable=False)
    actor_id = Column(String(64), nullable=False)
    source = Column(String(64), default="web-sdk", nullable=False)
    data = Column(JSONB, default=dict, nullable=False)
    consent = Column(JSONB, nullable=True)
    trace_id = Column(String(64), nullable=True)
    server_received_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    client_ip = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)

    session = relationship("SessionModel", back_populates="events")


class LeadModel(Base):
    __tablename__ = "leads"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    profile_id = Column(String(64), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    score = Column(Float, default=0.0, nullable=False)
    status = Column(String(32), default="new", nullable=False)
    source = Column(String(64), nullable=True)
    lead_metadata = Column("metadata", JSONB, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

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
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class ApiKeyModel(Base):
    __tablename__ = "api_keys"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    site_id = Column(String(64), nullable=False, index=True)
    key_hash = Column(String(128), unique=True, nullable=False, index=True)
    key_prefix = Column(String(16), nullable=False)
    name = Column(String(128), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)


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
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


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
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


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
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
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
    started_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
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
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    decided_at = Column(DateTime(timezone=True), nullable=True)


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
    last_updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
