from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AdminCommentReportItem(BaseModel):
    id: int
    reporter_user_id: int | None
    reporter_name: str | None
    comment_id: int
    comment_content: str
    comment_status: str
    comment_user_id: int
    portfolio_id: int
    reason_code: str | None
    description: str | None
    status: str
    handled_by: int | None
    handled_note: str | None
    handled_at: datetime | None
    created_at: datetime


class AdminCommentReportListResponse(BaseModel):
    items: list[AdminCommentReportItem]
    total: int
    limit: int
    offset: int


class AdminCommentReportReviewRequest(BaseModel):
    status: Literal[
        "reviewing",
        "resolved",
        "rejected",
    ]
    handled_note: str | None = Field(
        default=None,
        max_length=2000,
    )


class AdminCommentReportReviewResponse(BaseModel):
    report_id: int
    status: str
    handled_by: int
    handled_note: str | None
    handled_at: datetime
    message: str


class AdminCommentModerationRequest(BaseModel):
    reason: str = Field(
        min_length=1,
        max_length=1000,
    )


class AdminCommentModerationResponse(BaseModel):
    comment_id: int
    portfolio_id: int
    status: str
    comment_count: int
    message: str
