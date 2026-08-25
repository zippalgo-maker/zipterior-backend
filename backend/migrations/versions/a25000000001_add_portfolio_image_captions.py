"""add per-image captions so text can be shown next to its own photo

Revision ID: a25000000001
Revises: a21800000001
Create Date: 2026-08-19

v2.5.0
- 지금까지 포트폴리오 화면은 공간(방)마다 "설명 한 덩어리 + 사진 그리드" 구조였다.
- 원본 게시글은 문장 하나하나가 바로 다음/직전 사진 한 장을 설명하는 구조가 흔하다
  (예: "신발장 반대편에는 전신거울로..." → 전신거울 사진).
- 방 단위로만 합치면 이 연결이 사라지므로, 사진 하나하나에 자체 설명을 붙일 수 있게
  portfolio_images에 description을 추가한다.
- portfolio_spaces.description은 그대로 "방 전체를 여는 소개 문단"(사진 여러 장을
  아우르는 일반적인 설명, 특정 사진 하나에 묶이지 않는 문장) 용도로 유지한다.
"""

from alembic import op
import sqlalchemy as sa


revision = "a25000000001"
down_revision = "a21800000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "portfolio_images",
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "portfolio_images",
        "description",
    )
