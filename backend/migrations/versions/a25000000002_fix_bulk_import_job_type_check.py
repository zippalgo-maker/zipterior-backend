"""fix bulk_import_jobs job_type check constraint to allow company_portfolio_excel

Revision ID: a25000000002
Revises: a25000000001
Create Date: 2026-08-19

v2.5.0
- schemas.py의 BulkUploadCreateRequest.job_type과 excel_portfolio.py/service.py/
  worker.py는 처음부터 'company_portfolio_excel'을 정식 값으로 지원하도록
  작성돼 있었지만, bulk_import_jobs 테이블의 job_type CHECK 제약조건은
  'complex_excel'과 'company_portfolio_json' 두 값만 허용하고 있었다.
  이 값을 만드는 마이그레이션 파일 자체가 현재 migrations/versions에 없다
  (과거 이력 스쿼시로 유실 -- V2.5.0_PLAN.md의 alembic 이력 어긋남 기록 참고).
- 실제 발견 경위: 관리자 화면에 Excel 업로드 옵션을 추가한 뒤 운영에서
  실제로 업로드해보다가 POST /api/v1/admin/bulk-imports가 500
  (psycopg.errors.CheckViolation)으로 실패하는 것을 확인해서 찾음.
"""

from alembic import op


revision = "a25000000002"
down_revision = "a25000000001"
branch_labels = None
depends_on = None


OLD_CONSTRAINT = "bulk_import_jobs_job_type_check"


def upgrade() -> None:
    op.drop_constraint(OLD_CONSTRAINT, "bulk_import_jobs", type_="check")
    op.create_check_constraint(
        OLD_CONSTRAINT,
        "bulk_import_jobs",
        "job_type IN ('complex_excel', 'company_portfolio_json', 'company_portfolio_excel')",
    )


def downgrade() -> None:
    op.drop_constraint(OLD_CONSTRAINT, "bulk_import_jobs", type_="check")
    op.create_check_constraint(
        OLD_CONSTRAINT,
        "bulk_import_jobs",
        "job_type IN ('complex_excel', 'company_portfolio_json')",
    )
