from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.common.dependencies import CurrentAdmin
from app.core.database import get_db
from app.modules.admin.comment_moderation_schemas import (
    AdminCommentModerationRequest,
    AdminCommentModerationResponse,
    AdminCommentReportListResponse,
    AdminCommentReportReviewRequest,
    AdminCommentReportReviewResponse,
)
from app.modules.admin.comment_moderation_service import (
    AdminCommentModerationService,
    AdminCommentNotFoundError,
    AdminCommentReportNotFoundError,
    AdminCommentStateConflictError,
)


router = APIRouter(
    tags=["admin-comment-moderation"],
)


def handle_moderation_error(exc: ValueError) -> None:
    if isinstance(
        exc,
        (
            AdminCommentReportNotFoundError,
            AdminCommentNotFoundError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=str(exc),
    ) from exc


@router.get(
    "/api/v1/admin/comment-reports",
    response_model=AdminCommentReportListResponse,
)
def list_comment_reports(
    current_admin: CurrentAdmin,
    report_status: Literal[
        "received",
        "reviewing",
        "resolved",
        "rejected",
    ] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> dict:
    return AdminCommentModerationService.list_reports(
        session,
        report_status=report_status,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/api/v1/admin/comment-reports/{report_id}/review",
    response_model=AdminCommentReportReviewResponse,
)
def review_comment_report(
    report_id: int,
    payload: AdminCommentReportReviewRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminCommentModerationService.review_report(
            session,
            report_id=report_id,
            report_status=payload.status,
            handled_note=payload.handled_note,
            admin_user_id=current_admin["id"],
        )
    except (
        AdminCommentReportNotFoundError,
        AdminCommentStateConflictError,
    ) as exc:
        handle_moderation_error(exc)


@router.post(
    "/api/v1/admin/comments/{comment_id}/hide",
    response_model=AdminCommentModerationResponse,
)
def hide_comment(
    comment_id: int,
    payload: AdminCommentModerationRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminCommentModerationService.hide_comment(
            session,
            comment_id=comment_id,
            reason=payload.reason,
            admin_user_id=current_admin["id"],
        )
    except (
        AdminCommentNotFoundError,
        AdminCommentStateConflictError,
    ) as exc:
        handle_moderation_error(exc)


@router.post(
    "/api/v1/admin/comments/{comment_id}/restore",
    response_model=AdminCommentModerationResponse,
)
def restore_comment(
    comment_id: int,
    payload: AdminCommentModerationRequest,
    current_admin: CurrentAdmin,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return AdminCommentModerationService.restore_comment(
            session,
            comment_id=comment_id,
            reason=payload.reason,
            admin_user_id=current_admin["id"],
        )
    except (
        AdminCommentNotFoundError,
        AdminCommentStateConflictError,
    ) as exc:
        handle_moderation_error(exc)
