"""record tool-bus execution outcome on approval_queue rows

Revision ID: 006_approval_execution_columns
Revises: 005_cognition_tables
Create Date: 2026-10-07 00:00:00.000000

Approving an approval-queue item now executes the action through the tool bus
and records the outcome on the row (execution_status / execution_result), so the
loop propose -> gate -> approval -> execution -> verification is closed and an
operator can see what an approved action actually did.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006_approval_execution_columns"
down_revision: str | None = "005_cognition_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONType = sa.JSON().with_variant(sa.dialects.postgresql.JSONB, "postgresql")


def upgrade() -> None:
    op.add_column("approval_queue", sa.Column("execution_status", sa.String(length=32), nullable=True))
    op.add_column("approval_queue", sa.Column("execution_result", JSONType, nullable=True))


def downgrade() -> None:
    op.drop_column("approval_queue", "execution_result")
    op.drop_column("approval_queue", "execution_status")
