from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from nexus_api.config import Base


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
