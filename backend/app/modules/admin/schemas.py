from pydantic import BaseModel, Field, field_validator


class CompanyActionRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=1000)
    # 정지(suspend)에서만 쓰임: None이면 무기한, 값이 있으면 그 일수 후 자동 해제.
    # approve/reject는 이 필드를 그냥 무시한다.
    suspend_days: int | None = Field(default=None, ge=1, le=3650)


class CompanyActionResponse(BaseModel):
    company_id: int
    owner_user_id: int
    company_status: str
    user_status: str
    message: str


# 2026-08-25: 업체관리 체크박스 일괄 승인/반려/정지 -- 포트폴리오관리
# bulk-status(PortfolioBulkStatusRequest/Response)와 동일한 패턴.
class CompanyBulkStatusRequest(BaseModel):
    company_ids: list[int] = Field(min_length=1, max_length=500)
    action: str = Field(pattern="^(approve|reject|suspend)$")
    reason: str = Field(min_length=2, max_length=1000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return value.strip()


class CompanyBulkStatusFailureItem(BaseModel):
    company_id: int
    error: str


class CompanyBulkStatusResponse(BaseModel):
    succeeded: list[int]
    failed: list[CompanyBulkStatusFailureItem]


# 2026-08-26: 일반회원(개별 계정) 이용정지 -- 사유는 항상 필수, 기간은
# 무기한(None) 또는 N일 중 선택. 만료되면 백그라운드 워커가 자동 해제.
class UserSuspendRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=1000)
    suspend_days: int | None = Field(default=None, ge=1, le=3650)


class UserActionRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=1000)


class UserSuspendResponse(BaseModel):
    user_id: int
    user_status: str
    suspended_until: str | None = None
    message: str


class UserActionResponse(BaseModel):
    user_id: int
    user_status: str
    message: str
