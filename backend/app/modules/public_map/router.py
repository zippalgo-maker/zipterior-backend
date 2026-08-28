from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.public_map.schemas import (
    PublicApartmentTypeListResponse,
    PublicCompanyDetailResponse,
    PublicCompanyListResponse,
    PublicComplexDetailResponse,
    PublicComplexListResponse,
    PublicMapClusterGridSummaryResponse,
    PublicMapMarkerListResponse,
    PublicMapSearchResponse,
    PublicMapViewportResponse,
)
from app.modules.public_map.service import (
    PublicCompanyNotFoundError,
    PublicComplexNotFoundError,
    PublicMapService,
)


router = APIRouter(prefix="/api/v1/public", tags=["public-map"])


def norm(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def validate_bbox(*, north: float, south: float, east: float, west: float) -> None:
    if south > north:
        raise HTTPException(status_code=422, detail="south는 north보다 클 수 없습니다.")
    if west > east:
        raise HTTPException(status_code=422, detail="west는 east보다 클 수 없습니다.")


@router.get("/companies", response_model=PublicCompanyListResponse)
def list_public_companies_by_region(
    sido: str | None = Query(default=None, max_length=50),
    sigungu: str | None = Query(default=None, max_length=50),
    exclude_company_ids: list[int] | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=30),
    session: Session = Depends(get_db),
):
    return PublicMapService.list_companies_by_region(
        session,
        sido=norm(sido),
        sigungu=norm(sigungu),
        exclude_company_ids=exclude_company_ids,
        limit=limit,
    )


@router.get("/companies/{company_id}", response_model=PublicCompanyDetailResponse)
def get_public_company(company_id: int, session: Session = Depends(get_db)):
    try:
        return PublicMapService.get_company(session, company_id)
    except PublicCompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/complexes", response_model=PublicComplexListResponse)
def list_public_complexes(
    q: str | None = Query(None, max_length=100),
    sido: str | None = Query(None, max_length=50),
    sigungu: str | None = Query(None, max_length=80),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
):
    return PublicMapService.list_complexes(
        session,
        q=norm(q),
        sido=norm(sido),
        sigungu=norm(sigungu),
        limit=limit,
        offset=offset,
    )


@router.get("/complexes/{complex_id}", response_model=PublicComplexDetailResponse)
def get_public_complex(complex_id: int, session: Session = Depends(get_db)):
    try:
        return PublicMapService.get_complex(session, complex_id)
    except PublicComplexNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/apartment-types", response_model=PublicApartmentTypeListResponse)
def list_public_apartment_types(
    complex_id: int = Query(..., ge=1),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
):
    try:
        return PublicMapService.list_apartment_types(
            session,
            complex_id=complex_id,
            limit=limit,
            offset=offset,
        )
    except PublicComplexNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/map/markers", response_model=PublicMapMarkerListResponse)
def list_public_map_markers(
    marker_type: Literal["complex", "company"] = Query("complex"),
    north: float | None = None,
    south: float | None = None,
    east: float | None = None,
    west: float | None = None,
    sido: str | None = Query(None, max_length=50),
    sigungu: str | None = Query(None, max_length=80),
    consultation_available: bool | None = Query(None),
    premium_only: bool = Query(False),
    has_portfolio: bool = Query(False),
    limit: int = Query(1000, ge=1, le=3000),
    session: Session = Depends(get_db),
):
    if north is not None and south is not None and south > north:
        raise HTTPException(status_code=422, detail="south는 north보다 클 수 없습니다.")
    if east is not None and west is not None and west > east:
        raise HTTPException(status_code=422, detail="west는 east보다 클 수 없습니다.")
    if marker_type == "complex" and (consultation_available is not None or premium_only):
        raise HTTPException(
            status_code=422,
            detail="consultation_available/premium_only 필터는 company 마커에서만 사용할 수 있습니다.",
        )
    return PublicMapService.list_markers(
        session,
        marker_type=marker_type,
        north=north,
        south=south,
        east=east,
        west=west,
        sido=norm(sido),
        sigungu=norm(sigungu),
        limit=limit,
        consultation_available=consultation_available,
        premium_only=premium_only,
        has_portfolio=has_portfolio,
    )


@router.get("/map/viewport", response_model=PublicMapViewportResponse)
def get_public_map_viewport(
    marker_type: Literal["complex", "company"] = Query("complex"),
    zoom: int = Query(..., ge=4, le=20),
    north: float = Query(..., ge=-90, le=90),
    south: float = Query(..., ge=-90, le=90),
    east: float = Query(..., ge=-180, le=180),
    west: float = Query(..., ge=-180, le=180),
    sido: str | None = Query(None, max_length=50),
    sigungu: str | None = Query(None, max_length=80),
    consultation_available: bool | None = Query(None),
    premium_only: bool = Query(False),
    has_portfolio: bool = Query(False),
    source_limit: int = Query(3000, ge=1, le=5000),
    session: Session = Depends(get_db),
):
    validate_bbox(north=north, south=south, east=east, west=west)
    if marker_type == "complex" and (consultation_available is not None or premium_only):
        raise HTTPException(
            status_code=422,
            detail="consultation_available/premium_only 필터는 company 마커에서만 사용할 수 있습니다.",
        )
    return PublicMapService.viewport(
        session,
        marker_type=marker_type,
        zoom=zoom,
        north=north,
        south=south,
        east=east,
        west=west,
        sido=norm(sido),
        sigungu=norm(sigungu),
        limit=source_limit,
        consultation_available=consultation_available,
        premium_only=premium_only,
        has_portfolio=has_portfolio,
    )


@router.get("/map/search", response_model=PublicMapSearchResponse)
def search_public_map(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_db),
):
    return PublicMapService.search(session, q=q.strip(), limit=limit)


@router.get("/map/cluster-grid-summary", response_model=PublicMapClusterGridSummaryResponse)
def get_public_map_cluster_grid_summary(
    north: float = Query(..., ge=-90, le=90),
    south: float = Query(..., ge=-90, le=90),
    east: float = Query(..., ge=-180, le=180),
    west: float = Query(..., ge=-180, le=180),
    cell_size: float = Query(..., gt=0, le=10),
    session: Session = Depends(get_db),
):
    """2026-08-25(2차): 지도 클러스터 버블 숫자 정확도 보정 -- 화면(bbox)
    전체의 격자셀별 정확한 합계를 GROUP BY 한 번으로 모두 계산해
    배치로 내려준다(클러스터 개수만큼 요청이 나가던 1차 버전이 IP당
    분당 300건 제한에 걸려 마커 전체가 안 뜨는 사고로 이어져서 화면당
    1요청으로 축소, V2.5.0_PLAN.md 2026-08-25 기록 참고)."""
    validate_bbox(north=north, south=south, east=east, west=west)
    return PublicMapService.cluster_grid_summary(
        session, north=north, south=south, east=east, west=west, cell_size=cell_size
    )
