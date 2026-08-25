"""enhance reports for comment moderation

Revision ID: 44a47e6f2548
Revises: 3b1873f5f64c
"""

from alembic import op
import sqlalchemy as sa


revision = "44a47e6f2548"
down_revision = "3b1873f5f64c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reports",
        sa.Column(
            "handled_note",
            sa.Text(),
            nullable=True,
        ),
    )

    op.create_index(
        "idx_reports_target",
        "reports",
        ["target_type", "target_id"],
        unique=False,
    )

    op.create_index(
        "idx_reports_status_created",
        "reports",
        ["status", "created_at"],
        unique=False,
    )

    op.create_index(
        "idx_reports_reporter_created",
        "reports",
        ["reporter_user_id", "created_at"],
        unique=False,
    )

    op.create_index(
        "uq_reports_reporter_target",
        "reports",
        [
            "reporter_user_id",
            "target_type",
            "target_id",
        ],
        unique=True,
        postgresql_where=sa.text(
            "reporter_user_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_reports_reporter_target",
        table_name="reports",
    )

    op.drop_index(
        "idx_reports_reporter_created",
        table_name="reports",
    )

    op.drop_index(
        "idx_reports_status_created",
        table_name="reports",
    )

    op.drop_index(
        "idx_reports_target",
        table_name="reports",
    )

    op.drop_column(
        "reports",
        "handled_note",
    )
