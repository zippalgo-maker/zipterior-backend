from datetime import date
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentAdmin
from app.core.database import get_db
from app.modules.admin.portfolio_schemas import (
    PendingPortfolioItemResponse,
    PortfolioAdminActionRequest,
    PortfolioAdminActionResponse,
    PortfolioBulkStatusRequest,
    PortfolioBulkStatusResponse,
    PortfolioComplexAssignRequest,
    PortfolioComplexAssignResponse,
    PortfolioDetailResponse,
    PortfolioListResponse,
    PortfolioSpaceReorderRequest,
    PortfolioSpaceReorderResponse,
    PortfolioSpaceTextUpdateRequest,
    PortfolioSpaceTextUpdateResponse,
    PortfolioTextUpdateRequest,
    PortfolioTextUpdateResponse,
)
from app.modules.admin.portfolio_service import (
    AdminPortfolioNotFoundError,
    AdminPortfolioService,
    InvalidPortfolioStatusError,
)
from app.modules.portfolios.image_service import (
    PortfolioImageLimitError,
    PortfolioImageNotFoundError,
    PortfolioImageValidationError,
)
from app.modules.portfolios.schemas import (
    PortfolioImageDeleteResponse,
    PortfolioImageResponse,
    PortfolioImageSpaceMoveRequest,
)
from app.modules.portfolios.service import PortfolioStateConflictError


router = APIRouter(
    prefix="/api/v1/admin/portfolios",
    tags=["admin-portfolios"],
)


def handle_admin_portfolio_error(
    exc: ValueError,
) -> None:
    if isinstance(exc, AdminPortfolioNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=str(exc),
    ) from exc


def handle_admin_image_error(exc: ValueError) -> None:
    if isinstance(
        exc, (AdminPortfolioNotFoundError, PortfolioImageNotFoundError)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    if isinstance(
        exc, (PortfolioStateConflictError, PortfolioImageLimitError)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=str(exc),
    ) from exc


@router.get(
    "/pending",
    response_model=list[PendingPortfolioItemResponse],
)
def list_pending_portfolios(
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> list[dict]:
    return AdminPortfolioService.list_pending(session)


@router.get(
    "",
    response_model=PortfolioListResponse,
)
def list_portfolios(
    current_admin: CurrentAdmin,
    q: str | None = Query(None, max_length=100),
    status_filter: str | None = Query(None, alias="status", max_length=30),
    needs_review: bool | None = Query(
        None,
        description="true면 review_reason이 있는(주소 등 확인 필요) 건만, false면 없는 건만",
    ),
    review_reason: str | None = Query(
        None,
        max_length=50,
        description="확인필요 세부사유(예: address_missing)로 좁혀서 조회. needs_review와 별개로 줄 수 있음.",
    ),
    construction_scope: str | None = Query(None, max_length=30),
    created_date: date | None = Query(None, description="등록일(YYYY-MM-DD) 정확히 일치"),
    # 2026-08-22: limit=200 상한 때문에 프론트가 늘린 값(500)을 못 받아서
    # 목록이 통째로 안 뜨던 사고가 실제로 났음. "숫자만 올리는 임시방편은
    # 데이터가 더 늘면 또 터진다"는 지적을 받고 진짜 서버 페이지네이션으로
    # 전환 -- 기본 페이지 크기를 작게(50) 유지하고, sort_by/sort_dir도
    # 서버가 처리한다(정렬 대상이 현재 페이지 밖 데이터를 놓치지 않도록).
    sort_by: Literal["updated_at", "image_count"] = Query("updated_at"),
    sort_dir: Literal["asc", "desc"] = Query("desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
) -> dict:
    return AdminPortfolioService.list_portfolios(
        session,
        q=q,
        status_filter=status_filter,
        needs_review=needs_review,
        review_reason_contains=review_reason,
        construction_scope_filter=construction_scope,
        created_date=created_date.isoformat() if created_date else None,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{portfolio_id}",
    response_model=PortfolioDetailResponse,
)
def get_portfolio_detail(
    portfolio_id: int,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminPortfolioService.get_detail(session, portfolio_id)
    except AdminPortfolioNotFoundError as exc:
        handle_admin_portfolio_error(exc)


@router.patch(
    "/{portfolio_id}",
    response_model=PortfolioTextUpdateResponse,
)
def update_portfolio_text(
    portfolio_id: int,
    payload: PortfolioTextUpdateRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminPortfolioService.update_text(
            session,
            portfolio_id=portfolio_id,
            admin_user_id=current_admin["id"],
            title=payload.title,
            summary=payload.summary,
            description=payload.description,
        )
    except AdminPortfolioNotFoundError as exc:
        handle_admin_portfolio_error(exc)


@router.patch(
    "/{portfolio_id}/complex",
    response_model=PortfolioComplexAssignResponse,
)
def assign_portfolio_complex(
    portfolio_id: int,
    payload: PortfolioComplexAssignRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    """v2.5.0: 대량등록에서 단지를 못 찾아 '확인 필요'(review_reason)로 남은
    포트폴리오에 관리자가 직접 단지를 지정한다. 단지 검색은 기존
    GET /api/v1/admin/complexes?q=... 를 그대로 쓴다(새 검색 엔드포인트
    없음)."""
    try:
        return AdminPortfolioService.assign_complex(
            session,
            portfolio_id=portfolio_id,
            admin_user_id=current_admin["id"],
            complex_id=payload.complex_id,
            apartment_type_id=payload.apartment_type_id,
        )
    except AdminPortfolioNotFoundError as exc:
        handle_admin_portfolio_error(exc)


@router.patch(
    "/{portfolio_id}/spaces/reorder",
    response_model=PortfolioSpaceReorderResponse,
)
def reorder_portfolio_spaces(
    portfolio_id: int,
    payload: PortfolioSpaceReorderRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminPortfolioService.reorder_spaces(
            session,
            portfolio_id=portfolio_id,
            admin_user_id=current_admin["id"],
            space_ids=payload.space_ids,
        )
    except AdminPortfolioNotFoundError as exc:
        handle_admin_portfolio_error(exc)


@router.patch(
    "/{portfolio_id}/spaces/{space_id}",
    response_model=PortfolioSpaceTextUpdateResponse,
)
def update_portfolio_space_text(
    portfolio_id: int,
    space_id: int,
    payload: PortfolioSpaceTextUpdateRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminPortfolioService.update_space_text(
            session,
            portfolio_id=portfolio_id,
            space_id=space_id,
            admin_user_id=current_admin["id"],
            description=payload.description,
        )
    except AdminPortfolioNotFoundError as exc:
        handle_admin_portfolio_error(exc)


@router.post(
    "/{portfolio_id}/approve",
    response_model=PortfolioAdminActionResponse,
)
def approve_portfolio(
    portfolio_id: int,
    payload: PortfolioAdminActionRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminPortfolioService.approve(
            session=session,
            portfolio_id=portfolio_id,
            admin_user_id=current_admin["id"],
            reason=payload.reason,
        )
    except (
        AdminPortfolioNotFoundError,
        InvalidPortfolioStatusError,
    ) as exc:
        handle_admin_portfolio_error(exc)


@router.post(
    "/{portfolio_id}/reject",
    response_model=PortfolioAdminActionResponse,
)
def reject_portfolio(
    portfolio_id: int,
    payload: PortfolioAdminActionRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminPortfolioService.reject(
            session=session,
            portfolio_id=portfolio_id,
            admin_user_id=current_admin["id"],
            reason=payload.reason,
        )
    except (
        AdminPortfolioNotFoundError,
        InvalidPortfolioStatusError,
    ) as exc:
        handle_admin_portfolio_error(exc)


@router.post(
    "/{portfolio_id}/images",
    response_model=PortfolioImageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_portfolio_image(
    portfolio_id: int,
    current_admin: CurrentAdmin,
    room_code: str = Form("etc"),
    portfolio_space_id: int | None = Form(default=None),
    upload: UploadFile = File(...),
    session: Session = Depends(get_db),
) -> dict:
    try:
        return await AdminPortfolioService.upload_image(
            session,
            portfolio_id=portfolio_id,
            admin_user_id=current_admin["id"],
            room_code=room_code,
            portfolio_space_id=portfolio_space_id,
            upload=upload,
        )
    except (
        AdminPortfolioNotFoundError,
        PortfolioStateConflictError,
        PortfolioImageValidationError,
        PortfolioImageLimitError,
    ) as exc:
        handle_admin_image_error(exc)


@router.patch(
    "/{portfolio_id}/images/{image_id}",
    response_model=PortfolioImageResponse,
)
def update_portfolio_image(
    portfolio_id: int,
    image_id: int,
    current_admin: CurrentAdmin,
    sort_order: int | None = None,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminPortfolioService.update_image(
            session,
            portfolio_id=portfolio_id,
            image_id=image_id,
            admin_user_id=current_admin["id"],
            sort_order=sort_order,
        )
    except (
        AdminPortfolioNotFoundError,
        PortfolioStateConflictError,
        PortfolioImageNotFoundError,
    ) as exc:
        handle_admin_image_error(exc)


@router.post(
    "/{portfolio_id}/images/{image_id}/space",
    response_model=PortfolioImageResponse,
)
def move_portfolio_image_to_space(
    portfolio_id: int,
    image_id: int,
    payload: PortfolioImageSpaceMoveRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminPortfolioService.move_image_to_space(
            session,
            portfolio_id=portfolio_id,
            image_id=image_id,
            admin_user_id=current_admin["id"],
            portfolio_space_id=payload.portfolio_space_id,
        )
    except (
        AdminPortfolioNotFoundError,
        PortfolioStateConflictError,
        PortfolioImageNotFoundError,
    ) as exc:
        handle_admin_image_error(exc)


@router.delete(
    "/{portfolio_id}/images/{image_id}",
    response_model=PortfolioImageDeleteResponse,
)
def delete_portfolio_image(
    portfolio_id: int,
    image_id: int,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminPortfolioService.delete_image(
            session,
            portfolio_id=portfolio_id,
            image_id=image_id,
            admin_user_id=current_admin["id"],
        )
    except (
        AdminPortfolioNotFoundError,
        PortfolioStateConflictError,
        PortfolioImageNotFoundError,
    ) as exc:
        handle_admin_image_error(exc)


@router.post(
    "/{portfolio_id}/hide",
    response_model=PortfolioAdminActionResponse,
)
def hide_portfolio(
    portfolio_id: int,
    payload: PortfolioAdminActionRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminPortfolioService.hide(
            session=session,
            portfolio_id=portfolio_id,
            admin_user_id=current_admin["id"],
            reason=payload.reason,
        )
    except (
        AdminPortfolioNotFoundError,
        InvalidPortfolioStatusError,
    ) as exc:
        handle_admin_portfolio_error(exc)


@router.post(
    "/{portfolio_id}/unhide",
    response_model=PortfolioAdminActionResponse,
)
def unhide_portfolio(
    portfolio_id: int,
    payload: PortfolioAdminActionRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminPortfolioService.unhide(
            session=session,
            portfolio_id=portfolio_id,
            admin_user_id=current_admin["id"],
            reason=payload.reason,
        )
    except (
        AdminPortfolioNotFoundError,
        InvalidPortfolioStatusError,
    ) as exc:
        handle_admin_portfolio_error(exc)


@router.post(
    "/bulk-status",
    response_model=PortfolioBulkStatusResponse,
)
def bulk_status_portfolios(
    payload: PortfolioBulkStatusRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    """v2.5.0: 포트폴리오 관리 화면 체크박스(개별/전체선택)로 고른 항목을
    한 번에 승인/반려/숨김/숨김해제한다. 상태 조건이 안 맞는 건은 개별
    실패로만 표시되고 나머지는 계속 처리된다(부분 성공 허용)."""
    return AdminPortfolioService.bulk_status(
        session=session,
        portfolio_ids=payload.portfolio_ids,
        action=payload.action,
        admin_user_id=current_admin["id"],
        reason=payload.reason,
    )
