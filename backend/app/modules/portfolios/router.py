from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentUser
from app.core.database import get_db
from app.modules.portfolios.schemas import (
    PortfolioCreateRequest,
    PortfolioBulkStatusRequest,
    PortfolioBulkStatusResponse,
    PortfolioComplexLocationRequest,
    PortfolioComplexLocationResponse,
    PortfolioComplexSearchRequest,
    PortfolioComplexSearchResponse,
    PortfolioDeleteResponse,
    PortfolioDetailResponse,
    PortfolioListItemResponse,
    PortfolioSubmitResponse,
    PortfolioUpdateRequest,
)
from app.modules.portfolios.service import (
    CompanyPortfolioService,
    EmptyPortfolioUpdateError,
    PortfolioAccessDeniedError,
    PortfolioNotFoundError,
    PortfolioStateConflictError,
    PortfolioValidationError,
)


router = APIRouter(
    prefix="/api/v1/company/portfolios",
    tags=["company-portfolios"],
)


def handle_portfolio_error(
    exc: ValueError,
) -> None:
    if isinstance(exc, PortfolioNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if isinstance(exc, PortfolioAccessDeniedError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    if isinstance(exc, PortfolioStateConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=str(exc),
    ) from exc


@router.get(
    "",
    response_model=list[PortfolioListItemResponse],
)
def list_company_portfolios(
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> list[dict]:
    try:
        return CompanyPortfolioService.list_portfolios(
            session=session,
            user=current_user,
        )
    except (
        PortfolioAccessDeniedError,
        PortfolioNotFoundError,
    ) as exc:
        handle_portfolio_error(exc)


@router.post(
    "",
    response_model=PortfolioDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_company_portfolio(
    payload: PortfolioCreateRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CompanyPortfolioService.create_portfolio(
            session=session,
            user=current_user,
            payload=payload,
        )
    except (
        PortfolioAccessDeniedError,
        PortfolioNotFoundError,
        PortfolioValidationError,
    ) as exc:
        handle_portfolio_error(exc)


@router.post(
    "/complex-location",
    response_model=PortfolioComplexLocationResponse,
)
def resolve_company_portfolio_complex_location(
    payload: PortfolioComplexLocationRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CompanyPortfolioService.resolve_complex_location(
            session=session, user=current_user, payload=payload
        )
    except (PortfolioAccessDeniedError, PortfolioValidationError) as exc:
        handle_portfolio_error(exc)


@router.post(
    "/complex-search",
    response_model=PortfolioComplexSearchResponse,
)
def search_company_portfolio_complexes(
    payload: PortfolioComplexSearchRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        items = CompanyPortfolioService.match_complex_search_items(
            session=session,
            user=current_user,
            items=[item.model_dump() for item in payload.items],
        )
        return {"items": items}
    except (PortfolioAccessDeniedError, PortfolioValidationError) as exc:
        handle_portfolio_error(exc)


@router.post(
    "/registration-request",
)
def create_company_complex_registration_request(
    payload: PortfolioComplexLocationRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CompanyPortfolioService.create_complex_registration_request(
            session=session,
            user=current_user,
            payload=payload,
        )
    except (PortfolioAccessDeniedError, PortfolioValidationError) as exc:
        handle_portfolio_error(exc)


@router.get(
    "/{portfolio_id}",
    response_model=PortfolioDetailResponse,
)
def get_company_portfolio(
    portfolio_id: int,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CompanyPortfolioService.get_portfolio(
            session=session,
            user=current_user,
            portfolio_id=portfolio_id,
        )
    except (
        PortfolioAccessDeniedError,
        PortfolioNotFoundError,
    ) as exc:
        handle_portfolio_error(exc)


@router.patch(
    "/{portfolio_id}",
    response_model=PortfolioDetailResponse,
)
def update_company_portfolio(
    portfolio_id: int,
    payload: PortfolioUpdateRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CompanyPortfolioService.update_portfolio(
            session=session,
            user=current_user,
            portfolio_id=portfolio_id,
            payload=payload,
        )
    except (
        PortfolioAccessDeniedError,
        PortfolioNotFoundError,
        PortfolioValidationError,
        PortfolioStateConflictError,
        EmptyPortfolioUpdateError,
    ) as exc:
        handle_portfolio_error(exc)


@router.post(
    "/{portfolio_id}/submit",
    response_model=PortfolioSubmitResponse,
)
def submit_company_portfolio(
    portfolio_id: int,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CompanyPortfolioService.submit_portfolio(
            session=session,
            user=current_user,
            portfolio_id=portfolio_id,
        )
    except (
        PortfolioAccessDeniedError,
        PortfolioNotFoundError,
        PortfolioValidationError,
        PortfolioStateConflictError,
    ) as exc:
        handle_portfolio_error(exc)


@router.post(
    "/{portfolio_id}/hide",
    response_model=PortfolioSubmitResponse,
)
def hide_company_portfolio(
    portfolio_id: int,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CompanyPortfolioService.hide_portfolio(
            session=session,
            user=current_user,
            portfolio_id=portfolio_id,
        )
    except (
        PortfolioAccessDeniedError,
        PortfolioNotFoundError,
        PortfolioStateConflictError,
    ) as exc:
        handle_portfolio_error(exc)


@router.post(
    "/{portfolio_id}/show",
    response_model=PortfolioSubmitResponse,
)
def show_company_portfolio(
    portfolio_id: int,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CompanyPortfolioService.show_portfolio(
            session=session,
            user=current_user,
            portfolio_id=portfolio_id,
        )
    except (
        PortfolioAccessDeniedError,
        PortfolioNotFoundError,
        PortfolioStateConflictError,
    ) as exc:
        handle_portfolio_error(exc)


@router.post(
    "/bulk-status",
    response_model=PortfolioBulkStatusResponse,
)
def bulk_status_company_portfolios(
    payload: PortfolioBulkStatusRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    """v2.5.0: 업체 포트폴리오 관리 화면 체크박스(개별/전체선택) 일괄 처리
    -- submit(검수요청)/hide(비공개)/show(공개)만 허용."""
    try:
        return CompanyPortfolioService.bulk_status(
            session=session,
            user=current_user,
            portfolio_ids=payload.portfolio_ids,
            action=payload.action,
        )
    except (
        PortfolioAccessDeniedError,
        PortfolioValidationError,
    ) as exc:
        handle_portfolio_error(exc)


@router.delete(
    "/{portfolio_id}",
    response_model=PortfolioDeleteResponse,
)
def delete_company_portfolio(
    portfolio_id: int,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CompanyPortfolioService.delete_portfolio(
            session=session,
            user=current_user,
            portfolio_id=portfolio_id,
        )
    except (
        PortfolioAccessDeniedError,
        PortfolioNotFoundError,
        PortfolioStateConflictError,
    ) as exc:
        handle_portfolio_error(exc)

# ============================================================
# v2.1.8 Structured portfolio spaces
# ============================================================

from app.modules.portfolios.schemas import (
    PortfolioSpaceCreateRequest,
    PortfolioSpaceDeleteResponse,
    PortfolioSpaceResponse,
    PortfolioSpaceUpdateRequest,
)

from app.modules.portfolios.service import (
    CompanyPortfolioSpaceService,
    PortfolioSpaceHasImagesError,
    PortfolioSpaceNotFoundError,
)


@router.get(
    "/{portfolio_id}/spaces",
    response_model=list[PortfolioSpaceResponse],
)
def list_company_portfolio_spaces(
    portfolio_id: int,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> list[dict]:
    try:
        return CompanyPortfolioSpaceService.list_spaces(
            session=session,
            user=current_user,
            portfolio_id=portfolio_id,
        )
    except (
        PortfolioAccessDeniedError,
        PortfolioNotFoundError,
    ) as exc:
        handle_portfolio_error(exc)


@router.post(
    "/{portfolio_id}/spaces",
    response_model=PortfolioSpaceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_company_portfolio_space(
    portfolio_id: int,
    payload: PortfolioSpaceCreateRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CompanyPortfolioSpaceService.create_space(
            session=session,
            user=current_user,
            portfolio_id=portfolio_id,
            payload=payload,
        )
    except (
        PortfolioAccessDeniedError,
        PortfolioNotFoundError,
        PortfolioValidationError,
        PortfolioStateConflictError,
    ) as exc:
        handle_portfolio_error(exc)


@router.patch(
    "/{portfolio_id}/spaces/{space_id}",
    response_model=PortfolioSpaceResponse,
)
def update_company_portfolio_space(
    portfolio_id: int,
    space_id: int,
    payload: PortfolioSpaceUpdateRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CompanyPortfolioSpaceService.update_space(
            session=session,
            user=current_user,
            portfolio_id=portfolio_id,
            space_id=space_id,
            payload=payload,
        )
    except PortfolioSpaceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except (
        PortfolioAccessDeniedError,
        PortfolioNotFoundError,
        PortfolioValidationError,
        PortfolioStateConflictError,
        EmptyPortfolioUpdateError,
    ) as exc:
        handle_portfolio_error(exc)


@router.delete(
    "/{portfolio_id}/spaces/{space_id}",
    response_model=PortfolioSpaceDeleteResponse,
)
def delete_company_portfolio_space(
    portfolio_id: int,
    space_id: int,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CompanyPortfolioSpaceService.delete_space(
            session=session,
            user=current_user,
            portfolio_id=portfolio_id,
            space_id=space_id,
        )
    except PortfolioSpaceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PortfolioSpaceHasImagesError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except (
        PortfolioAccessDeniedError,
        PortfolioNotFoundError,
        PortfolioStateConflictError,
    ) as exc:
        handle_portfolio_error(exc)

