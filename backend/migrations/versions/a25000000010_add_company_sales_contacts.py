"""add company_sales_contacts (영업팀 업체 통화기록)

Revision ID: a25000000010
Revises: a25000000009
Create Date: 2026-08-28

집팔고360 영업팀이 등록된 업체(현재는 집테리어 업체)에 전화해서
집팔고360/집테리어를 설명(TM)한 뒤, 통화했다는 근거·누가 했는지·
통화 내용을 기록하기 위한 테이블. 회원가입/이관과 무관한 순수
영업활동 로그라 기존 companies/users 스키마는 건드리지 않는다.

- admin_user_id는 ON DELETE SET NULL: 담당자 계정이 나중에 삭제돼도
  통화 기록 자체(내용·시각)는 남아야 한다.
- contacted_at은 created_at과 별도로 둔다 -- 통화 직후가 아니라
  나중에 몰아서 기록하는 경우 실제 통화 시각을 다르게 남길 수 있어야
  하기 때문.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a25000000010"
down_revision: Union[str, Sequence[str], None] = "a25000000009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_sales_contacts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "company_id",
            sa.BigInteger(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "admin_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "contacted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_company_sales_contacts_company_id_contacted_at",
        "company_sales_contacts",
        ["company_id", "contacted_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_sales_contacts_company_id_contacted_at",
        table_name="company_sales_contacts",
    )
    op.drop_table("company_sales_contacts")
