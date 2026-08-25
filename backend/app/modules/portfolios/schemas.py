from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.portfolios.constants import CONSTRUCTION_SCOPE_OPTIONS


def _validate_construction_scope(value: str | None) -> str | None:
    if value is None:
        return None
    if value not in CONSTRUCTION_SCOPE_OPTIONS:
        allowed = ", ".join(CONSTRUCTION_SCOPE_OPTIONS)
        raise ValueError(f"공사 범위는 다음 중 하나여야 합니다: {allowed}")
    return value


class PortfolioComplexLocationRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    address: str = Field(min_length=3, max_length=500)
    road_address: str | None = Field(default=None, max_length=500)
    jibun_address: str | None = Field(default=None, max_length=500)
    latitude: float = Field(ge=33.0, le=39.5)
    longitude: float = Field(ge=124.0, le=132.0)

    @field_validator("name", "address", "road_address", "jibun_address")
    @classmethod
    def normalize_location_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class PortfolioComplexSearchItem(BaseModel):
    name: str
    road_address: str | None = None
    jibun_address: str | None = None
    latitude: float
    longitude: float
    registered: bool = False
    complex_id: int | None = None


class PortfolioComplexSearchRequest(BaseModel):
    items: list[PortfolioComplexSearchItem]


class PortfolioComplexSearchResponse(BaseModel):
    items: list[PortfolioComplexSearchItem]


class PortfolioComplexLocationResponse(BaseModel):
    id: int
    name: str
    road_address: str | None = None
    jibun_address: str | None = None
    latitude: float
    longitude: float


class PortfolioCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    summary: str | None = Field(default=None, max_length=1000)
    description: str | None = Field(default=None, max_length=30000)

    complex_id: int | None = Field(default=None, ge=1)
    apartment_type_id: int | None = Field(default=None, ge=1)

    construction_scope: str | None = Field(
        default=None,
        max_length=100,
    )
    budget_min: Decimal | None = Field(default=None, ge=0)
    budget_max: Decimal | None = Field(default=None, ge=0)
    construction_days: int | None = Field(
        default=None,
        ge=1,
        le=3650,
    )
    construction_date: date | None = None

    @field_validator(
        "title",
        "summary",
        "description",
        "construction_scope",
    )
    @classmethod
    def normalize_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @field_validator("construction_scope")
    @classmethod
    def validate_construction_scope(cls, value: str | None) -> str | None:
        return _validate_construction_scope(value)

    @model_validator(mode="after")
    def validate_relations(self):
        if (
            self.apartment_type_id is not None
            and self.complex_id is None
        ):
            raise ValueError(
                "평형을 선택하려면 아파트 단지도 함께 선택해야 합니다."
            )

        if (
            self.budget_min is not None
            and self.budget_max is not None
            and self.budget_min > self.budget_max
        ):
            raise ValueError(
                "최소 예산은 최대 예산보다 클 수 없습니다."
            )

        return self


class PortfolioUpdateRequest(BaseModel):
    title: str | None = Field(
        default=None,
        min_length=2,
        max_length=200,
    )
    summary: str | None = Field(default=None, max_length=1000)
    description: str | None = Field(default=None, max_length=30000)

    complex_id: int | None = Field(default=None, ge=1)
    apartment_type_id: int | None = Field(default=None, ge=1)

    construction_scope: str | None = Field(
        default=None,
        max_length=100,
    )
    budget_min: Decimal | None = Field(default=None, ge=0)
    budget_max: Decimal | None = Field(default=None, ge=0)
    construction_days: int | None = Field(
        default=None,
        ge=1,
        le=3650,
    )
    construction_date: date | None = None

    @field_validator(
        "title",
        "summary",
        "description",
        "construction_scope",
    )
    @classmethod
    def normalize_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @field_validator("construction_scope")
    @classmethod
    def validate_construction_scope(cls, value: str | None) -> str | None:
        return _validate_construction_scope(value)


class PortfolioListItemResponse(BaseModel):
    id: int
    company_id: int
    title: str
    summary: str | None

    complex_id: int | None
    complex_name: str | None

    apartment_type_id: int | None
    apartment_type_name: str | None
    pyeong_label: str | None

    construction_scope: str | None
    budget_min: Decimal | None
    budget_max: Decimal | None
    construction_days: int | None
    construction_date: date | None

    status: str
    representative_image_id: int | None
    representative_thumbnail_path: str | None

    view_count: int
    like_count: int
    comment_count: int

    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PortfolioDetailResponse(PortfolioListItemResponse):
    description: str | None
    registration_source: str
    created_by_user_id: int | None
    rejection_reason: str | None


class PortfolioDeleteResponse(BaseModel):
    portfolio_id: int
    message: str


class PortfolioSubmitResponse(BaseModel):
    portfolio_id: int
    status: str
    message: str


class PortfolioBulkStatusRequest(BaseModel):
    portfolio_ids: list[int] = Field(min_length=1, max_length=500)
    action: str = Field(pattern="^(submit|hide|show)$")


class PortfolioBulkStatusFailureItem(BaseModel):
    portfolio_id: int
    error: str


class PortfolioBulkStatusResponse(BaseModel):
    succeeded: list[int]
    failed: list[PortfolioBulkStatusFailureItem]


from typing import Literal


PortfolioRoomCode = Literal[
    "living_room",
    "kitchen",
    "master_room",
    "room",
    "bathroom",
    "entrance",
    "balcony",
    "dressing_room",
    "utility_room",
    "etc",
]


class PortfolioImageUpdateRequest(BaseModel):
    room_code: PortfolioRoomCode | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10000)


class PortfolioImageSpaceMoveRequest(BaseModel):
    portfolio_space_id: int = Field(gt=0)


class PortfolioImageResponse(BaseModel):
    id: int
    portfolio_id: int
    portfolio_space_id: int | None = None
    room_code: str

    original_filename: str
    original_mime_type: str | None
    original_size_bytes: int | None
    original_width: int | None
    original_height: int | None

    large_path: str | None
    large_size_bytes: int | None
    large_width: int | None
    large_height: int | None

    medium_path: str | None
    medium_size_bytes: int | None
    medium_width: int | None
    medium_height: int | None

    thumbnail_path: str | None
    thumbnail_size_bytes: int | None
    thumbnail_width: int | None
    thumbnail_height: int | None

    sort_order: int
    is_representative: bool
    processing_status: str
    processing_error: str | None
    created_at: datetime


class PortfolioImageDeleteResponse(BaseModel):
    portfolio_id: int
    image_id: int
    message: str


class PortfolioRepresentativeImageResponse(BaseModel):
    portfolio_id: int
    image_id: int
    representative_image_id: int
    message: str

# ============================================================
# v2.1.8 Structured portfolio spaces
# ============================================================

PortfolioSpaceCode = Literal[
    "living_room",
    "kitchen",
    "master_room",
    "room",
    "bathroom",
    "entrance",
    "balcony",
    "dressing_room",
    "utility_room",
    "etc",
]


class PortfolioSpaceCreateRequest(BaseModel):
    space_code: PortfolioSpaceCode
    space_name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=30000)
    sort_order: int | None = Field(default=None, ge=0, le=10000)

    @field_validator("space_name", "description")
    @classmethod
    def normalize_space_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()
        return value or None


class PortfolioSpaceUpdateRequest(BaseModel):
    space_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    description: str | None = Field(
        default=None,
        max_length=30000,
    )
    sort_order: int | None = Field(
        default=None,
        ge=0,
        le=10000,
    )

    @field_validator("space_name", "description")
    @classmethod
    def normalize_space_update_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()
        return value or None


class PortfolioSpaceResponse(BaseModel):
    id: int
    portfolio_id: int

    space_code: str
    space_name: str
    space_number: int

    description: str | None = None
    sort_order: int

    image_count: int = 0

    created_at: datetime
    updated_at: datetime


class PortfolioSpaceDeleteResponse(BaseModel):
    portfolio_id: int
    space_id: int
    message: str

