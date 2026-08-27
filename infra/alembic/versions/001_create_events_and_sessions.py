"""create events and sessions tables

Revision ID: 001_create_events_and_sessions
Revises: 
Create Date: 2026-08-27 22:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001_events_and_sessions'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create sessions table
    op.create_table(
        'sessions',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('tenant_id', sa.String(length=64), nullable=False),
        sa.Column('site_id', sa.String(length=64), nullable=False),
        sa.Column('visitor_id', sa.String(length=64), nullable=False),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False)
    )
    op.create_index('idx_sessions_tenant_site', 'sessions', ['tenant_id', 'site_id'])
    op.create_index('idx_sessions_visitor', 'sessions', ['visitor_id'])
    op.create_index('idx_sessions_started_at', 'sessions', [sa.text('started_at DESC')])

    # Create events table
    op.create_table(
        'events',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('tenant_id', sa.String(length=64), nullable=False),
        sa.Column('site_id', sa.String(length=64), nullable=False),
        sa.Column('session_id', sa.String(length=64), sa.ForeignKey('sessions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('type', sa.String(length=128), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('actor_type', sa.String(length=32), server_default='visitor', nullable=False),
        sa.Column('actor_id', sa.String(length=64), nullable=False),
        sa.Column('source', sa.String(length=64), server_default='web-sdk', nullable=False),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('consent', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('trace_id', sa.String(length=64), nullable=True),
        sa.Column('server_received_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('client_ip', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True)
    )
    op.create_index('idx_events_tenant_site_time', 'events', ['tenant_id', 'site_id', sa.text('occurred_at DESC')])
    op.create_index('idx_events_type', 'events', ['type'])
    op.create_index('idx_events_actor', 'events', ['actor_type', 'actor_id'])
    op.create_index('idx_events_session', 'events', ['session_id'])


def downgrade() -> None:
    op.drop_index('idx_events_session', table_name='events')
    op.drop_index('idx_events_actor', table_name='events')
    op.drop_index('idx_events_type', table_name='events')
    op.drop_index('idx_events_tenant_site_time', table_name='events')
    op.drop_table('events')

    op.drop_index('idx_sessions_started_at', table_name='sessions')
    op.drop_index('idx_sessions_visitor', table_name='sessions')
    op.drop_index('idx_sessions_tenant_site', table_name='sessions')
    op.drop_table('sessions')
