"""add job_kind to complex_region_import_jobs for 네이버 검색 기반 이중검사

Revision ID: a25000000007
Revises: a25000000006
Create Date: 2026-08-22

v2.5.1 (같은 세션 이어서)
- 사용자 지시: 시군구 자동수집(법정동 cortarNo 훑기)과는 별개로, 네이버
  통합검색(fin.land.naver.com의 키워드 검색 API, 기존 단지 상세조회와
  같은 서버 -- 오늘 실제로 차단 안 됐던 곳)으로 같은 시군구를 한 번 더
  검색해서 우리 DB에 없는 단지가 있는지 대조하는 "이중검사" 기능 요청.
  실제 테스트로 효과 검증됨(양평군에서 진짜 누락 2건 발견 -- 분양중
  아파트(B01) 필터링 누락, V2.5.0_PLAN.md 참고).
- 기존 complex_region_import_jobs 테이블(법정동 훑기 job과 컬럼 구조가
  거의 동일 -- sigungu_query/status/summary(jsonb)/진행 카운트)을
  그대로 재사용하고 `job_kind` 컬럼만 추가해서 두 종류를 구분한다.
  이중검사는 "법정동 진행"이 아니라 "네이버 검색 페이지 진행"이라
  total_dong_count/processed_dong_count를 페이지 진행으로 재해석해서
  쓴다(새 컬럼 불필요).
"""

from alembic import op
import sqlalchemy as sa


revision = "a25000000007"
down_revision = "a25000000006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "complex_region_import_jobs",
        sa.Column(
            "job_kind",
            sa.String(length=20),
            nullable=False,
            server_default="sweep",
        ),
    )
    op.create_check_constraint(
        "ck_complex_region_import_jobs_kind",
        "complex_region_import_jobs",
        "job_kind IN ('sweep','cross_check')",
    )
    op.create_index(
        "idx_complex_region_import_jobs_kind",
        "complex_region_import_jobs",
        ["job_kind", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_complex_region_import_jobs_kind",
        table_name="complex_region_import_jobs",
    )
    op.drop_constraint(
        "ck_complex_region_import_jobs_kind",
        "complex_region_import_jobs",
        type_="check",
    )
    op.drop_column("complex_region_import_jobs", "job_kind")
