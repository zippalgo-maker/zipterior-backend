from datetime import datetime

from pydantic import BaseModel

from app.modules.portfolios.public_schemas import (
    PublicPortfolioListItemResponse,
)


class PortfolioFavoriteStatusResponse(BaseModel):
    portfolio_id: int
    favorited: bool


class PortfolioFavoriteActionResponse(BaseModel):
    portfolio_id: int
    favorited: bool
    message: str


class FavoritePortfolioItemResponse(BaseModel):
    favorited_at: datetime
    portfolio: PublicPortfolioListItemResponse


class FavoritePortfolioListResponse(BaseModel):
    items: list[FavoritePortfolioItemResponse]
    total: int
    limit: int
    offset: int
