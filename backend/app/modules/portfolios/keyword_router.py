from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentUser
from app.core.database import get_db
from app.modules.portfolios.keyword_schemas import (
    PortfolioKeywordResponse,
    PortfolioKeywordSelectionResponse,
    PortfolioKeywordUpdateRequest,
    PortfolioKeywordUpdateResponse,
)
from app.modules.portfolios.keyword_service import (
    CompanyPortfolioKeywordService,
    PortfolioKeywordValidationError,
)
from app.modules.portfolios.service import (
    PortfolioAccessDeniedError,
    PortfolioNotFoundError,
    PortfolioStateConflictError,
)


router = APIRouter(
    tags=["portfolio-keywords"],
)


def handle_keyword_error(
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
    "/api/v1/portfolio-keywords",
    response_model=list[PortfolioKeywordResponse],
)
def list_portfolio_keywords(
    session: Session = Depends(get_db),
) -> list[dict]:
    return CompanyPortfolioKeywordService.list_available(
        session
    )


@router.get(
    "/api/v1/company/portfolios/{portfolio_id}/keywords",
    response_model=PortfolioKeywordSelectionResponse,
)
def get_company_portfolio_keywords(
    portfolio_id: int,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return (
            CompanyPortfolioKeywordService.list_selected(
                session=session,
                user=current_user,
                portfolio_id=portfolio_id,
            )
        )
    except (
        PortfolioAccessDeniedError,
        PortfolioNotFoundError,
    ) as exc:
        handle_keyword_error(exc)


@router.put(
    "/api/v1/company/portfolios/{portfolio_id}/keywords",
    response_model=PortfolioKeywordUpdateResponse,
)
def replace_company_portfolio_keywords(
    portfolio_id: int,
    payload: PortfolioKeywordUpdateRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return (
            CompanyPortfolioKeywordService.replace_selected(
                session=session,
                user=current_user,
                portfolio_id=portfolio_id,
                keyword_ids=payload.keyword_ids,
            )
        )
    except (
        PortfolioAccessDeniedError,
        PortfolioNotFoundError,
        PortfolioStateConflictError,
        PortfolioKeywordValidationError,
    ) as exc:
        handle_keyword_error(exc)
