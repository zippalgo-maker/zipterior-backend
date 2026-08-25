"""add apartment_complexes.complex_type + sigungu_regions reference table

Revision ID: a25000000006
Revises: a25000000005
Create Date: 2026-08-21

v2.5.1
- "이 단지가 아파트인지 오피스텔인지" 구분이 지금까지 어디에도 저장되지
  않고 있었다(평형/타입정보(apartment_types, A타입/B타입 등)와는 완전히
  다른 개념 -- 그건 이미 저장되고 있었음). 네이버부동산 지역별 단지목록
  API(hscpTypeCd: A01=아파트/A02=오피스텔)에서 이미 이 정보를 정확히
  받아오고 있었는데 저장할 컬럼이 없어 버려지고 있었다.
- 기존에 저장된 단지(수동 등록분 포함)는 정확한 값을 모르므로 NULL로
  두고 추측해서 채우지 않는다(예: 이름에 "오피스텔"이 없는 오피스텔이
  실제로 많음 -- 과천시 테스트에서 확인). NULL은 관리자 노출 설정에서
  "미분류"로 다뤄야 한다.
- `sigungu_regions`: 시군구 기준 자동수집 화면을 자유 텍스트 입력에서
  "시/도별로 묶인 시군구 체크박스 목록"으로 바꾸기 위한 정적 참조
  테이블. data.go.kr 법정동코드 API 전체(20,560행)를 한 번 받아
  시군구 단위(umd_cd='000', sgg_cd<>'000') 행만 걸러 269건을 시드
  데이터로 넣는다(같은 디렉터리의 seed_data/*.sql).
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "a25000000006"
down_revision = "a25000000005"
branch_labels = None
depends_on = None

SEED_SQL_PATH = (
    Path(__file__).resolve().parent
    / "seed_data"
    / "a25000000006_sigungu_regions.sql"
)


def upgrade() -> None:
    op.add_column(
        "apartment_complexes",
        sa.Column("complex_type", sa.String(length=20), nullable=True),
    )
    op.create_check_constraint(
        "ck_apartment_complexes_type",
        "apartment_complexes",
        "complex_type IN ('apartment', 'officetel') OR complex_type IS NULL",
    )

    op.create_table(
        "sigungu_regions",
        sa.Column("code", sa.String(length=10), primary_key=True),
        sa.Column("sido_name", sa.String(length=50), nullable=False),
        sa.Column("sigungu_name", sa.String(length=80), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
    )
    op.create_index(
        "idx_sigungu_regions_sido", "sigungu_regions", ["sido_name"]
    )
    op.execute(SEED_SQL_PATH.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.drop_index("idx_sigungu_regions_sido", table_name="sigungu_regions")
    op.drop_table("sigungu_regions")
    op.drop_constraint(
        "ck_apartment_complexes_type", "apartment_complexes", type_="check"
    )
    op.drop_column("apartment_complexes", "complex_type")
