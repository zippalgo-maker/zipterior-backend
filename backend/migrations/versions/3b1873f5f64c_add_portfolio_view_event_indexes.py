"""add portfolio view event indexes

Revision ID: 3b1873f5f64c
Revises: bac70dd2f593
"""

from alembic import op


revision = "3b1873f5f64c"
down_revision = "bac70dd2f593"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_view_events_portfolio_user_date",
        "portfolio_view_events",
        ["portfolio_id", "user_id", "viewed_at"],
        unique=False,
    )
    op.create_index(
        "idx_view_events_portfolio_visitor_date",
        "portfolio_view_events",
        ["portfolio_id", "visitor_hash", "viewed_at"],
        unique=False,
    )
    op.create_index(
        "idx_view_events_portfolio_session_date",
        "portfolio_view_events",
        ["portfolio_id", "session_id", "viewed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_view_events_portfolio_session_date",
        table_name="portfolio_view_events",
    )
    op.drop_index(
        "idx_view_events_portfolio_visitor_date",
        table_name="portfolio_view_events",
    )
    op.drop_index(
        "idx_view_events_portfolio_user_date",
        table_name="portfolio_view_events",
    )
