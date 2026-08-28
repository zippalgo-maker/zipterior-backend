"""add reviews, estimate_milestones, users.notification_prefs

Revision ID: a25000000010
Revises: a25000000009
Create Date: 2026-08-26

v1.10.1 -- 목업(집팔고360 견적 매칭)에서 확정했던 화면 중 백엔드 자체가
없어서 미뤄뒀던 3개(시공 진행상황, 리뷰, 알림 설정)를 사용자 지시
("이것도 만들어 추가해서 최종 확인하자")로 이번에 채운다.

- users.notification_prefs: 알림 설정 화면(목업 15번)의 3개 토글(견적
  응답/시공업체 댓글/현장 사진) 상태 저장. 마케팅 토글은 이미 있는
  users.marketing_agreed를 그대로 씀 -- 새 컬럼 불필요. JSONB로 넣어서
  나중에 토글 종류가 늘어도 스키마 변경 없이 확장 가능하게 함.
- reviews: "준공 완료 후 작성 가능"(목업 13번 화면 하단 CTA) 검증을
  위해 estimate_request_id를 FK+UNIQUE로 묶는다(견적 1건당 리뷰 1개,
  서비스 레벨에서 estimate_requests.status='closed'인 본인 견적에만
  쓸 수 있도록 검증 -- DB 레벨 제약은 아님, service.py에서 체크).
- estimate_milestones: 5단계 공정(계약완료/철거/설비전기/목공마감/
  준공청소) 진행상태. 댓글은 새 테이블 안 만들고 기존 chat_rooms/
  chat_messages를 그대로 재사용(고객-업체 1:1 상담방이 이미 있는
  구조라 거기 이어서 대화하면 됨, estimate_request_id 연결 컬럼도
  chat_rooms에 이미 있어서 이번 마이그레이션에서 손댈 것 없음).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a25000000010"
down_revision: Union[str, Sequence[str], None] = "a25000000009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "notification_prefs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text(
                '\'{"estimate_response": true, "company_comment": true, "photo_upload": true}\'::jsonb'
            ),
        ),
    )

    op.create_table(
        "reviews",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "estimate_request_id",
            sa.BigInteger(),
            sa.ForeignKey("estimate_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.BigInteger(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "portfolio_id",
            sa.BigInteger(),
            sa.ForeignKey("portfolios.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_reviews_rating_range"),
        sa.UniqueConstraint("estimate_request_id", name="uq_reviews_estimate_request_id"),
    )
    op.create_index("ix_reviews_company_id", "reviews", ["company_id"])
    op.create_index("ix_reviews_customer_id", "reviews", ["customer_id"])

    op.create_table(
        "estimate_milestones",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "estimate_request_id",
            sa.BigInteger(),
            sa.ForeignKey("estimate_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("phase_key", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("estimate_request_id", "phase_key", name="uq_estimate_milestones_request_phase"),
    )
    op.create_index("ix_estimate_milestones_request_id", "estimate_milestones", ["estimate_request_id"])


def downgrade() -> None:
    op.drop_index("ix_estimate_milestones_request_id", table_name="estimate_milestones")
    op.drop_table("estimate_milestones")
    op.drop_index("ix_reviews_customer_id", table_name="reviews")
    op.drop_index("ix_reviews_company_id", table_name="reviews")
    op.drop_table("reviews")
    op.drop_column("users", "notification_prefs")
