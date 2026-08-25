from pydantic import BaseModel


class PortfolioLikeStatusResponse(BaseModel):
    portfolio_id: int
    liked: bool
    like_count: int


class PortfolioLikeActionResponse(BaseModel):
    portfolio_id: int
    liked: bool
    like_count: int
    message: str
