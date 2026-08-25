"""add analytics system

Revision ID: 26c40b86b1c0
Revises: 5aed56a79fb5
Create Date: 2026-08-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "26c40b86b1c0"
down_revision: Union[str, None] = "5aed56a79fb5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analytics_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("anonymous_id", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("landing_path", sa.Text(), nullable=True),
        sa.Column("referrer", sa.Text(), nullable=True),
        sa.Column("utm_source", sa.String(length=150), nullable=True),
        sa.Column("utm_medium", sa.String(length=150), nullable=True),
        sa.Column("utm_campaign", sa.String(length=150), nullable=True),
        sa.Column("device_type", sa.String(length=30), nullable=True),
        sa.Column("browser", sa.String(length=100), nullable=True),
        sa.Column("os", sa.String(length=100), nullable=True),
        sa.Column("region_code", sa.String(length=30), nullable=True),
        sa.Column("consent_status", sa.String(length=30), nullable=False, server_default="essential"),
    )

    op.create_table(
        "analytics_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_uuid", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analytics_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_name", sa.String(length=100), nullable=False),
        sa.Column("event_category", sa.String(length=50), nullable=False),
        sa.Column("page_path", sa.Text(), nullable=True),
        sa.Column("target_type", sa.String(length=50), nullable=True),
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "company_id",
            sa.BigInteger(),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "portfolio_id",
            sa.BigInteger(),
            sa.ForeignKey("portfolios.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "complex_id",
            sa.BigInteger(),
            sa.ForeignKey("apartment_complexes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "apartment_type_id",
            sa.BigInteger(),
            sa.ForeignKey("apartment_types.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("properties", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )

    op.create_table(
        "analytics_daily_metrics",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("metric_key", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=True),
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        sa.Column("region_code", sa.String(length=30), nullable=True),
        sa.Column("impression_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("hover_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("click_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("detail_view_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("like_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("favorite_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("phone_click_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("chat_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("estimate_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("unique_user_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("average_duration_seconds", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("conversion_rate", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint(
            "metric_date",
            "metric_key",
            "target_type",
            "target_id",
            "region_code",
            name="uq_analytics_daily_metric",
        ),
    )

    op.create_table(
        "analytics_funnels",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("funnel_key", sa.String(length=100), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )

    op.create_table(
        "analytics_funnel_steps",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "funnel_id",
            sa.BigInteger(),
            sa.ForeignKey("analytics_funnels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("event_name", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=150), nullable=False),
        sa.Column("condition_config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("funnel_id", "step_order", name="uq_analytics_funnel_step_order"),
    )

    op.create_table(
        "analytics_metric_definitions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("metric_key", sa.String(length=100), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("calculation_type", sa.String(length=50), nullable=False),
        sa.Column("calculation_config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )

    op.create_table(
        "analytics_collection_settings",
        sa.Column("setting_key", sa.String(length=100), primary_key=True),
        sa.Column("display_name", sa.String(length=150), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("settings", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )

    op.create_index("idx_analytics_sessions_user", "analytics_sessions", ["user_id", "started_at"])
    op.create_index("idx_analytics_sessions_anonymous", "analytics_sessions", ["anonymous_id", "started_at"])

    op.create_index(
        "idx_analytics_events_session_time",
        "analytics_events",
        ["session_id", "occurred_at"],
    )
    op.create_index(
        "idx_analytics_events_name_time",
        "analytics_events",
        ["event_name", "occurred_at"],
    )
    op.create_index(
        "idx_analytics_events_company_time",
        "analytics_events",
        ["company_id", "occurred_at"],
    )
    op.create_index(
        "idx_analytics_events_portfolio_time",
        "analytics_events",
        ["portfolio_id", "occurred_at"],
    )
    op.create_index(
        "idx_analytics_events_complex_time",
        "analytics_events",
        ["complex_id", "occurred_at"],
    )
    op.create_index(
        "idx_analytics_daily_metrics_date",
        "analytics_daily_metrics",
        ["metric_date", "metric_key"],
    )

    op.execute(
        """
        INSERT INTO analytics_collection_settings
        (setting_key, display_name, is_enabled, settings)
        VALUES
        (
            'default_tracking',
            '기본 행동분석 수집',
            TRUE,
            '{
                "batch_size": 20,
                "flush_interval_seconds": 5,
                "hover_minimum_ms": 1000,
                "raw_event_retention_days": 180,
                "track_scroll_depth": true,
                "track_map_move": true
            }'::jsonb
        )
        """
    )

    op.execute(
        """
        INSERT INTO analytics_funnels
        (funnel_key, display_name, description)
        VALUES
        (
            'estimate_conversion',
            '견적문의 전환',
            '견적 팝업을 열고 최종 접수하기까지의 단계별 전환'
        )
        """
    )

    op.execute(
        """
        INSERT INTO analytics_funnel_steps
        (funnel_id, step_order, event_name, display_name)
        SELECT id, 1, 'estimate_modal_open', '견적 팝업 열기'
        FROM analytics_funnels
        WHERE funnel_key = 'estimate_conversion'
        UNION ALL
        SELECT id, 2, 'estimate_step_complete', '의뢰정보 입력 완료'
        FROM analytics_funnels
        WHERE funnel_key = 'estimate_conversion'
        UNION ALL
        SELECT id, 3, 'estimate_company_select', '업체 선택'
        FROM analytics_funnels
        WHERE funnel_key = 'estimate_conversion'
        UNION ALL
        SELECT id, 4, 'estimate_submit', '견적 접수 완료'
        FROM analytics_funnels
        WHERE funnel_key = 'estimate_conversion'
        """
    )

    op.execute(
        """
        INSERT INTO analytics_metric_definitions
        (metric_key, display_name, description, calculation_type, calculation_config)
        VALUES
        (
            'portfolio_click_rate',
            '포트폴리오 클릭률',
            '포트폴리오 노출 대비 클릭 비율',
            'ratio',
            '{"numerator":"portfolio_click","denominator":"portfolio_impression"}'::jsonb
        ),
        (
            'company_detail_conversion_rate',
            '업체 상세 전환율',
            '업체 노출 대비 업체 상세 열기 비율',
            'ratio',
            '{"numerator":"company_detail_open","denominator":"company_impression"}'::jsonb
        ),
        (
            'estimate_conversion_rate',
            '견적 전환율',
            '견적 팝업 열기 대비 최종 접수 비율',
            'ratio',
            '{"numerator":"estimate_submit","denominator":"estimate_modal_open"}'::jsonb
        )
        """
    )


def downgrade() -> None:
    op.drop_index("idx_analytics_daily_metrics_date", table_name="analytics_daily_metrics")
    op.drop_index("idx_analytics_events_complex_time", table_name="analytics_events")
    op.drop_index("idx_analytics_events_portfolio_time", table_name="analytics_events")
    op.drop_index("idx_analytics_events_company_time", table_name="analytics_events")
    op.drop_index("idx_analytics_events_name_time", table_name="analytics_events")
    op.drop_index("idx_analytics_events_session_time", table_name="analytics_events")
    op.drop_index("idx_analytics_sessions_anonymous", table_name="analytics_sessions")
    op.drop_index("idx_analytics_sessions_user", table_name="analytics_sessions")

    op.drop_table("analytics_collection_settings")
    op.drop_table("analytics_metric_definitions")
    op.drop_table("analytics_funnel_steps")
    op.drop_table("analytics_funnels")
    op.drop_table("analytics_daily_metrics")
    op.drop_table("analytics_events")
    op.drop_table("analytics_sessions")
