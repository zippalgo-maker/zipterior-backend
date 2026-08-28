from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class PublicCompanyPortfolioSummary(BaseModel):
    id: int
    title: str
    summary: str | None
    representative_thumbnail_path: str | None
    view_count: int
    like_count: int
    published_at: datetime


class PublicCompanyListItemResponse(BaseModel):
    id: int
    name: str
    logo_path: str | None
    sido: str | None
    sigungu: str | None
    portfolio_count: int


class PublicCompanyListResponse(BaseModel):
    items: list[PublicCompanyListItemResponse]


class PublicServiceRegionResponse(BaseModel):
    sido: str | None
    sigungu: str | None
    eupmyeondong: str | None
    is_primary: bool


class PublicCompanyDetailResponse(BaseModel):
    id: int
    name: str
    slug: str | None
    representative_name: str | None
    phone: str | None
    email: str | None
    address: str | None
    address_detail: str | None
    sido: str | None
    sigungu: str | None
    eupmyeondong: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    intro: str | None
    logo_path: str | None
    website_url: str | None
    kakao_url: str | None
    consultation_available: bool
    portfolio_count: int
    exposure_score: Decimal
    map_priority: int = 0
    is_premium: bool = False
    service_regions: list[PublicServiceRegionResponse]
    portfolios: list[PublicCompanyPortfolioSummary]


class PublicApartmentTypeResponse(BaseModel):
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
    portfolio_count: int


class PublicComplexImageResponse(BaseModel):
    id: int
    image_path: str
    thumbnail_path: str
    width: int
    height: int
    sort_order: int
    is_representative: bool


class PublicComplexListItemResponse(BaseModel):
    id: int
    name: str
    sido: str | None
    sigungu: str | None
    eupmyeondong: str | None
    latitude: Decimal
    longitude: Decimal
    completion_year: int | None
    household_count: int | None
    building_count: int | None
    apartment_type_count: int
    portfolio_count: int


class PublicComplexDetailResponse(PublicComplexListItemResponse):
    road_address: str | None
    jibun_address: str | None
    parking_count: int | None
    heating_type: str | None
    builder_name: str | None
    images: list[PublicComplexImageResponse]
    apartment_types: list[PublicApartmentTypeResponse]


class PublicComplexListResponse(BaseModel):
    items: list[PublicComplexListItemResponse]
    total: int
    limit: int
    offset: int


class PublicApartmentTypeListResponse(BaseModel):
    items: list[PublicApartmentTypeResponse]
    total: int
    limit: int
    offset: int


class PublicMapMarkerResponse(BaseModel):
    id: int
    marker_type: Literal["complex", "company"]
    name: str
    latitude: Decimal
    longitude: Decimal
    sido: str | None
    sigungu: str | None
    eupmyeondong: str | None
    portfolio_count: int
    apartment_type_count: int | None = None
    consultation_available: bool | None = None
    logo_path: str | None = None
    exposure_score: Decimal | None = None
    map_priority: int | None = None
    is_premium: bool | None = None
    marker_level: Literal["standard", "premium"] | None = None


class PublicMapMarkerListResponse(BaseModel):
    items: list[PublicMapMarkerResponse]
    total: int


# 2026-08-25: 통합검색 카카오 보강("place") 추가 -- 집테리어 DB에 없는
# 아파트/오피스텔/지하철역을 카카오로 채운 결과라 id가 없고(DB row가
# 아니므로), source로 어디서 온 결과인지, place_category로 카테고리
# 라벨("아파트"/"오피스텔"/"지하철역")을 내려준다.
class PublicMapSearchItemResponse(BaseModel):
    result_type: Literal["complex", "company", "place"]
    id: int | None = None
    name: str
    sido: str | None = None
    sigungu: str | None = None
    eupmyeondong: str | None = None
    latitude: Decimal | None
    longitude: Decimal | None
    portfolio_count: int = 0
    source: Literal["zipterior", "kakao"] = "zipterior"
    place_category: str | None = None


class PublicMapSearchResponse(BaseModel):
    items: list[PublicMapSearchItemResponse]
    total: int


# 2026-08-25(2차): 클러스터 버블 숫자 정확도 보정 -- 화면 하나에 있는
# 모든 격자셀 합계를 한 번의 응답으로 배치 전달(요청 수를 클러스터
# 개수만큼이 아니라 화면당 1건으로 줄이기 위함).
class PublicMapClusterGridCellResponse(BaseModel):
    lat_index: int
    lng_index: int
    complex_count: int
    total_portfolio_count: int


class PublicMapClusterGridSummaryResponse(BaseModel):
    cells: list[PublicMapClusterGridCellResponse]


class PublicViewportItemResponse(BaseModel):
    item_type: Literal["cluster", "marker"]
    marker_type: Literal["complex", "company"]
    cluster_id: str | None = None
    id: int | None = None
    name: str | None = None
    latitude: Decimal
    longitude: Decimal
    count: int = 1
    portfolio_count: int = 0
    apartment_type_count: int | None = None
    premium_count: int = 0
    consultation_available: bool | None = None
    logo_path: str | None = None
    exposure_score: Decimal | None = None
    map_priority: int | None = None
    is_premium: bool | None = None
    marker_level: Literal["standard", "premium"] | None = None


class PublicMapViewportResponse(BaseModel):
    zoom: int
    clustered: bool
    cluster_cell_degrees: Decimal | None
    items: list[PublicViewportItemResponse]
    total_items: int
    source_marker_count: int
