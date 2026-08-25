"""add dong_codes_filter to complex_region_import_jobs for 실패 법정동 재시도

Revision ID: a25000000008
Revises: a25000000007
Create Date: 2026-08-22

v2.5.1 (같은 세션 이어서)
- 사용자 지시: 고양시 자동수집 job에서 실패한 법정동 8개를 확인해보니
  전부 "네이버 단지목록 요청에 실패했습니다. (HTTP 307)" -- 이미 있는
  차단(abuse) 탐지에 정확히 걸려서 8회 연속 실패로 쿨다운이 걸렸던
  바로 그 8개 법정동이었고(로그 실측 확인), 쿨다운 후 재개는 성공했지만
  이 8개는 재시도되지 않은 채 job 안에 "실패"로 남아있었음(정부 법정동
  코드 API는 정상 -- 애초에 이게 실패했으면 job 자체가 시작도 못 했을
  것. "그 읍면동에 진짜 아파트가 없는" 경우는 이미 status='ok',
  found_count=0으로 별도 구분되고 있어 혼동 없음).
- "실패한 법정동만 다시 수집" 버튼을 위해, sweep job이 시군구 전체 대신
  특정 법정동 목록만 처리하도록 하는 필터 컬럼을 추가. 재시도 job은
  원래 job의 summary.dong_results에 이미 저장돼 있는 code/name/dong_name
  을 그대로 재사용하므로 정부 법정동코드 API를 다시 부를 필요가 없음
  (이 컬럼이 채워져 있으면 worker가 그 API 호출을 건너뜀).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a25000000008"
down_revision = "a25000000007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "complex_region_import_jobs",
        sa.Column("dong_codes_filter", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("complex_region_import_jobs", "dong_codes_filter")
