"""add portfolio_content_blocks for raw-document-order rendering test

Revision ID: a25000000003
Revises: a25000000002
Create Date: 2026-08-20

v2.5.0 (테스트, additive)
- 오늘의집 원본 bpdDocument.contents 배열을 재정렬 없이 그대로 재현하는
  실험용 구조. 기존 portfolio_spaces/portfolio_images는 그대로 두고
  (검색·필터·공간분류용 역할 유지), 이 테이블은 상세페이지 원문 순서
  재현 테스트 전용이다.
- document_order: 원본 contents[] 배열 인덱스, 재정렬하지 않음.
- node_type: 크롤러가 넘겨준 원본 타입 문자열 그대로 (p/image/h2/h4/
  callout/hr/button 등, 처음 보는 값도 그대로 저장 -- 여기서 화이트리스트
  검증하지 않는다).
- block_type: 렌더러가 어떤 템플릿을 쓸지 고르기 위해 애플리케이션
  코드에서 계산해 넣는 정규화된 값(text/heading/image/callout/divider/
  link/unknown). node_type과 분리해 둬야 나중에 매핑 로직을 고칠 때
  원본 타입 값을 다시 볼 수 있다.
- raw_node(JSONB): 크롤러가 넘긴 원본 노드를 통째로 보존 -- 아직 해석
  못 하는 필드가 있어도 데이터를 버리지 않는다.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a25000000003"
down_revision = "a25000000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_content_blocks",

        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),

        sa.Column(
            "portfolio_id",
            sa.BigInteger(),
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),

        # 원본 contents[] 배열 인덱스. 재정렬하지 않음.
        sa.Column("document_order", sa.Integer(), nullable=False),

        # 원본 노드 타입 그대로 (p/image/h2/h4/callout/hr/button/...)
        sa.Column("node_type", sa.String(length=50), nullable=False),

        # 렌더러용 정규화 타입 (text/heading/image/callout/divider/link/unknown)
        sa.Column("block_type", sa.String(length=30), nullable=False),

        # 추출된 평문 (본문/제목/callout 등). 이미지 전용 블록은 비어있을 수 있음.
        sa.Column("text_content", sa.Text(), nullable=True),

        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("image_width", sa.Integer(), nullable=True),
        sa.Column("image_height", sa.Integer(), nullable=True),

        # 원본 노드 원문 그대로 (JSONB) -- 데이터 손실 방지용
        sa.Column("raw_node", postgresql.JSONB(), nullable=False),

        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),

        sa.UniqueConstraint(
            "portfolio_id",
            "document_order",
            name="uq_portfolio_content_blocks_portfolio_order",
        ),
    )

    op.create_index(
        "idx_portfolio_content_blocks_portfolio",
        "portfolio_content_blocks",
        ["portfolio_id", "document_order"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_portfolio_content_blocks_portfolio",
        table_name="portfolio_content_blocks",
    )
    op.drop_table("portfolio_content_blocks")
