"""add authentication token tables

Revision ID: bac70dd2f593
Revises: dcc637a3b16c
Create Date: 2026-08-06 15:40:44.608095
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "bac70dd2f593"
down_revision: Union[str, Sequence[str], None] = "dcc637a3b16c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Refresh Token 원문은 저장하지 않고 SHA-256 해시만 저장
    op.create_table(
        "auth_refresh_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "token_hash",
            sa.String(length=64),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "token_family_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "parent_token_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "auth_refresh_tokens.id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "revoke_reason",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "replaced_by_token_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "ip_address",
            postgresql.INET(),
            nullable=True,
        ),
        sa.Column(
            "user_agent",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "device_name",
            sa.String(length=150),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "expires_at > issued_at",
            name="ck_auth_refresh_tokens_expiry",
        ),
    )

    op.create_index(
        "idx_auth_refresh_tokens_user",
        "auth_refresh_tokens",
        ["user_id", "expires_at"],
    )

    op.create_index(
        "idx_auth_refresh_tokens_family",
        "auth_refresh_tokens",
        ["token_family_id", "issued_at"],
    )

    op.create_index(
        "idx_auth_refresh_tokens_active",
        "auth_refresh_tokens",
        ["user_id", "revoked_at", "expires_at"],
    )

    # 이메일 인증, 비밀번호 재설정 등 일회성 토큰
    op.create_table(
        "auth_one_time_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "purpose",
            sa.String(length=40),
            nullable=False,
        ),
        sa.Column(
            "token_hash",
            sa.String(length=64),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "target_value",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "used_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "invalidated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
        sa.Column(
            "ip_address",
            postgresql.INET(),
            nullable=True,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            """
            purpose IN (
                'email_verification',
                'password_reset',
                'phone_verification',
                'email_change',
                'account_recovery'
            )
            """,
            name="ck_auth_one_time_tokens_purpose",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0",
            name="ck_auth_one_time_tokens_attempts",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_auth_one_time_tokens_expiry",
        ),
    )

    op.create_index(
        "idx_auth_one_time_tokens_user_purpose",
        "auth_one_time_tokens",
        ["user_id", "purpose", "created_at"],
    )

    op.create_index(
        "idx_auth_one_time_tokens_expiry",
        "auth_one_time_tokens",
        ["expires_at", "used_at", "invalidated_at"],
    )

    # 로그인 보안 및 운영 분석 기록
    op.create_table(
        "auth_login_attempts",
        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "email",
            postgresql.CITEXT(),
            nullable=False,
        ),
        sa.Column(
            "was_successful",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "failure_reason",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "ip_address",
            postgresql.INET(),
            nullable=True,
        ),
        sa.Column(
            "user_agent",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "device_name",
            sa.String(length=150),
            nullable=True,
        ),
        sa.Column(
            "request_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.create_index(
        "idx_auth_login_attempts_email_time",
        "auth_login_attempts",
        ["email", "created_at"],
    )

    op.create_index(
        "idx_auth_login_attempts_user_time",
        "auth_login_attempts",
        ["user_id", "created_at"],
    )

    op.create_index(
        "idx_auth_login_attempts_ip_time",
        "auth_login_attempts",
        ["ip_address", "created_at"],
    )

    op.create_index(
        "idx_auth_login_attempts_failure",
        "auth_login_attempts",
        ["was_successful", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_auth_login_attempts_failure",
        table_name="auth_login_attempts",
    )
    op.drop_index(
        "idx_auth_login_attempts_ip_time",
        table_name="auth_login_attempts",
    )
    op.drop_index(
        "idx_auth_login_attempts_user_time",
        table_name="auth_login_attempts",
    )
    op.drop_index(
        "idx_auth_login_attempts_email_time",
        table_name="auth_login_attempts",
    )
    op.drop_table("auth_login_attempts")

    op.drop_index(
        "idx_auth_one_time_tokens_expiry",
        table_name="auth_one_time_tokens",
    )
    op.drop_index(
        "idx_auth_one_time_tokens_user_purpose",
        table_name="auth_one_time_tokens",
    )
    op.drop_table("auth_one_time_tokens")

    op.drop_index(
        "idx_auth_refresh_tokens_active",
        table_name="auth_refresh_tokens",
    )
    op.drop_index(
        "idx_auth_refresh_tokens_family",
        table_name="auth_refresh_tokens",
    )
    op.drop_index(
        "idx_auth_refresh_tokens_user",
        table_name="auth_refresh_tokens",
    )
    op.drop_table("auth_refresh_tokens")
