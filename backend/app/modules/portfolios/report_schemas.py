from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class CommentReportCreateRequest(BaseModel):
    reason_code: str = Field(min_length=1, max_length=50)
    description: str | None = Field(
        default=None,
        max_length=1000,
    )

    @field_validator("reason_code")
    @classmethod
    def normalize_reason_code(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("신고 사유를 선택해야 합니다.")

        return value

    @field_validator("description")
    @classmethod
    def normalize_description(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()
        return value or None


class CommentReportResponse(BaseModel):
    id: int
    reporter_user_id: int
    target_type: str
    target_id: int
    reason_code: str | None
    description: str | None
    status: str
    created_at: datetime
    message: str
