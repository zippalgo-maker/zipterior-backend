from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class BulkUploadCreateRequest(BaseModel):
    job_type: Literal["complex_excel", "company_portfolio_json", "company_portfolio_excel"]
    filename: str = Field(min_length=1, max_length=255)
    # v2.5.0: 250MB대 실 데이터(2,000건 규모) 업로드를 위해 200MB -> 500MB로 상향.
    size_bytes: int = Field(gt=0, le=500 * 1024 * 1024)
    # v2.5.0: 사진 개수 제한 삭제. 원본에 있는 사진은 개수와 무관하게 전부 등록한다.
    max_images_per_portfolio: int | None = Field(default=None, ge=1)
    # v2.4.0 첫 운영 검증은 대량 원본 전체가 아닌 30건 이내로 제한했었다.
    # v2.5.0에서 관리자 검수 UI(신뢰도 계산 + 체크박스)가 완성된 뒤 실제
    # 대량 원본(1,800건 이상)을 등록하기 위해 상한을 올림.
    max_portfolios: int = Field(default=30, ge=1, le=5000)
    prefer_complex_address: bool = True
    publish_immediately: bool = True
    # v2.5.0: 구조 신호 기반 신뢰도가 이 값 미만이면 자동 공개하지 않고
    # 'pending'(검수 대기) 상태로 등록한다. 관리자 화면에서 조정 가능해야 한다.
    confidence_threshold: int = Field(default=80, ge=0, le=100)

    @field_validator("filename")
    @classmethod
    def normalize_filename(cls, value: str) -> str:
        normalized = value.replace("\\", "/").split("/")[-1].strip()
        if not normalized or normalized in {".", ".."}:
            raise ValueError("올바른 파일명이 필요합니다.")
        return normalized


class ComplexResolutionItem(BaseModel):
    record_id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=200)
    road_address: str = Field(min_length=3, max_length=500)
    jibun_address: str | None = Field(default=None, max_length=500)
    sido: str | None = Field(default=None, max_length=50)
    sigungu: str | None = Field(default=None, max_length=80)
    eupmyeondong: str | None = Field(default=None, max_length=100)
    latitude: float = Field(ge=33.0, le=39.5)
    longitude: float = Field(ge=124.0, le=132.0)


class ComplexResolutionFailureItem(BaseModel):
    record_id: int = Field(ge=1)
    error_message: str = Field(min_length=1, max_length=500)


class ComplexResolutionRequest(BaseModel):
    items: list[ComplexResolutionItem] = Field(default_factory=list, max_length=50)
    failures: list[ComplexResolutionFailureItem] = Field(default_factory=list, max_length=50)


class BulkImportJobResponse(BaseModel):
    id: int
    job_type: str
    status: str
    original_filename: str
    expected_size: int
    uploaded_size: int
    options: dict[str, Any]
    summary: dict[str, Any]
    total_count: int
    resolved_count: int
    processed_count: int
    success_count: int
    # v2.5.60(2026-08-24): success_count에 이미 포함돼 있는 "확인필요"
    # (단지/타입을 못 찾아 review_reason이 붙은, 등록은 됐지만 비공개인)
    # 건수를 별도로 내려준다 -- repository.find_job/list_jobs의
    # JOB_REVIEW_COUNT_SUBQUERY 참고. 프론트가 성공(순수) = success_count
    # - review_count로 분리해서 보여준다.
    review_count: int = 0
    duplicate_count: int
    failed_count: int
    skipped_count: int
    image_success_count: int
    image_failed_count: int
    error_message: str | None
    created_at: Any
    started_at: Any | None
    completed_at: Any | None


class BulkImportRecordResponse(BaseModel):
    id: int
    job_id: int
    record_type: str
    record_key: str
    source_label: str | None
    status: str
    payload: dict[str, Any]
    result: dict[str, Any]
    target_id: int | None
    error_message: str | None


class BulkImportRecordListResponse(BaseModel):
    """2026-08-25: /records 응답에 total을 추가(기존엔 순수 배열이라
    500건 넘는 작업은 그 이상이 잘려도 프론트가 알 방법이 없었음).
    다른 admin 목록 API(admin/overview_schemas.py 등)와 동일한
    {items,total,limit,offset} 컨벤션."""
    items: list[BulkImportRecordResponse]
    total: int
    limit: int
    offset: int


class RecordSelectionRequest(BaseModel):
    """v2.5.0: 관리자가 미리보기 화면에서 개별 레코드의 공개 체크박스를
    뒤집을 때 쓴다. 신뢰도 자동판정보다 이 값이 우선한다."""
    selected: bool


class ConfidenceThresholdRequest(BaseModel):
    """v2.5.0: 관리자가 검수 화면에서 신뢰도 기준값(%)을 조정할 때 쓴다.
    적용 시 모든 포트폴리오 레코드의 기본 선택 상태가 이 기준으로
    재계산된다(개별로 뒤집어 둔 체크는 초기화됨)."""
    threshold: int = Field(ge=0, le=100)
