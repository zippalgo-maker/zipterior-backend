from datetime import datetime

from pydantic import BaseModel, Field


class SalesContactCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    contacted_at: datetime | None = None
    """실제 통화한 시각. 안 주면 지금(기록하는 시점)으로 저장."""


class SalesContactItem(BaseModel):
    id: int
    company_id: int
    admin_user_id: int | None = None
    admin_name: str | None = None
    content: str
    contacted_at: datetime
    created_at: datetime


class SalesContactListResponse(BaseModel):
    items: list[SalesContactItem]
