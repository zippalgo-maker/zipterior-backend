"""add portfolio spaces for structured portfolio contents

Revision ID: a21800000001
Revises: 44a47e6f2548
Create Date: 2026-08-12

v2.1.8
- 공간별 포트폴리오 구조
- 공간별 설명
- 동일 공간 다중 생성 (방1, 방2, 거실1, 거실2 ...)
- 이미지와 공간 직접 연결
- 향후 관리자 Excel + ZIP 대량등록 공통 구조
"""

from alembic import op
import sqlalchemy as sa


revision = "a21800000001"
down_revision = "44a47e6f2548"
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ========================================================
    # portfolio_spaces
    # ========================================================

    op.create_table(
        "portfolio_spaces",

        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
        ),

        sa.Column(
            "portfolio_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "portfolios.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),

        # 거실 / 주방 / 안방 / 방 / 욕실 / 드레스룸 / 현관 / 기타 등
        sa.Column(
            "space_code",
            sa.String(length=50),
            nullable=False,
        ),

        # 고객 및 관리자 화면에 사용할 기본 명칭
        # 예: 거실, 방, 욕실
        sa.Column(
            "space_name",
            sa.String(length=100),
            nullable=False,
        ),

        # 동일 종류 공간의 순번
        # 최초 1개만 있을 때도 DB에서는 1
        # 추가 시 방1/방2, 거실1/거실2 형태로 UI에서 표현
        sa.Column(
            "space_number",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),

        # 공간별 상세 설명
        # 값이 없으면 고객 화면에서 설명 영역 자체를 노출하지 않음
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),

        # 포트폴리오 내 공간 표시 순서
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),

        sa.CheckConstraint(
            "space_number >= 1",
            name="ck_portfolio_spaces_number_positive",
        ),

        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_portfolio_spaces_sort_nonnegative",
        ),

        sa.UniqueConstraint(
            "portfolio_id",
            "space_code",
            "space_number",
            name="uq_portfolio_spaces_portfolio_code_number",
        ),
    )

    op.create_index(
        "idx_portfolio_spaces_portfolio",
        "portfolio_spaces",
        [
            "portfolio_id",
            "sort_order",
            "id",
        ],
    )

    # ========================================================
    # portfolio_images → portfolio_spaces 연결
    #
    # 기존 room_code는 즉시 삭제하지 않는다.
    # 기존 코드 호환 + 안전한 단계적 migration을 위해 유지.
    # ========================================================

    op.add_column(
        "portfolio_images",
        sa.Column(
            "portfolio_space_id",
            sa.BigInteger(),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_portfolio_images_space",
        "portfolio_images",
        "portfolio_spaces",
        ["portfolio_space_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "idx_portfolio_images_space",
        "portfolio_images",
        [
            "portfolio_space_id",
            "sort_order",
            "id",
        ],
    )


def downgrade() -> None:

    op.drop_index(
        "idx_portfolio_images_space",
        table_name="portfolio_images",
    )

    op.drop_constraint(
        "fk_portfolio_images_space",
        "portfolio_images",
        type_="foreignkey",
    )

    op.drop_column(
        "portfolio_images",
        "portfolio_space_id",
    )

    op.drop_index(
        "idx_portfolio_spaces_portfolio",
        table_name="portfolio_spaces",
    )

    op.drop_table(
        "portfolio_spaces",
    )
