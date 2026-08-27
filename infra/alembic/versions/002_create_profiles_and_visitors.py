"""create profiles and visitors tables

Revision ID: 002_create_profiles_and_visitors
Revises: 001_events_and_sessions
Create Date: 2026-08-27 22:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '002_profiles_and_visitors'
down_revision: Union[str, None] = '001_events_and_sessions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create profiles table
    op.create_table(
        'profiles',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('tenant_id', sa.String(length=64), nullable=False),
        sa.Column('primary_email', sa.String(length=255), nullable=True),
        sa.Column('identities', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('traits', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False)
    )
    op.create_index('idx_profiles_tenant_email', 'profiles', ['tenant_id', 'primary_email'])

    # Create visitors table
    op.create_table(
        'visitors',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('tenant_id', sa.String(length=64), nullable=False),
        sa.Column('site_id', sa.String(length=64), nullable=False),
        sa.Column('profile_id', sa.String(length=64), sa.ForeignKey('profiles.id', ondelete='SET NULL'), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False)
    )
    op.create_index('idx_visitors_tenant_site', 'visitors', ['tenant_id', 'site_id'])
    op.create_index('idx_visitors_profile', 'visitors', ['profile_id'])

    # Create leads table
    op.create_table(
        'leads',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('tenant_id', sa.String(length=64), nullable=False),
        sa.Column('profile_id', sa.String(length=64), sa.ForeignKey('profiles.id', ondelete='SET NULL'), nullable=True),
        sa.Column('score', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('status', sa.String(length=32), server_default='new', nullable=False),
        sa.Column('source', sa.String(length=64), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False)
    )
    op.create_index('idx_leads_tenant_status', 'leads', ['tenant_id', 'status'])
    op.create_index('idx_leads_profile', 'leads', ['profile_id'])


def downgrade() -> None:
    op.drop_index('idx_leads_profile', table_name='leads')
    op.drop_index('idx_leads_tenant_status', table_name='leads')
    op.drop_table('leads')

    op.drop_index('idx_visitors_profile', table_name='visitors')
    op.drop_index('idx_visitors_tenant_site', table_name='visitors')
    op.drop_table('visitors')

    op.drop_index('idx_profiles_tenant_email', table_name='profiles')
    op.drop_table('profiles')
