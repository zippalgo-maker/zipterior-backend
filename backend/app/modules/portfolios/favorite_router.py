from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentUser
from app.core.database import get_db
from app.modules.portfolios.favorite_schemas import (
    FavoritePortfolioListResponse,
    PortfolioFavoriteActionResponse,
    PortfolioFavoriteStatusResponse,
)
from app.modules.portfolios.favorite_service import (
    PortfolioFavoriteService,
    PortfolioFavoriteTargetNotFoundError,
)


router = APIRouter(
    tags=["portfolio-favorites"],
)


@router.get(
    "/api/v1/portfolios/{portfolio_id}/favorite",
    response_model=PortfolioFavoriteStatusResponse,
)
def get_favorite_status(
    portfolio_id: int,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return PortfolioFavoriteService.get_status(
            session,
            user=current_user,
            portfolio_id=portfolio_id,
        )
    except PortfolioFavoriteTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/api/v1/portfolios/{portfolio_id}/favorite",
    response_model=PortfolioFavoriteActionResponse,
)
def add_favorite(
    portfolio_id: int,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return PortfolioFavoriteService.add(
            session,
            user=current_user,
            portfolio_id=portfolio_id,
        )
    except PortfolioFavoriteTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.delete(
    "/api/v1/portfolios/{portfolio_id}/favorite",
    response_model=PortfolioFavoriteActionResponse,
)
def remove_favorite(
    portfolio_id: int,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    return PortfolioFavoriteService.remove(
        session,
        user=current_user,
        portfolio_id=portfolio_id,
    )


@router.get(
    "/api/v1/me/favorite-portfolios",
    response_model=FavoritePortfolioListResponse,
)
def list_my_favorite_portfolios(
    current_user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> dict:
    return PortfolioFavoriteService.list_mine(
        session,
        user=current_user,
        limit=limit,
        offset=offset,
    )
