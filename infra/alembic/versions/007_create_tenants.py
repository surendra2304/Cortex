"""persist tenant registry records for onboarding

Revision ID: 007_create_tenants
Revises: 006_approval_execution_columns
Create Date: 2026-10-21 06:17:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007_create_tenants"
down_revision: str | None = "006_approval_execution_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("admin_email", sa.String(length=254), nullable=False),
        sa.Column("plan", sa.String(length=32), nullable=False),
        sa.Column("primary_site_id", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("primary_site_id", name="uq_tenants_primary_site_id"),
    )


def downgrade() -> None:
    op.drop_table("tenants")
