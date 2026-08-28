from datetime import datetime

from pydantic import BaseModel, Field


class SalesContactCodeItem(BaseModel):
    id: int
    code_type: str
    label: str
    sort_order: int
    is_active: bool


class SalesContactCodeListResponse(BaseModel):
    items: list[SalesContactCodeItem]


class SalesContactCodeCreateRequest(BaseModel):
    code_type: str = Field(pattern="^(status|reason)$")
    label: str = Field(min_length=1, max_length=100)


class SalesContactCreateRequest(BaseModel):
    content: str = Field(default="", max_length=4000)
    """굵게/색상 서식이 포함된 HTML. 서버에서 반드시 sanitize 후 저장."""
    contacted_at: datetime | None = None
    status_code_id: int | None = None
    reason_code_id: int | None = None


class SalesContactUpdateRequest(BaseModel):
    content: str = Field(default="", max_length=4000)
    status_code_id: int | None = None
    reason_code_id: int | None = None
    contacted_at: datetime | None = None
    reason: str = Field(min_length=2, max_length=500)
    """수정 사유 -- 필수 입력."""


class SalesContactEditItem(BaseModel):
    id: int
    edited_by: int | None = None
    edited_by_name: str | None = None
    edited_at: datetime
    reason: str
    previous_content: str | None = None
    previous_status_label: str | None = None
    previous_reason_label: str | None = None


class SalesContactItem(BaseModel):
    id: int
    company_id: int
    admin_user_id: int | None = None
    admin_name: str | None = None
    content: str
    status_code_id: int | None = None
    status_label: str | None = None
    reason_code_id: int | None = None
    reason_label: str | None = None
    contacted_at: datetime
    created_at: datetime
    updated_at: datetime | None = None
    updated_by: int | None = None
    updated_by_name: str | None = None
    update_reason: str | None = None
    edit_count: int = 0


class SalesContactListResponse(BaseModel):
    items: list[SalesContactItem]
    total: int


class SalesContactDetailResponse(BaseModel):
    contact: SalesContactItem
    edits: list[SalesContactEditItem]
