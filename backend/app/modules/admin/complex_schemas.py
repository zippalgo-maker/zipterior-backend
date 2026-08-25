from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AdminComplexCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sido: str | None = Field(default=None, max_length=50)
    sigungu: str | None = Field(default=None, max_length=80)
    eupmyeondong: str | None = Field(default=None, max_length=100)
    road_address: str | None = None
    jibun_address: str | None = None
    latitude: Decimal
    longitude: Decimal
    completion_year: int | None = None
    household_count: int | None = None
    building_count: int | None = None
    parking_count: int | None = None
    heating_type: str | None = Field(default=None, max_length=100)
    builder_name: str | None = Field(default=None, max_length=200)
    # v2.5.1: 아파트/오피스텔 구분(네이버부동산 hscpTypeCd 기반, 시군구
    # 자동수집이 채워줌). 관리자가 수동으로 등록/수정할 때도 직접
    # 지정할 수 있게 여기 포함한다. V2.5.0_PLAN.md 참고.
    complex_type: Literal["apartment", "officetel"] | None = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return str(value).strip()


class AdminComplexUpdateRequest(AdminComplexCreateRequest):
    is_active: bool = True


class AdminApartmentTypeRequest(BaseModel):
    type_name: str | None = Field(default=None, max_length=100)
    supply_area_m2: Decimal | None = None
    exclusive_area_m2: Decimal | None = None
    pyeong_label: str | None = Field(default=None, max_length=50)
    room_count: int | None = None
    bathroom_count: int | None = None
    floor_plan_path: str | None = None
    has_basic_layout: bool | None = None
    has_expanded_layout: bool | None = None
    sort_order: int = 0


class AdminComplexCreateWithTypesRequest(AdminComplexCreateRequest):
    apartment_types: list[AdminApartmentTypeRequest] = Field(min_length=1)


class AdminApartmentTypeResponse(BaseModel):
    id: int
    complex_id: int
    type_name: str | None
    supply_area_m2: Decimal | None
    exclusive_area_m2: Decimal | None
    pyeong_label: str | None
    room_count: int | None
    bathroom_count: int | None
    floor_plan_path: str | None
    has_basic_layout: bool | None
    has_expanded_layout: bool | None
    sort_order: int
    portfolio_count: int = 0


class AdminComplexImageResponse(BaseModel):
    id: int
    complex_id: int
    image_path: str
    thumbnail_path: str
    width: int
    height: int
    size_bytes: int
    sort_order: int
    is_representative: bool


class AdminNaverComplexLookupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    latitude: Decimal
    longitude: Decimal


class AdminNaverApartmentTypeResponse(BaseModel):
    type_name: str | None
    pyeong_label: str | None
    supply_area_m2: Decimal | None
    exclusive_area_m2: Decimal | None
    room_count: int | None
    bathroom_count: int | None
    has_basic_layout: bool
    has_expanded_layout: bool
    sort_order: int


class AdminNaverComplexLookupResponse(BaseModel):
    naver_complex_number: int
    name: str
    sido: str | None
    sigungu: str | None
    eupmyeondong: str | None
    road_address: str | None
    jibun_address: str | None
    latitude: Decimal
    longitude: Decimal
    completion_year: int | None
    household_count: int | None
    building_count: int | None
    parking_count: int | None
    heating_type: str | None
    builder_name: str | None
    apartment_types: list[AdminNaverApartmentTypeResponse]


class AdminComplexListItemResponse(BaseModel):
    id: int
    name: str
    sido: str | None
    sigungu: str | None
    eupmyeondong: str | None
    road_address: str | None
    jibun_address: str | None
    latitude: Decimal
    longitude: Decimal
    completion_year: int | None
    household_count: int | None
    building_count: int | None
    parking_count: int | None
    heating_type: str | None
    builder_name: str | None
    complex_type: str | None
    representative_image_path: str | None
    representative_thumbnail_path: str | None
    is_active: bool
    apartment_type_count: int
    portfolio_count: int


class AdminComplexDetailResponse(AdminComplexListItemResponse):
    apartment_types: list[AdminApartmentTypeResponse]
    images: list[AdminComplexImageResponse]


class AdminComplexRegistrationRequestResponse(BaseModel):
    id: int
    company_id: int
    company_name: str | None
    requested_name: str
    requested_road_address: str | None
    requested_jibun_address: str | None
    requested_latitude: Decimal | None
    requested_longitude: Decimal | None
    status: str
    completed_complex_id: int | None
    completed_complex_name: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class AdminComplexRegistrationRequestListResponse(BaseModel):
    items: list[AdminComplexRegistrationRequestResponse]
    total: int
    limit: int
    offset: int


class AdminComplexListResponse(BaseModel):
    items: list[AdminComplexListItemResponse]
    total: int
    limit: int
    offset: int


class AdminComplexMutationResponse(BaseModel):
    id: int
    message: str
    apartment_type_ids: list[int] | None = None
