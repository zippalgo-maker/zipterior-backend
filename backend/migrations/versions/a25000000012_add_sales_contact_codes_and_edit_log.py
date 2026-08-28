"""add sales_contact_codes, sales_contact_edits, extend company_sales_contacts

Revision ID: a25000000012
Revises: a25000000011
Create Date: 2026-08-28

영업관리 통화기록 고도화:
- sales_contact_codes: 상태(통화완료/부재중/결번/오번호)와 TM내용
  코드(전화금지/다시전화 등)를 관리자가 화면에서 직접 추가할 수 있는
  코드 테이블. code_type으로 두 종류를 한 테이블에서 관리한다(둘 다
  "선택형 라벨 목록"이라는 같은 성격이라 테이블을 나눌 이유가 없음).
- company_sales_contacts: status_code_id/reason_code_id(위 코드 참조),
  content는 이제 굵게/색상 서식이 들어간 sanitize된 HTML을 저장한다
  (컬럼 타입은 그대로 TEXT). 수정 시각/수정자/수정사유를 레코드에도
  최신값으로 남긴다(목록에서 "수정됨" 표시용).
- sales_contact_edits: 통화기록 수정 이력. 수정할 때마다 수정 "이전"
  값을 스냅샷으로 남겨서, 누가 언제 무슨 사유로 뭘 바꿨는지 감사
  가능하게 한다.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a25000000012"
down_revision: Union[str, Sequence[str], None] = "a25000000011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sales_contact_codes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code_type", sa.String(length=20), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint("code_type IN ('status','reason')", name="ck_sales_contact_codes_type"),
    )
    op.create_index(
        "ix_sales_contact_codes_type_active",
        "sales_contact_codes",
        ["code_type", "is_active", "sort_order"],
    )

    op.add_column(
        "company_sales_contacts",
        sa.Column(
            "status_code_id",
            sa.BigInteger(),
            sa.ForeignKey("sales_contact_codes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "company_sales_contacts",
        sa.Column(
            "reason_code_id",
            sa.BigInteger(),
            sa.ForeignKey("sales_contact_codes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "company_sales_contacts",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "company_sales_contacts",
        sa.Column(
            "updated_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "company_sales_contacts",
        sa.Column("update_reason", sa.Text(), nullable=True),
    )

    op.create_table(
        "sales_contact_edits",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "contact_id",
            sa.BigInteger(),
            sa.ForeignKey("company_sales_contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "edited_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "edited_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("previous_content", sa.Text(), nullable=True),
        sa.Column(
            "previous_status_code_id",
            sa.BigInteger(),
            sa.ForeignKey("sales_contact_codes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "previous_reason_code_id",
            sa.BigInteger(),
            sa.ForeignKey("sales_contact_codes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_sales_contact_edits_contact_id_edited_at",
        "sales_contact_edits",
        ["contact_id", "edited_at"],
    )

    codes_table = sa.table(
        "sales_contact_codes",
        sa.column("code_type", sa.String),
        sa.column("label", sa.String),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        codes_table,
        [
            {"code_type": "status", "label": "통화완료", "sort_order": 1},
            {"code_type": "status", "label": "부재중", "sort_order": 2},
            {"code_type": "status", "label": "결번", "sort_order": 3},
            {"code_type": "status", "label": "오번호", "sort_order": 4},
            {"code_type": "reason", "label": "전화금지", "sort_order": 1},
            {"code_type": "reason", "label": "다시전화", "sort_order": 2},
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_sales_contact_edits_contact_id_edited_at", table_name="sales_contact_edits")
    op.drop_table("sales_contact_edits")
    op.drop_column("company_sales_contacts", "update_reason")
    op.drop_column("company_sales_contacts", "updated_by")
    op.drop_column("company_sales_contacts", "updated_at")
    op.drop_column("company_sales_contacts", "reason_code_id")
    op.drop_column("company_sales_contacts", "status_code_id")
    op.drop_index("ix_sales_contact_codes_type_active", table_name="sales_contact_codes")
    op.drop_table("sales_contact_codes")
