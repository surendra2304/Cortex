"""persist and isolate Sentinel scans and findings by tenant

Revision ID: 008_sentinel_tenant_findings
Revises: 007_create_tenants
Create Date: 2026-10-21 06:28:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "008_sentinel_tenant_findings"
down_revision: str | None = "007_create_tenants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sentinel_scans",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("site_id", sa.String(length=64), nullable=False),
        sa.Column("sentinel_task_id", sa.String(length=128), nullable=False),
        sa.Column("posture_score", sa.Float(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("tenant_id", "site_id", "sentinel_task_id", name="uq_sentinel_scan_tenant_site_task"),
    )
    op.create_index("ix_sentinel_scans_tenant_id", "sentinel_scans", ["tenant_id"])
    op.create_index("ix_sentinel_scans_site_id", "sentinel_scans", ["site_id"])
    op.create_index("ix_sentinel_scans_received_at", "sentinel_scans", ["received_at"])
    op.create_index("idx_sentinel_scans_tenant_site_received", "sentinel_scans", ["tenant_id", "site_id", "received_at"])

    op.create_table(
        "sentinel_findings",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("scan_id", sa.String(length=64), sa.ForeignKey("sentinel_scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("site_id", sa.String(length=64), nullable=False),
        sa.Column("finding_id", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence_ref", sa.Text(), nullable=True),
        sa.Column("attack_vector", sa.String(length=128), nullable=True),
        sa.Column("affected_endpoint", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("scan_id", "finding_id", name="uq_sentinel_finding_scan_finding"),
    )
    op.create_index("ix_sentinel_findings_scan_id", "sentinel_findings", ["scan_id"])
    op.create_index("ix_sentinel_findings_tenant_id", "sentinel_findings", ["tenant_id"])
    op.create_index("ix_sentinel_findings_site_id", "sentinel_findings", ["site_id"])
    op.create_index("ix_sentinel_findings_severity", "sentinel_findings", ["severity"])
    op.create_index("ix_sentinel_findings_received_at", "sentinel_findings", ["received_at"])
    op.create_index(
        "idx_sentinel_findings_tenant_site_received",
        "sentinel_findings",
        ["tenant_id", "site_id", "received_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_sentinel_findings_tenant_site_received", table_name="sentinel_findings")
    op.drop_index("ix_sentinel_findings_received_at", table_name="sentinel_findings")
    op.drop_index("ix_sentinel_findings_severity", table_name="sentinel_findings")
    op.drop_index("ix_sentinel_findings_site_id", table_name="sentinel_findings")
    op.drop_index("ix_sentinel_findings_tenant_id", table_name="sentinel_findings")
    op.drop_index("ix_sentinel_findings_scan_id", table_name="sentinel_findings")
    op.drop_table("sentinel_findings")

    op.drop_index("idx_sentinel_scans_tenant_site_received", table_name="sentinel_scans")
    op.drop_index("ix_sentinel_scans_received_at", table_name="sentinel_scans")
    op.drop_index("ix_sentinel_scans_site_id", table_name="sentinel_scans")
    op.drop_index("ix_sentinel_scans_tenant_id", table_name="sentinel_scans")
    op.drop_table("sentinel_scans")
