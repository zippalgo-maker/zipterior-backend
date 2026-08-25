from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class PortfolioCommentAuthorResponse(BaseModel):
    id: int
    name: str
    nickname: str | None


class PortfolioCommentResponse(BaseModel):
    id: int
    portfolio_id: int
    parent_id: int | None
    content: str
    status: str
    author: PortfolioCommentAuthorResponse
    created_at: datetime
    updated_at: datetime


class PortfolioCommentListResponse(BaseModel):
    items: list[PortfolioCommentResponse]
    total: int
    limit: int
    offset: int


class PortfolioCommentCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=1000)
    parent_id: int | None = Field(default=None, ge=1)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError("댓글 내용을 입력해야 합니다.")

        return normalized


class PortfolioCommentUpdateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=1000)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError("댓글 내용을 입력해야 합니다.")

        return normalized


class PortfolioCommentDeleteResponse(BaseModel):
    comment_id: int
    portfolio_id: int
    comment_count: int
    message: str
