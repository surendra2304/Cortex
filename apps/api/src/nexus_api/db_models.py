from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Float
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
