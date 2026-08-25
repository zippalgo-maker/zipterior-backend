"""add complex_region_import_jobs for 시군구 기준 네이버부동산 단지 자동수집

Revision ID: a25000000005
Revises: a25000000004
Create Date: 2026-08-21

v2.5.1
- 기존 "단지 추가" 화면은 관리자가 단지 하나씩 카카오 주소검색 -> 네이버
  상세조회로 등록하는 수동 흐름이다. 이번에 추가하는 기능은 시군구
  이름 하나만 입력하면 그 안의 아파트+오피스텔 단지 전체를 서버가
  백그라운드에서 자동 수집해 등록하는 것 -- bulk_import_jobs와 컬럼
  구조가 근본적으로 달라(포트폴리오/이미지 개념이 없고, 법정동 단위
  진행 + 단지 단위 진행 두 겹으로 추적) 별도 테이블로 둔다.
- 처리 흐름: legal_dong_client로 시군구 -> 법정동(cortarNo) 목록 조회 ->
  naver_complex_client.list_complexes_by_cortarno로 법정동마다 단지
  목록(단지번호) 수집 -> 단지번호 기준 중복 제거 -> 단지마다
  lookup_by_complex_number로 상세조회 -> AdminComplexService로 저장.
- 개별 단지 실패 사유는 별도 레코드 테이블 없이 summary(jsonb)의
  failed_complexes 배열에 간단히 남긴다(대량등록처럼 건별 검수 화면이
  필요한 기능이 아니라서 단순화함).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a25000000005"
down_revision = "a25000000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "complex_region_import_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "requested_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("sigungu_query", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="queued",
        ),
        sa.Column(
            "total_dong_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "processed_dong_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "processed_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "duplicate_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "summary",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','completed','completed_with_errors',"
            "'failed','cancelled')",
            name="ck_complex_region_import_jobs_status",
        ),
    )
    op.create_index(
        "idx_complex_region_import_jobs_status",
        "complex_region_import_jobs",
        ["status", "created_at"],
    )
    op.execute(
        """
        CREATE TRIGGER trg_complex_region_import_jobs_updated_at
        BEFORE UPDATE ON complex_region_import_jobs
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_complex_region_import_jobs_updated_at "
        "ON complex_region_import_jobs"
    )
    op.drop_index(
        "idx_complex_region_import_jobs_status",
        table_name="complex_region_import_jobs",
    )
    op.drop_table("complex_region_import_jobs")
