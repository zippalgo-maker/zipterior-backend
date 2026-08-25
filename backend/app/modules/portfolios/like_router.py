from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentUser
from app.core.database import get_db
from app.modules.portfolios.like_schemas import (
    PortfolioLikeActionResponse,
    PortfolioLikeStatusResponse,
)
from app.modules.portfolios.like_service import (
    PortfolioLikeTargetNotFoundError,
    PublicPortfolioLikeService,
)


router = APIRouter(
    prefix="/api/v1/portfolios",
    tags=["portfolio-likes"],
)


def handle_like_error(
    exc: ValueError,
) -> None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=str(exc),
    ) from exc


@router.get(
    "/{portfolio_id}/like",
    response_model=PortfolioLikeStatusResponse,
)
def get_portfolio_like_status(
    portfolio_id: int,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return PublicPortfolioLikeService.get_status(
            session,
            user=current_user,
            portfolio_id=portfolio_id,
        )
    except PortfolioLikeTargetNotFoundError as exc:
        handle_like_error(exc)


@router.post(
    "/{portfolio_id}/like",
    response_model=PortfolioLikeActionResponse,
)
def like_portfolio(
    portfolio_id: int,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return PublicPortfolioLikeService.like(
            session,
            user=current_user,
            portfolio_id=portfolio_id,
        )
    except PortfolioLikeTargetNotFoundError as exc:
        handle_like_error(exc)


@router.delete(
    "/{portfolio_id}/like",
    response_model=PortfolioLikeActionResponse,
)
def unlike_portfolio(
    portfolio_id: int,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return PublicPortfolioLikeService.unlike(
            session,
            user=current_user,
            portfolio_id=portfolio_id,
        )
    except PortfolioLikeTargetNotFoundError as exc:
        handle_like_error(exc)
