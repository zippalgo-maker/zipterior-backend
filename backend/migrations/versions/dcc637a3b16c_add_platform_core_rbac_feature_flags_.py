"""add platform core rbac feature flags audit outbox

Revision ID: dcc637a3b16c
Revises: 5aed56a79fb5
Create Date: 2026-08-06 14:00:20.393588
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "dcc637a3b16c"
down_revision: Union[str, Sequence[str], None] = "5aed56a79fb5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------------------------------------
    # 1. 사용자별 권한 예외 설정
    # 역할 권한보다 우선하여 특정 사용자에게 허용 또는 차단
    # ---------------------------------------------------------
    op.create_table(
        "user_permission_overrides",
        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "permission_id",
            sa.BigInteger(),
            sa.ForeignKey("admin_permissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "effect",
            sa.String(length=10),
            nullable=False,
        ),
        sa.Column(
            "reason",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "starts_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "ends_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "effect IN ('allow', 'deny')",
            name="ck_user_permission_overrides_effect",
        ),
        sa.UniqueConstraint(
            "user_id",
            "permission_id",
            name="uq_user_permission_override",
        ),
    )

    op.create_index(
        "idx_user_permission_overrides_user",
        "user_permission_overrides",
        ["user_id", "is_active"],
    )

    # ---------------------------------------------------------
    # 2. Feature Flag 적용 범위
    # 전체 기능 설정 아래에서 역할·지역·메뉴별 예외 적용
    # ---------------------------------------------------------
    op.create_table(
        "system_feature_scopes",
        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "feature_key",
            sa.String(length=100),
            sa.ForeignKey(
                "system_features.feature_key",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "scope_type",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "scope_value",
            sa.String(length=150),
            nullable=False,
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "read_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "write_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "settings",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "starts_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "ends_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            """
            scope_type IN (
                'role',
                'company_grade',
                'region',
                'channel',
                'user',
                'environment'
            )
            """,
            name="ck_system_feature_scopes_type",
        ),
        sa.UniqueConstraint(
            "feature_key",
            "scope_type",
            "scope_value",
            name="uq_system_feature_scope",
        ),
    )

    op.create_index(
        "idx_system_feature_scopes_lookup",
        "system_feature_scopes",
        ["feature_key", "scope_type", "scope_value"],
    )

    # ---------------------------------------------------------
    # 3. 기존 관리자 감사로그 보강
    # ---------------------------------------------------------
    op.add_column(
        "admin_action_logs",
        sa.Column(
            "request_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.add_column(
        "admin_action_logs",
        sa.Column(
            "reason",
            sa.Text(),
            nullable=True,
        ),
    )

    op.add_column(
        "admin_action_logs",
        sa.Column(
            "user_agent",
            sa.Text(),
            nullable=True,
        ),
    )

    op.add_column(
        "admin_action_logs",
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.create_index(
        "idx_admin_action_logs_admin_time",
        "admin_action_logs",
        ["admin_user_id", "created_at"],
    )

    op.create_index(
        "idx_admin_action_logs_target_time",
        "admin_action_logs",
        ["target_type", "target_id", "created_at"],
    )

    op.create_index(
        "idx_admin_action_logs_request",
        "admin_action_logs",
        ["request_id"],
    )

    # ---------------------------------------------------------
    # 4. Event Outbox
    # 업무 데이터와 이벤트를 동일 트랜잭션으로 저장
    # ---------------------------------------------------------
    op.create_table(
        "event_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "event_name",
            sa.String(length=150),
            nullable=False,
        ),
        sa.Column(
            "event_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "aggregate_type",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "aggregate_id",
            sa.String(length=150),
            nullable=False,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "locked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "locked_by",
            sa.String(length=150),
            nullable=True,
        ),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            """
            status IN (
                'pending',
                'processing',
                'completed',
                'failed',
                'cancelled'
            )
            """,
            name="ck_event_outbox_status",
        ),
    )

    op.create_index(
        "idx_event_outbox_pending",
        "event_outbox",
        ["status", "available_at", "created_at"],
    )

    op.create_index(
        "idx_event_outbox_aggregate",
        "event_outbox",
        ["aggregate_type", "aggregate_id", "created_at"],
    )

    op.create_index(
        "idx_event_outbox_event_name",
        "event_outbox",
        ["event_name", "created_at"],
    )

    # ---------------------------------------------------------
    # 5. 이벤트 소비 중복 방지
    # 같은 Worker가 동일 이벤트를 두 번 처리하지 않도록 관리
    # ---------------------------------------------------------
    op.create_table(
        "event_consumptions",
        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("event_outbox.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "consumer_name",
            sa.String(length=150),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="completed",
        ),
        sa.Column(
            "result",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "status IN ('completed', 'failed', 'skipped')",
            name="ck_event_consumptions_status",
        ),
        sa.UniqueConstraint(
            "event_id",
            "consumer_name",
            name="uq_event_consumption",
        ),
    )

    op.create_index(
        "idx_event_consumptions_consumer",
        "event_consumptions",
        ["consumer_name", "processed_at"],
    )

    # ---------------------------------------------------------
    # 6. Platform Core 관리자 권한 초기값
    # ---------------------------------------------------------
    op.execute(
        """
        INSERT INTO admin_permissions
            (permission_key, display_name, description)
        VALUES
            (
                'rbac.view',
                '역할·권한 조회',
                '관리자 역할과 권한 설정을 조회합니다.'
            ),
            (
                'rbac.update',
                '역할·권한 변경',
                '관리자 역할과 권한 설정을 변경합니다.'
            ),
            (
                'feature_flags.manage',
                '기능 설정 관리',
                '댓글·좋아요·리뷰 등 기능 설정을 변경합니다.'
            ),
            (
                'audit_logs.view',
                '감사로그 조회',
                '관리자 변경 이력과 감사로그를 조회합니다.'
            ),
            (
                'event_outbox.view',
                '이벤트 처리 현황 조회',
                '이벤트 아웃박스 처리 현황을 조회합니다.'
            ),
            (
                'event_outbox.retry',
                '실패 이벤트 재처리',
                '실패한 이벤트를 다시 처리하도록 요청합니다.'
            ),
            (
                'analytics.view',
                '데이터 분석 조회',
                '사용자 행동과 서비스 성과 분석을 조회합니다.'
            )
        ON CONFLICT (permission_key) DO NOTHING
        """
    )

    # 최고관리자 역할에 모든 Platform Core 권한 부여
    op.execute(
        """
        INSERT INTO admin_role_permissions (role_id, permission_id)
        SELECT
            roles.id,
            permissions.id
        FROM admin_roles AS roles
        CROSS JOIN admin_permissions AS permissions
        WHERE roles.role_key = 'super_admin'
          AND permissions.permission_key IN (
              'rbac.view',
              'rbac.update',
              'feature_flags.manage',
              'audit_logs.view',
              'event_outbox.view',
              'event_outbox.retry',
              'analytics.view'
          )
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    # 최고관리자에게 추가한 Platform Core 권한 연결 제거
    op.execute(
        """
        DELETE FROM admin_role_permissions
        WHERE permission_id IN (
            SELECT id
            FROM admin_permissions
            WHERE permission_key IN (
                'rbac.view',
                'rbac.update',
                'feature_flags.manage',
                'audit_logs.view',
                'event_outbox.view',
                'event_outbox.retry',
                'analytics.view'
            )
        )
        """
    )

    # 이번 마이그레이션에서 추가한 권한 제거
    op.execute(
        """
        DELETE FROM admin_permissions
        WHERE permission_key IN (
            'rbac.view',
            'rbac.update',
            'feature_flags.manage',
            'audit_logs.view',
            'event_outbox.view',
            'event_outbox.retry',
            'analytics.view'
        )
        """
    )

    op.drop_index(
        "idx_event_consumptions_consumer",
        table_name="event_consumptions",
    )
    op.drop_table("event_consumptions")

    op.drop_index(
        "idx_event_outbox_event_name",
        table_name="event_outbox",
    )
    op.drop_index(
        "idx_event_outbox_aggregate",
        table_name="event_outbox",
    )
    op.drop_index(
        "idx_event_outbox_pending",
        table_name="event_outbox",
    )
    op.drop_table("event_outbox")

    op.drop_index(
        "idx_admin_action_logs_request",
        table_name="admin_action_logs",
    )
    op.drop_index(
        "idx_admin_action_logs_target_time",
        table_name="admin_action_logs",
    )
    op.drop_index(
        "idx_admin_action_logs_admin_time",
        table_name="admin_action_logs",
    )

    op.drop_column("admin_action_logs", "metadata")
    op.drop_column("admin_action_logs", "user_agent")
    op.drop_column("admin_action_logs", "reason")
    op.drop_column("admin_action_logs", "request_id")

    op.drop_index(
        "idx_system_feature_scopes_lookup",
        table_name="system_feature_scopes",
    )
    op.drop_table("system_feature_scopes")

    op.drop_index(
        "idx_user_permission_overrides_user",
        table_name="user_permission_overrides",
    )
    op.drop_table("user_permission_overrides")
