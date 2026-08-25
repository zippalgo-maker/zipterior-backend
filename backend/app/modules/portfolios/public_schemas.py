from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


ROOM_LABELS = {
    "living_room": "거실",
    "kitchen": "주방",
    "master_room": "안방",
    "room": "방",
    "bathroom": "욕실",
    "entrance": "현관",
    "balcony": "발코니",
    "dressing_room": "드레스룸",
    "utility_room": "다용도실",
    "etc": "기타",
}


class PublicPortfolioKeywordResponse(BaseModel):
    id: int
    name: str
    category: str
    sort_order: int


class PublicImageVariantResponse(BaseModel):
    path: str | None
    width: int | None
    height: int | None
    size_bytes: int | None


class PublicPortfolioImageResponse(BaseModel):
    id: int
    portfolio_space_id: int | None = None
    room_code: str
    room_label: str
    original_filename: str | None

    # 기존 프론트 호환 필드
    large_path: str | None
    medium_path: str | None
    thumbnail_path: str | None

    # 프론트에서 variant 단위로 바로 사용할 수 있는 신규 구조
    large: PublicImageVariantResponse
    medium: PublicImageVariantResponse
    thumbnail: PublicImageVariantResponse

    sort_order: int
    is_representative: bool
    aspect_ratio: float | None

    # v2.5.0: 방 전체 설명과는 별개로, 이 사진 한 장에 붙는 원본 문단.
    description: str | None = None


class PublicPortfolioCompanyResponse(BaseModel):
    id: int
    name: str
    logo_path: str | None
    phone: str | None
    sido: str | None
    sigungu: str | None
    eupmyeondong: str | None
    consultation_available: bool


class PublicPortfolioListItemResponse(BaseModel):
    id: int
    title: str
    summary: str | None

    company: PublicPortfolioCompanyResponse

    complex_id: int | None
    complex_name: str | None
    apartment_type_id: int | None
    apartment_type_name: str | None
    pyeong_label: str | None
    supply_area_m2: Decimal | None
    exclusive_area_m2: Decimal | None

    construction_scope: str | None
    budget_min: Decimal | None
    budget_max: Decimal | None
    construction_days: int | None
    construction_date: date | None

    # 기존 프론트 호환 필드
    representative_image_id: int | None
    representative_large_path: str | None
    representative_medium_path: str | None
    representative_thumbnail_path: str | None

    # v0.5.2 신규: 대표 이미지를 하나의 객체로 제공
    representative_image: PublicPortfolioImageResponse | None

    keywords: list[PublicPortfolioKeywordResponse]

    view_count: int
    like_count: int
    comment_count: int
    published_at: datetime

    # v2.5.67(2026-08-24): near_lat/near_lng로 조회했을 때만 값이 있고
    # (하버사인 거리, km), 그 외 조회에서는 None.
    distance_km: float | None = None


class PublicPortfolioSpaceResponse(BaseModel):
    id: int
    space_code: str
    space_name: str
    space_number: int
    description: str | None
    sort_order: int


class PublicContentBlockResponse(BaseModel):
    document_order: int
    node_type: str
    block_type: str
    text_content: str | None
    image_url: str | None
    image_width: int | None
    image_height: int | None
    raw_node: dict


class PublicPortfolioDetailResponse(
    PublicPortfolioListItemResponse
):
    description: str | None
    images: list[PublicPortfolioImageResponse]
    spaces: list[PublicPortfolioSpaceResponse]
    # v2.5.0 (원문 재현): 있으면 상세페이지는 이 순서 그대로 렌더링하고,
    # 없으면(과거 데이터, 또는 아직 개편 전 업체 개별등록) 기존 spaces
    # 갤러리로 표시한다.
    content_blocks: list[PublicContentBlockResponse]


class PublicPortfolioListResponse(BaseModel):
    items: list[PublicPortfolioListItemResponse]
    total: int
    limit: int
    offset: int
