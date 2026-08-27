"""create api_keys table

Revision ID: 004_create_api_keys
Revises: 003_audit_records
Create Date: 2026-08-27 23:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '004_api_keys'
down_revision: Union[str, None] = '003_audit_records'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'api_keys',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('tenant_id', sa.String(length=64), nullable=False),
        sa.Column('site_id', sa.String(length=64), nullable=False),
        sa.Column('key_hash', sa.String(length=128), unique=True, nullable=False),
        sa.Column('key_prefix', sa.String(length=16), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index('idx_api_keys_hash', 'api_keys', ['key_hash'])
    op.create_index('idx_api_keys_tenant_site', 'api_keys', ['tenant_id', 'site_id'])


def downgrade() -> None:
    op.drop_index('idx_api_keys_tenant_site', table_name='api_keys')
    op.drop_index('idx_api_keys_hash', table_name='api_keys')
    op.drop_table('api_keys')
