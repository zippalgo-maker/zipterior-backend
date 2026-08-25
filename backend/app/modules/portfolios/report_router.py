from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentUser
from app.core.database import get_db
from app.modules.portfolios.report_schemas import (
    CommentReportCreateRequest,
    CommentReportResponse,
)
from app.modules.portfolios.report_service import (
    CommentReportConflictError,
    CommentReportService,
    CommentReportTargetNotFoundError,
    CommentReportValidationError,
)


router = APIRouter(
    tags=["comment-reports"],
)


@router.post(
    "/api/v1/comments/{comment_id}/report",
    response_model=CommentReportResponse,
    status_code=status.HTTP_201_CREATED,
)
def report_comment(
    comment_id: int,
    payload: CommentReportCreateRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return CommentReportService.create(
            session,
            user=current_user,
            comment_id=comment_id,
            reason_code=payload.reason_code,
            description=payload.description,
        )

    except CommentReportTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except CommentReportConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except CommentReportValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
