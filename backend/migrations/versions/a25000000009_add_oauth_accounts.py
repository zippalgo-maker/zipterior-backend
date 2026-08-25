"""add user_oauth_accounts and make users.password_hash nullable for SNS login

Revision ID: a25000000009
Revises: a25000000008
Create Date: 2026-08-24

v2.5.57 -- SNS(카카오/네이버/Google) 로그인 실제 구현 착수. 사용자
지시: "SNS로그인 기능 만들고 실제 로그인 가능하도록 기능 셋팅
시작해" / "키는 내가 발급 받아서 나중에 주면 되잖아 일단 개발을 다
해놓고 키만 입력하면 되도록 진행". 자세한 설계는
app/modules/oauth/service.py 상단 주석, 배경/결정 근거는
V2.5.0_PLAN.md 참고.

- users.password_hash를 NOT NULL에서 nullable로 완화한다(SNS로만
  가입한 고객은 비밀번호가 없음). 기존 행은 전부 이미 값이 채워져
  있으므로 데이터 마이그레이션 불필요 -- 제약을 "넓히는" 방향이라
  기존 데이터에 영향 없음.
- user_oauth_accounts: 한 유저가 여러 SNS 계정을 연결할 수 있게
  1:N(user_id 여러 행 가능), 제공사+제공사쪽 유저ID 조합은 유일해야
  하므로(같은 카카오 계정이 두 유저에 중복 연결되면 안 됨) UNIQUE
  제약을 건다.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a25000000009"
down_revision: Union[str, Sequence[str], None] = "a25000000008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.Text(),
        nullable=True,
    )

    op.create_table(
        "user_oauth_accounts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("provider_user_id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
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
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_user_oauth_accounts_provider_identity"),
    )
    op.create_index(
        "ix_user_oauth_accounts_user_id",
        "user_oauth_accounts",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_oauth_accounts_user_id", table_name="user_oauth_accounts")
    op.drop_table("user_oauth_accounts")
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.Text(),
        nullable=False,
    )
