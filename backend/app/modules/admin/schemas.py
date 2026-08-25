from pydantic import BaseModel, Field, field_validator


class CompanyActionRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=1000)


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
