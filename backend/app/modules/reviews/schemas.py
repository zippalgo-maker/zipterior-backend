"""v1.10.1(2026-08-26): 시공 리뷰(목업 13번 화면 하단 "시공 리뷰 작성" CTA).
reviews 모듈이 지금까지 전부 0바이트 빈 스캘폴드였던 걸 이번에 처음 채운다."""

from datetime import datetime

from pydantic import BaseModel, Field


class ReviewCreateRequest(BaseModel):
    estimate_request_id: int = Field(ge=1)
    rating: int = Field(ge=1, le=5)
    content: str | None = Field(default=None, max_length=2000)


class ReviewCompanySummary(BaseModel):
    id: int
    name: str


class ReviewResponse(BaseModel):
    id: int
    estimate_request_id: int
    customer_id: int
    company: ReviewCompanySummary
    portfolio_id: int | None = None
    rating: int
    content: str | None = None
    created_at: datetime


class ReviewListResponse(BaseModel):
    items: list[ReviewResponse]
    total: int
    limit: int
    offset: int
