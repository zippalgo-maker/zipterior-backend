from pydantic import BaseModel, Field, field_validator


class PortfolioKeywordResponse(BaseModel):
    id: int
    name: str
    category: str
    sort_order: int


class PortfolioKeywordSelectionResponse(BaseModel):
    portfolio_id: int
    keywords: list[PortfolioKeywordResponse]


class PortfolioKeywordUpdateRequest(BaseModel):
    keyword_ids: list[int] = Field(
        default_factory=list,
        max_length=10,
    )

    @field_validator("keyword_ids")
    @classmethod
    def validate_keyword_ids(
        cls,
        value: list[int],
    ) -> list[int]:
        if any(keyword_id < 1 for keyword_id in value):
            raise ValueError(
                "키워드 ID는 1 이상의 정수여야 합니다."
            )

        if len(value) != len(set(value)):
            raise ValueError(
                "같은 키워드를 중복 선택할 수 없습니다."
            )

        return value


class PortfolioKeywordUpdateResponse(BaseModel):
    portfolio_id: int
    keyword_count: int
    keywords: list[PortfolioKeywordResponse]
    message: str
