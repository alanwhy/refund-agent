"""Add submitted order references and technical manual review tasks."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("submitted_order_number", sa.String(50), nullable=True))
    op.create_index(
        "ix_tickets_submitted_order_number",
        "tickets",
        ["submitted_order_number"],
    )
    op.execute(
        """
        UPDATE tickets AS ticket
        SET submitted_order_number = orders.order_number
        FROM orders
        WHERE ticket.order_id = orders.id
          AND ticket.submitted_order_number IS NULL
        """
    )
    op.execute(
        """
        UPDATE tickets AS ticket
        SET submitted_order_number = candidate.order_number
        FROM (
            SELECT DISTINCT ON (ticket_id)
                ticket_id,
                details->'arguments'->>'order_number' AS order_number
            FROM audit_events
            WHERE action = 'tool.requested'
              AND details->>'tool' = 'SubmitRefundContext'
              AND details->'arguments'->>'order_number' ~ '^ORD-[A-Z0-9-]+$'
            ORDER BY ticket_id, created_at DESC
        ) AS candidate
        WHERE ticket.id = candidate.ticket_id
          AND ticket.submitted_order_number IS NULL
        """
    )

    op.create_table(
        "manual_review_tasks",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("ticket_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("submitted_order_number", sa.String(50), nullable=True),
        sa.Column("technical_summary", sa.String(500), nullable=False),
        sa.Column("assigned_to", sa.String(36), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.String(36), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"]),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_manual_review_tasks_ticket_id",
        "manual_review_tasks",
        ["ticket_id"],
        unique=True,
    )
    op.create_index("ix_manual_review_tasks_status", "manual_review_tasks", ["status"])
    op.create_index("ix_manual_review_tasks_category", "manual_review_tasks", ["category"])
    op.create_index("ix_manual_review_tasks_assigned_to", "manual_review_tasks", ["assigned_to"])
    op.create_index("ix_manual_review_tasks_created_at", "manual_review_tasks", ["created_at"])

    op.execute(
        """
        INSERT INTO manual_review_tasks (
            id, ticket_id, status, category, submitted_order_number,
            technical_summary, version, created_at, updated_at
        )
        SELECT
            md5('manual-review-' || ticket.id),
            ticket.id,
            'PENDING',
            CASE
                WHEN EXISTS (
                    SELECT 1 FROM refund_requests AS refund
                    WHERE refund.ticket_id = ticket.id AND refund.status = 'UNKNOWN'
                ) THEN 'PAYMENT_UNKNOWN'
                WHEN EXISTS (
                    SELECT 1 FROM audit_events AS audit
                    WHERE audit.ticket_id = ticket.id
                      AND audit.action = 'security.tool_rejected'
                ) THEN 'SECURITY_REJECTION'
                WHEN EXISTS (
                    SELECT 1 FROM audit_events AS audit
                    WHERE audit.ticket_id = ticket.id
                      AND audit.action = 'agent.manual_review'
                      AND audit.details->>'reason' IN (
                          'MODEL_UNAVAILABLE', 'INVALID_MODEL_MESSAGE', 'AGENT_STEP_LIMIT'
                      )
                ) THEN 'MODEL_FAILURE'
                ELSE 'DATA_INCONSISTENCY'
            END,
            ticket.submitted_order_number,
            CASE
                WHEN EXISTS (
                    SELECT 1 FROM refund_requests AS refund
                    WHERE refund.ticket_id = ticket.id AND refund.status = 'UNKNOWN'
                ) THEN '支付结果未知，需要核对支付渠道结果。'
                WHEN EXISTS (
                    SELECT 1 FROM audit_events AS audit
                    WHERE audit.ticket_id = ticket.id
                      AND audit.action = 'security.tool_rejected'
                ) THEN '智能助手调用未通过安全校验，需要人工核查。'
                WHEN EXISTS (
                    SELECT 1 FROM audit_events AS audit
                    WHERE audit.ticket_id = ticket.id
                      AND audit.action = 'agent.manual_review'
                      AND audit.details->>'reason' IN (
                          'MODEL_UNAVAILABLE', 'INVALID_MODEL_MESSAGE', 'AGENT_STEP_LIMIT'
                      )
                ) THEN '智能助手服务异常，需要人工继续处理。'
                ELSE '工单数据状态不完整，需要人工核查。'
            END,
            1,
            ticket.created_at,
            ticket.updated_at
        FROM tickets AS ticket
        WHERE ticket.status = 'MANUAL_REVIEW'
        ON CONFLICT (ticket_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_manual_review_tasks_created_at", table_name="manual_review_tasks")
    op.drop_index("ix_manual_review_tasks_assigned_to", table_name="manual_review_tasks")
    op.drop_index("ix_manual_review_tasks_category", table_name="manual_review_tasks")
    op.drop_index("ix_manual_review_tasks_status", table_name="manual_review_tasks")
    op.drop_index("ix_manual_review_tasks_ticket_id", table_name="manual_review_tasks")
    op.drop_table("manual_review_tasks")
    op.drop_index("ix_tickets_submitted_order_number", table_name="tickets")
    op.drop_column("tickets", "submitted_order_number")
