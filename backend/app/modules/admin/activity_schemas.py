from datetime import datetime
from pydantic import BaseModel


class ActivityItem(BaseModel):
    id: int
    label: str
    created_at: datetime
    nav_view: str


class ActivityCategory(BaseModel):
    key: str
    label: str
    color: str
    count: int
    nav_view: str
    items: list[ActivityItem]


class ActivitySummaryResponse(BaseModel):
    days: int
    date: str | None = None
    categories: list[ActivityCategory]


class ActivityLogRow(BaseModel):
    id: int
    action_type: str
    target_type: str | None = None
    target_id: int | None = None
    actor_label: str
    target_label: str | None = None
    reason: str | None = None
    created_at: datetime


class ActivityLogResponse(BaseModel):
    items: list[ActivityLogRow]
    total: int
    limit: int
    offset: int
