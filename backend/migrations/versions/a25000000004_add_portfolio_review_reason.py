"""add portfolios.review_reason for bulk-import records that need manual completion

Revision ID: a25000000004
Revises: a25000000003
Create Date: 2026-08-20

v2.5.0
- 대량등록 시 주소(단지)를 확정하지 못한 포트폴리오는 지도에 마커를 꽂을 수
  없다. 예전엔 이런 경우도 그대로 'approved'/'pending'으로 마무리돼 버렸는데,
  지금부터는 status='draft'로 남기고 이 컬럼에 짧은 사유 코드를 남긴다.
- 값 예시: 'address_missing'(원본에 주소 자체가 없음),
  'complex_match_failed'(주소는 있는데 단지 매칭/지오코딩 실패).
  화이트리스트로 강하게 제약하지 않는다 -- 새 사유가 필요할 때 마이그레이션
  없이 문자열만 추가하면 되도록 CHECK 제약 없이 자유 텍스트로 둔다.
- NULL이면 정상 처리된 포트폴리오(기존 동작과 동일). 업체가 직접 고쳐서
  제출하거나(draft -> 수정 -> 제출 -> 기존 검수 흐름) 관리자가 직접 단지를
  지정하면(즉시 승인) 이 값을 NULL로 비운다 -- portfolios/service.py의
  update_portfolio, admin/portfolio_service.py의 새 단지 지정 처리 참고.
"""

from alembic import op
import sqlalchemy as sa


revision = "a25000000004"
down_revision = "a25000000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "portfolios",
        sa.Column("review_reason", sa.String(length=50), nullable=True),
    )
    op.create_index(
        "idx_portfolios_review_reason",
        "portfolios",
        ["review_reason"],
        postgresql_where=sa.text("review_reason IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_portfolios_review_reason", table_name="portfolios")
    op.drop_column("portfolios", "review_reason")
