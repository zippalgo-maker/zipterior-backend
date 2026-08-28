"""v1.10.1(2026-08-26): reviews 모듈 최초 구현."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentUser
from app.core.database import get_db
from app.modules.reviews.schemas import ReviewCreateRequest, ReviewListResponse, ReviewResponse
from app.modules.reviews.service import (
    ReviewAccessDeniedError,
    ReviewNotFoundError,
    ReviewService,
    ReviewStateConflictError,
    ReviewValidationError,
)

router = APIRouter(tags=["reviews"])


def handle_review_error(exc: ValueError) -> None:
    if isinstance(exc, ReviewNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, ReviewAccessDeniedError):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, ReviewStateConflictError):
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.post("/api/v1/reviews", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
def create_review(payload: ReviewCreateRequest, current_user: CurrentUser, session: Session = Depends(get_db)) -> dict:
    try:
        return ReviewService.create(session, user=current_user, payload=payload)
    except (ReviewAccessDeniedError, ReviewNotFoundError, ReviewStateConflictError, ReviewValidationError) as exc:
        handle_review_error(exc)


@router.get("/api/v1/reviews/mine", response_model=ReviewListResponse)
def list_my_reviews(
    current_user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> dict:
    try:
        return ReviewService.list_mine(session, user=current_user, limit=limit, offset=offset)
    except ReviewAccessDeniedError as exc:
        handle_review_error(exc)


@router.get("/api/v1/public/companies/{company_id}/reviews", response_model=ReviewListResponse)
def list_company_reviews(
    company_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> dict:
    return ReviewService.list_by_company(session, company_id=company_id, limit=limit, offset=offset)
