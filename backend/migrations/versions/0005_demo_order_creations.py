"""Add idempotent demo order creation records."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "demo_order_creations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column("order_id", sa.String(36), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("scenario", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_demo_order_creations_request_id",
        "demo_order_creations",
        ["request_id"],
        unique=True,
    )
    op.create_index(
        "ix_demo_order_creations_order_id",
        "demo_order_creations",
        ["order_id"],
        unique=True,
    )
    op.create_index(
        "ix_demo_order_creations_created_by",
        "demo_order_creations",
        ["created_by"],
    )
    op.create_index(
        "ix_demo_order_creations_created_at",
        "demo_order_creations",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_demo_order_creations_created_at", table_name="demo_order_creations")
    op.drop_index("ix_demo_order_creations_created_by", table_name="demo_order_creations")
    op.drop_index("ix_demo_order_creations_order_id", table_name="demo_order_creations")
    op.drop_index("ix_demo_order_creations_request_id", table_name="demo_order_creations")
    op.drop_table("demo_order_creations")
