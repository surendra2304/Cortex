"""create the cognition tables that only existed in ORM metadata

Revision ID: 005_cognition_tables
Revises: 004_api_keys
Create Date: 2026-10-05 00:00:00.000000

Audit finding: alembic migrated 7 of the 13 ORM tables. ``approval_queue``,
``identity_links``, ``lead_scores``, ``memory_entries``, ``strategy_performance``
and ``workflow_runs`` were created only by ``Base.metadata.create_all``, so a
deployment that followed the documented migration path had a half-built schema.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005_cognition_tables"
down_revision: str | None = "004_api_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Portable JSON type: native JSONB on PostgreSQL, JSON elsewhere. Using
# sa.JSON() keeps the migration runnable against SQLite for verification.
JSONType = sa.JSON().with_variant(sa.dialects.postgresql.JSONB, "postgresql")


def upgrade() -> None:
    op.create_table(
        "identity_links",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_value", sa.String(length=255), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("metadata", JSONType, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
    )
    op.create_index("ix_identity_links_tenant_id", "identity_links", ["tenant_id"])
    op.create_index("ix_identity_links_source_value", "identity_links", ["source_value"])
    op.create_index("ix_identity_links_target_id", "identity_links", ["target_id"])

    op.create_table(
        "lead_scores",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("lead_id", sa.String(length=64), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("total_score", sa.Float(), nullable=False),
        sa.Column("behavior_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("firmographic_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("engagement_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("score_breakdown", JSONType, nullable=False),
        sa.Column("triggered_by", sa.String(length=64), nullable=False, server_default="event"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
    )
    op.create_index("ix_lead_scores_tenant_id", "lead_scores", ["tenant_id"])
    op.create_index("ix_lead_scores_lead_id", "lead_scores", ["lead_id"])

    op.create_table(
        "memory_entries",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("scope_id", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("content", JSONType, nullable=False),
        sa.Column("trust_label", sa.String(length=32), nullable=False, server_default="verified_telemetry"),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="cognitive_loop"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_memory_entries_tenant_id", "memory_entries", ["tenant_id"])
    op.create_index("ix_memory_entries_scope", "memory_entries", ["scope"])
    op.create_index("ix_memory_entries_scope_id", "memory_entries", ["scope_id"])
    op.create_index("ix_memory_entries_key", "memory_entries", ["key"])

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("workflow_name", sa.String(length=64), nullable=False),
        sa.Column("trigger_event", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("steps", JSONType, nullable=False),
        sa.Column("context", JSONType, nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_workflow_runs_tenant_id", "workflow_runs", ["tenant_id"])
    op.create_index("ix_workflow_runs_workflow_name", "workflow_runs", ["workflow_name"])
    op.create_index("ix_workflow_runs_state", "workflow_runs", ["state"])

    op.create_table(
        "approval_queue",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=64), nullable=True),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=128), nullable=False),
        sa.Column("params", JSONType, nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_refs", JSONType, nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("decision_by", sa.String(length=128), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_approval_queue_tenant_id", "approval_queue", ["tenant_id"])
    op.create_index("ix_approval_queue_workflow_run_id", "approval_queue", ["workflow_run_id"])

    op.create_table(
        "strategy_performance",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("strategy_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PROBATION"),
        sa.Column("total_executions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("successes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("recent_outcomes", JSONType, nullable=False),
        sa.Column(
            "last_updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
    )
    op.create_index("ix_strategy_performance_tenant_id", "strategy_performance", ["tenant_id"])
    op.create_index("ix_strategy_performance_strategy_key", "strategy_performance", ["strategy_key"])


def downgrade() -> None:
    for table in (
        "strategy_performance",
        "approval_queue",
        "workflow_runs",
        "memory_entries",
        "lead_scores",
        "identity_links",
    ):
        op.drop_table(table)
