from typing import Any, Literal

from pydantic import BaseModel, Field


ComplexRegionImportStatus = Literal[
    "queued", "running", "completed", "completed_with_errors", "failed", "cancelled"
]


class ComplexRegionImportCreateRequest(BaseModel):
    sigungu_query: str = Field(
        min_length=2,
        max_length=200,
        description="시군구 이름 (예: '성남시 분당구', '경기도 수원시 영통구')",
    )


ComplexRegionImportJobKind = Literal["sweep", "cross_check"]


class ComplexRegionImportJobResponse(BaseModel):
    id: int
    requested_by: int
    sigungu_query: str
    job_kind: ComplexRegionImportJobKind = "sweep"
    status: ComplexRegionImportStatus
    total_dong_count: int
    processed_dong_count: int
    total_count: int
    processed_count: int
    success_count: int
    duplicate_count: int
    failed_count: int
    error_message: str | None
    summary: dict[str, Any]
    created_at: Any
    started_at: Any | None
    completed_at: Any | None


class ComplexRegionImportJobListResponse(BaseModel):
    items: list[ComplexRegionImportJobResponse]


class SigunguOptionResponse(BaseModel):
    code: str
    sido_name: str
    sigungu_name: str
    full_name: str
    # 2026-08-22: 체크박스 화면에 상태 색 표시용 -- 아직 한 번도 자동수집을
    # 안 돌려본 시군구는 전부 None.
    latest_job_id: int | None = None
    latest_job_status: ComplexRegionImportStatus | None = None
    latest_total_dong_count: int | None = None
    latest_failed_dong_count: int = 0
    latest_failed_dong_names: list[str] | None = None
    latest_completed_at: Any | None = None
