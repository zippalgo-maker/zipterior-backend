from datetime import datetime

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    id: int
    notification_type: str
    title: str
    message: str | None = None
    target_type: str | None = None
    target_id: int | None = None
    read_at: datetime | None = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse] = Field(default_factory=list)
    total: int
    unread_count: int
    limit: int
    offset: int


class NotificationActionResponse(BaseModel):
    updated_count: int
    unread_count: int
    message: str
