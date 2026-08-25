from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class PortfolioAdminActionRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=2000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return value.strip()


class PortfolioBulkStatusRequest(BaseModel):
    portfolio_ids: list[int] = Field(min_length=1, max_length=500)
    action: str = Field(pattern="^(approve|reject|hide|unhide)$")
    reason: str = Field(min_length=2, max_length=2000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return value.strip()


class PortfolioBulkStatusFailureItem(BaseModel):
    portfolio_id: int
    error: str


class PortfolioBulkStatusResponse(BaseModel):
    succeeded: list[int]
    failed: list[PortfolioBulkStatusFailureItem]


class PendingPortfolioItemResponse(BaseModel):
    id: int
    company_id: int
    company_name: str

    title: str
    summary: str | None
    description: str | None

    complex_id: int | None
    complex_name: str | None

    apartment_type_id: int | None
    apartment_type_name: str | None
    pyeong_label: str | None

    representative_image_id: int | None
    representative_thumbnail_path: str | None

    status: str
    created_by_user_id: int | None
    submitted_at: datetime


class PortfolioAdminActionResponse(BaseModel):
    portfolio_id: int
    company_id: int
    status: str
    rejection_reason: str | None
    published_at: datetime | None
    message: str


class PortfolioListItemResponse(BaseModel):
    id: int
    company_id: int
    company_name: str
    title: str
    construction_scope: str | None = None
    image_count: int = 0
    created_at: datetime
    status: str
    review_reason: str | None = None
    complex_id: int | None
    complex_name: str | None
    representative_image_id: int | None
    representative_thumbnail_path: str | None
    updated_at: datetime
    has_source_url: bool
    has_content_blocks: bool = False


class PortfolioListResponse(BaseModel):
    items: list[PortfolioListItemResponse]
    total: int


class PortfolioContentBlockResponse(BaseModel):
    id: int
    document_order: int
    node_type: str
    block_type: str
    text_content: str | None
    image_url: str | None
    image_width: int | None
    image_height: int | None
    raw_node: dict


class PortfolioSpaceImageResponse(BaseModel):
    id: int
    thumbnail_path: str | None
    medium_path: str | None
    description: str | None
    sort_order: int
    is_representative: bool


class PortfolioSpaceDetailResponse(BaseModel):
    id: int
    space_code: str
    space_name: str
    space_number: int | None
    description: str | None
    sort_order: int
    images: list[PortfolioSpaceImageResponse]


class PortfolioDetailResponse(BaseModel):
    id: int
    company_id: int
    company_name: str
    title: str
    summary: str | None
    description: str | None
    status: str
    review_reason: str | None = None
    complex_id: int | None
    complex_name: str | None
    updated_at: datetime
    source_portfolio_id: str | None
    source_url: str | None
    spaces: list[PortfolioSpaceDetailResponse]
    content_blocks: list[PortfolioContentBlockResponse] = []


class PortfolioComplexAssignRequest(BaseModel):
    complex_id: int
    apartment_type_id: int | None = None


class PortfolioComplexAssignResponse(BaseModel):
    portfolio_id: int
    complex_id: int | None
    apartment_type_id: int | None
    status: str
    review_reason: str | None


class PortfolioTextUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    summary: str | None = Field(default=None, max_length=5000)
    description: str | None = Field(default=None, max_length=30000)


class PortfolioTextUpdateResponse(BaseModel):
    portfolio_id: int
    title: str
    summary: str | None
    description: str | None


class PortfolioSpaceTextUpdateRequest(BaseModel):
    description: str | None = Field(default=None, max_length=30000)


class PortfolioSpaceReorderRequest(BaseModel):
    space_ids: list[int] = Field(min_length=1, max_length=200)


class PortfolioSpaceReorderResponse(BaseModel):
    portfolio_id: int
    updated: int


class PortfolioSpaceTextUpdateResponse(BaseModel):
    id: int
    portfolio_id: int
    description: str | None
