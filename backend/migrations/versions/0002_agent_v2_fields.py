"""Add Agent v2 business fields and replay keys."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("dedup_key", sa.String(160), nullable=True))
    op.create_index("uq_messages_dedup_key", "messages", ["dedup_key"], unique=True)

    op.add_column("tickets", sa.Column("waiting_for", sa.String(32), nullable=True))
    op.add_column("tickets", sa.Column("current_question", sa.Text(), nullable=True))
    op.add_column(
        "tickets",
        sa.Column("policy_evidence", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column("tickets", sa.Column("graph_version", sa.String(32), nullable=True))

    op.add_column("audit_events", sa.Column("event_key", sa.String(200), nullable=True))
    op.add_column("audit_events", sa.Column("run_id", sa.String(36), nullable=True))
    op.add_column("audit_events", sa.Column("node_name", sa.String(64), nullable=True))
    op.create_index("uq_audit_events_event_key", "audit_events", ["event_key"], unique=True)
    op.create_index("ix_audit_events_run_id", "audit_events", ["run_id"])

    op.execute(
        "UPDATE tickets SET status = 'MANUAL_REVIEW', "
        "current_step = 'legacy_workflow_migrated' "
        "WHERE status NOT IN ('COMPLETED', 'REJECTED', 'FAILED', 'MANUAL_REVIEW')"
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_run_id", table_name="audit_events")
    op.drop_index("uq_audit_events_event_key", table_name="audit_events")
    op.drop_column("audit_events", "node_name")
    op.drop_column("audit_events", "run_id")
    op.drop_column("audit_events", "event_key")
    op.drop_column("tickets", "graph_version")
    op.drop_column("tickets", "policy_evidence")
    op.drop_column("tickets", "current_question")
    op.drop_column("tickets", "waiting_for")
    op.drop_index("uq_messages_dedup_key", table_name="messages")
    op.drop_column("messages", "dedup_key")
