from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentUser
from app.core.database import get_db
from app.modules.portfolios.comment_schemas import (
    PortfolioCommentCreateRequest,
    PortfolioCommentDeleteResponse,
    PortfolioCommentListResponse,
    PortfolioCommentResponse,
    PortfolioCommentUpdateRequest,
)
from app.modules.portfolios.comment_service import (
    PortfolioCommentAccessDeniedError,
    PortfolioCommentNotFoundError,
    PortfolioCommentService,
    PortfolioCommentTargetNotFoundError,
    PortfolioCommentValidationError,
)


router = APIRouter(
    tags=["portfolio-comments"],
)


def handle_comment_error(
    exc: ValueError,
) -> None:
    if isinstance(
        exc,
        (
            PortfolioCommentTargetNotFoundError,
            PortfolioCommentNotFoundError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if isinstance(exc, PortfolioCommentAccessDeniedError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=str(exc),
    ) from exc


@router.get(
    "/api/v1/portfolios/{portfolio_id}/comments",
    response_model=PortfolioCommentListResponse,
)
def list_portfolio_comments(
    portfolio_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> dict:
    try:
        return PortfolioCommentService.list_comments(
            session,
            portfolio_id=portfolio_id,
            limit=limit,
            offset=offset,
        )
    except PortfolioCommentTargetNotFoundError as exc:
        handle_comment_error(exc)


@router.post(
    "/api/v1/portfolios/{portfolio_id}/comments",
    response_model=PortfolioCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_portfolio_comment(
    portfolio_id: int,
    payload: PortfolioCommentCreateRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return PortfolioCommentService.create_comment(
            session,
            user=current_user,
            portfolio_id=portfolio_id,
            content=payload.content,
            parent_id=payload.parent_id,
        )
    except (
        PortfolioCommentTargetNotFoundError,
        PortfolioCommentValidationError,
    ) as exc:
        handle_comment_error(exc)


@router.patch(
    "/api/v1/comments/{comment_id}",
    response_model=PortfolioCommentResponse,
)
def update_portfolio_comment(
    comment_id: int,
    payload: PortfolioCommentUpdateRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return PortfolioCommentService.update_comment(
            session,
            user=current_user,
            comment_id=comment_id,
            content=payload.content,
        )
    except (
        PortfolioCommentTargetNotFoundError,
        PortfolioCommentNotFoundError,
        PortfolioCommentAccessDeniedError,
    ) as exc:
        handle_comment_error(exc)


@router.delete(
    "/api/v1/comments/{comment_id}",
    response_model=PortfolioCommentDeleteResponse,
)
def delete_portfolio_comment(
    comment_id: int,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return PortfolioCommentService.delete_comment(
            session,
            user=current_user,
            comment_id=comment_id,
        )
    except (
        PortfolioCommentNotFoundError,
        PortfolioCommentAccessDeniedError,
    ) as exc:
        handle_comment_error(exc)
