from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentAdmin
from app.core.database import get_db
from app.modules.feature_flags.map_visibility_service import MapVisibilityService
from app.modules.feature_flags.portfolio_display_service import (
    InvalidNoticeImageError,
    PortfolioDisplaySettingsService,
)
from app.modules.feature_flags.schemas import (
    MapComplexTypeVisibilityResponse,
    MapComplexTypeVisibilityUpdateRequest,
    NoticeImageUploadResponse,
    PortfolioDisplaySettingsResponse,
    PortfolioDisplaySettingsUpdateRequest,
)


# v2.5.1: 포트폴리오 상세 하단 표시 설정(SNS링크 노출 + 안내문구/CTA).
# 공개 GET은 인증 없이 누구나 조회 가능(공개 사이트 렌더링용), 나머지는
# 관리자 전용. V2.5.0_PLAN.md 참고.
public_router = APIRouter(prefix="/api/v1/public", tags=["public-settings"])
admin_router = APIRouter(prefix="/api/v1/admin", tags=["admin-settings"])


@public_router.get(
    "/portfolio-display-settings",
    response_model=PortfolioDisplaySettingsResponse,
)
def get_public_portfolio_display_settings(
    session: Session = Depends(get_db),
) -> dict:
    return PortfolioDisplaySettingsService.get(session)


@admin_router.get(
    "/portfolio-display-settings",
    response_model=PortfolioDisplaySettingsResponse,
)
def get_admin_portfolio_display_settings(
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    return PortfolioDisplaySettingsService.get(session)


@admin_router.patch(
    "/portfolio-display-settings",
    response_model=PortfolioDisplaySettingsResponse,
)
def update_admin_portfolio_display_settings(
    payload: PortfolioDisplaySettingsUpdateRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    return PortfolioDisplaySettingsService.update(
        session,
        admin_user_id=current_admin["id"],
        sns_links_enabled=payload.sns_links_enabled,
        notice_enabled=payload.notice_enabled,
        notice_text=payload.notice_text,
        notice_button_label=payload.notice_button_label,
    )


@admin_router.post(
    "/portfolio-display-settings/notice-image",
    response_model=NoticeImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_notice_image(
    current_admin: CurrentAdmin,
    upload: UploadFile = File(...),
    session: Session = Depends(get_db),
) -> dict:
    try:
        return await PortfolioDisplaySettingsService.upload_notice_image(
            session,
            admin_user_id=current_admin["id"],
            upload=upload,
        )
    except InvalidNoticeImageError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@admin_router.delete(
    "/portfolio-display-settings/notice-image",
    response_model=NoticeImageUploadResponse,
)
def delete_notice_image(
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    return PortfolioDisplaySettingsService.delete_notice_image(
        session,
        admin_user_id=current_admin["id"],
    )


# v2.5.1: 지도 마커/단지 기본정보 아파트·오피스텔 유형별 노출 설정.
# 공개 GET은 없음 -- 서버가 지도 쿼리 안에서 직접 반영한다.
@admin_router.get(
    "/map-settings/complex-type-visibility",
    response_model=MapComplexTypeVisibilityResponse,
)
def get_map_complex_type_visibility(
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    return MapVisibilityService.get(session)


@admin_router.patch(
    "/map-settings/complex-type-visibility",
    response_model=MapComplexTypeVisibilityResponse,
)
def update_map_complex_type_visibility(
    payload: MapComplexTypeVisibilityUpdateRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    return MapVisibilityService.update(
        session,
        admin_user_id=current_admin["id"],
        apartment_visible=payload.apartment_visible,
        officetel_visible=payload.officetel_visible,
    )
