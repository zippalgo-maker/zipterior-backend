from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.common.dependencies import OptionalCurrentUser
from app.core.database import get_db
from app.modules.portfolios.public_schemas import (
    PublicPortfolioDetailResponse,
    PublicPortfolioListResponse,
)
from app.modules.portfolios.public_service import (
    PublicPortfolioNotFoundError,
    PublicPortfolioService,
)
from app.modules.portfolios.view_service import PublicPortfolioViewService


router = APIRouter(
    prefix="/api/v1/portfolios",
    tags=["public-portfolios"],
)


def normalize_optional_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    return normalized or None


@router.get(
    "",
    response_model=PublicPortfolioListResponse,
)
def list_public_portfolios(
    keyword_id: int | None = Query(default=None, ge=1),
    keyword_ids: list[int] | None = Query(default=None),

    q: str | None = Query(
        default=None,
        max_length=100,
    ),

    sido: str | None = Query(
        default=None,
        max_length=50,
    ),
    sigungu: str | None = Query(
        default=None,
        max_length=50,
    ),

    company_id: int | None = Query(
        default=None,
        ge=1,
    ),
    company_name: str | None = Query(
        default=None,
        max_length=100,
    ),

    complex_id: int | None = Query(
        default=None,
        ge=1,
    ),
    complex_name: str | None = Query(
        default=None,
        max_length=100,
    ),

    apartment_type_id: int | None = Query(
        default=None,
        ge=1,
    ),

    construction_scope: str | None = Query(
        default=None,
        max_length=100,
    ),

    pyeong_min: float | None = Query(
        default=None,
        ge=0,
        le=500,
    ),
    pyeong_max: float | None = Query(
        default=None,
        ge=0,
        le=500,
    ),

    budget_min: int | None = Query(
        default=None,
        ge=0,
    ),
    budget_max: int | None = Query(
        default=None,
        ge=0,
    ),

    sort: Literal["latest", "popular", "nearest"] = Query(
        default="latest"
    ),
    near_lat: float | None = Query(default=None, ge=-90, le=90),
    near_lng: float | None = Query(default=None, ge=-180, le=180),

    limit: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),

    session: Session = Depends(get_db),
) -> dict:
    normalized_keyword_ids = None

    if keyword_ids:
        normalized_keyword_ids = sorted(
            set(keyword_ids)
        )

    return PublicPortfolioService.list_portfolios(
        session,
        keyword_id=keyword_id,
        keyword_ids=normalized_keyword_ids,
        q=normalize_optional_text(q),
        sido=normalize_optional_text(sido),
        sigungu=normalize_optional_text(sigungu),
        company_id=company_id,
        company_name=normalize_optional_text(
            company_name
        ),
        complex_id=complex_id,
        complex_name=normalize_optional_text(
            complex_name
        ),
        apartment_type_id=apartment_type_id,
        construction_scope=normalize_optional_text(
            construction_scope
        ),
        pyeong_min=pyeong_min,
        pyeong_max=pyeong_max,
        budget_min=budget_min,
        budget_max=budget_max,
        sort=sort,
        near_lat=near_lat,
        near_lng=near_lng,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{portfolio_id}",
    response_model=PublicPortfolioDetailResponse,
)
def get_public_portfolio(
    portfolio_id: int,
    request: Request,
    current_user: OptionalCurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        portfolio = PublicPortfolioService.get_portfolio(
            session,
            portfolio_id=portfolio_id,
        )
    except PublicPortfolioNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    forwarded_for = request.headers.get(
        "x-forwarded-for"
    )

    if forwarded_for:
        client_ip = forwarded_for.split(
            ",",
            1,
        )[0].strip()
    elif request.client is not None:
        client_ip = request.client.host
    else:
        client_ip = "unknown"

    user_agent = request.headers.get(
        "user-agent",
        "",
    )
    session_id = request.headers.get(
        "x-session-id"
    )

    try:
        view_result = (
            PublicPortfolioViewService.register_view(
                session,
                portfolio_id=portfolio_id,
                current_user=current_user,
                client_ip=client_ip,
                user_agent=user_agent,
                session_id=session_id,
            )
        )

        if (
            view_result["counted"]
            and view_result["view_count"] is not None
        ):
            portfolio["view_count"] = (
                view_result["view_count"]
            )

    except Exception:
        session.rollback()

    return portfolio

