from typing import Any

from sqlalchemy.orm import Session

from app.modules.admin import comment_moderation_repository
from app.modules.audit.service import AuditService
from app.modules.event_outbox.service import EventOutboxService


class AdminCommentReportNotFoundError(ValueError):
    pass


class AdminCommentNotFoundError(ValueError):
    pass


class AdminCommentStateConflictError(ValueError):
    pass


class AdminCommentModerationService:
    @staticmethod
    def list_reports(
        session: Session,
        *,
        report_status: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        items = (
            comment_moderation_repository
            .list_comment_reports(
                session,
                report_status=report_status,
                limit=limit,
                offset=offset,
            )
        )

        total = (
            comment_moderation_repository
            .count_comment_reports(
                session,
                report_status=report_status,
            )
        )

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    def review_report(
        session: Session,
        *,
        report_id: int,
        report_status: str,
        handled_note: str | None,
        admin_user_id: int,
    ) -> dict[str, Any]:
        existing = (
            comment_moderation_repository
            .find_comment_report(
                session,
                report_id=report_id,
            )
        )

        if existing is None:
            raise AdminCommentReportNotFoundError(
                "댓글 신고를 찾을 수 없습니다."
            )

        try:
            result = (
                comment_moderation_repository
                .review_comment_report(
                    session,
                    report_id=report_id,
                    report_status=report_status,
                    admin_user_id=admin_user_id,
                    handled_note=handled_note,
                )
            )

            audit_id = AuditService.record(
                session=session,
                admin_user_id=admin_user_id,
                action_type="comment.report_reviewed",
                target_type="report",
                target_id=report_id,
                before_data={
                    "status": existing["status"],
                },
                after_data={
                    "status": report_status,
                    "handled_note": handled_note,
                },
                reason="댓글 신고 관리자 검토",
                metadata={
                    "source": "comment_moderation",
                    "comment_id": existing["comment_id"],
                },
            )

            EventOutboxService.publish(
                session=session,
                event_name="CommentReportReviewed",
                aggregate_type="report",
                aggregate_id=str(report_id),
                payload={
                    "report_id": report_id,
                    "comment_id": existing["comment_id"],
                    "status": report_status,
                    "admin_user_id": admin_user_id,
                    "audit_id": audit_id,
                },
                metadata={
                    "source": "comment_moderation",
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            "report_id": result["id"],
            "status": result["status"],
            "handled_by": result["handled_by"],
            "handled_note": result["handled_note"],
            "handled_at": result["handled_at"],
            "message": "댓글 신고 검토 상태가 변경되었습니다.",
        }

    @staticmethod
    def hide_comment(
        session: Session,
        *,
        comment_id: int,
        reason: str,
        admin_user_id: int,
    ) -> dict[str, Any]:
        comment = (
            comment_moderation_repository
            .find_comment_for_moderation(
                session,
                comment_id=comment_id,
            )
        )

        if comment is None or comment["deleted_at"] is not None:
            raise AdminCommentNotFoundError(
                "댓글을 찾을 수 없습니다."
            )

        if comment["status"] != "visible":
            raise AdminCommentStateConflictError(
                "현재 상태에서는 댓글을 숨김 처리할 수 없습니다."
            )

        try:
            changed = comment_moderation_repository.hide_comment(
                session,
                comment_id=comment_id,
            )

            if not changed:
                raise AdminCommentStateConflictError(
                    "댓글을 숨김 처리하지 못했습니다."
                )

            comment_count = (
                comment_moderation_repository
                .decrement_comment_count(
                    session,
                    portfolio_id=comment["portfolio_id"],
                )
            )

            audit_id = AuditService.record(
                session=session,
                admin_user_id=admin_user_id,
                action_type="comment.hidden",
                target_type="portfolio_comment",
                target_id=comment_id,
                before_data={
                    "status": "visible",
                },
                after_data={
                    "status": "hidden",
                },
                reason=reason,
                metadata={
                    "source": "comment_moderation",
                    "portfolio_id": comment["portfolio_id"],
                },
            )

            EventOutboxService.publish(
                session=session,
                event_name="CommentHidden",
                aggregate_type="portfolio_comment",
                aggregate_id=str(comment_id),
                payload={
                    "comment_id": comment_id,
                    "portfolio_id": comment["portfolio_id"],
                    "admin_user_id": admin_user_id,
                    "comment_count": comment_count,
                    "audit_id": audit_id,
                },
                metadata={
                    "source": "comment_moderation",
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            "comment_id": comment_id,
            "portfolio_id": comment["portfolio_id"],
            "status": "hidden",
            "comment_count": comment_count,
            "message": "댓글이 숨김 처리되었습니다.",
        }

    @staticmethod
    def restore_comment(
        session: Session,
        *,
        comment_id: int,
        reason: str,
        admin_user_id: int,
    ) -> dict[str, Any]:
        comment = (
            comment_moderation_repository
            .find_comment_for_moderation(
                session,
                comment_id=comment_id,
            )
        )

        if comment is None or comment["deleted_at"] is not None:
            raise AdminCommentNotFoundError(
                "댓글을 찾을 수 없습니다."
            )

        if comment["status"] != "hidden":
            raise AdminCommentStateConflictError(
                "숨김 상태의 댓글만 복원할 수 있습니다."
            )

        try:
            changed = (
                comment_moderation_repository.restore_comment(
                    session,
                    comment_id=comment_id,
                )
            )

            if not changed:
                raise AdminCommentStateConflictError(
                    "댓글을 복원하지 못했습니다."
                )

            comment_count = (
                comment_moderation_repository
                .increment_comment_count(
                    session,
                    portfolio_id=comment["portfolio_id"],
                )
            )

            audit_id = AuditService.record(
                session=session,
                admin_user_id=admin_user_id,
                action_type="comment.restored",
                target_type="portfolio_comment",
                target_id=comment_id,
                before_data={
                    "status": "hidden",
                },
                after_data={
                    "status": "visible",
                },
                reason=reason,
                metadata={
                    "source": "comment_moderation",
                    "portfolio_id": comment["portfolio_id"],
                },
            )

            EventOutboxService.publish(
                session=session,
                event_name="CommentRestored",
                aggregate_type="portfolio_comment",
                aggregate_id=str(comment_id),
                payload={
                    "comment_id": comment_id,
                    "portfolio_id": comment["portfolio_id"],
                    "admin_user_id": admin_user_id,
                    "comment_count": comment_count,
                    "audit_id": audit_id,
                },
                metadata={
                    "source": "comment_moderation",
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            "comment_id": comment_id,
            "portfolio_id": comment["portfolio_id"],
            "status": "visible",
            "comment_count": comment_count,
            "message": "댓글이 다시 공개되었습니다.",
        }
