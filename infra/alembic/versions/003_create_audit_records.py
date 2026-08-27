"""create audit_records table

Revision ID: 003_create_audit_records
Revises: 002_profiles_and_visitors
Create Date: 2026-08-27 22:35:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '003_audit_records'
down_revision: Union[str, None] = '002_profiles_and_visitors'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_records',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('tenant_id', sa.String(length=64), nullable=False),
        sa.Column('actor_id', sa.String(length=64), nullable=False),
        sa.Column('action', sa.String(length=128), nullable=False),
        sa.Column('target_resource', sa.String(length=255), nullable=False),
        sa.Column('changes', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('verification_status', sa.String(length=32), server_default='verified', nullable=False),
        sa.Column('trace_id', sa.String(length=64), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False)
    )
    op.create_index('idx_audit_records_tenant_time', 'audit_records', ['tenant_id', sa.text('timestamp DESC')])
    op.create_index('idx_audit_records_action', 'audit_records', ['action'])
    op.create_index('idx_audit_records_trace', 'audit_records', ['trace_id'])


def downgrade() -> None:
    op.drop_index('idx_audit_records_trace', table_name='audit_records')
    op.drop_index('idx_audit_records_action', table_name='audit_records')
    op.drop_index('idx_audit_records_tenant_time', table_name='audit_records')
    op.drop_table('audit_records')
