from typing import Any

from sqlalchemy.orm import Session

from app.modules.event_outbox.service import EventOutboxService
from app.modules.portfolios import report_repository


class CommentReportTargetNotFoundError(ValueError):
    pass


class CommentReportConflictError(ValueError):
    pass


class CommentReportValidationError(ValueError):
    pass


class CommentReportService:
    @staticmethod
    def create(
        session: Session,
        *,
        user: dict[str, Any],
        comment_id: int,
        reason_code: str,
        description: str | None,
    ) -> dict[str, Any]:
        reporter_user_id = int(user["id"])

        target = report_repository.find_reportable_comment(
            session,
            comment_id=comment_id,
        )

        if target is None:
            raise CommentReportTargetNotFoundError(
                "신고할 수 있는 댓글을 찾을 수 없습니다."
            )

        if int(target["user_id"]) == reporter_user_id:
            raise CommentReportValidationError(
                "본인이 작성한 댓글은 신고할 수 없습니다."
            )

        existing = report_repository.find_existing_report(
            session,
            reporter_user_id=reporter_user_id,
            comment_id=comment_id,
        )

        if existing is not None:
            raise CommentReportConflictError(
                "이미 신고한 댓글입니다."
            )

        try:
            report = report_repository.create_comment_report(
                session,
                reporter_user_id=reporter_user_id,
                comment_id=comment_id,
                reason_code=reason_code,
                description=description,
            )

            EventOutboxService.publish(
                session=session,
                event_name="CommentReported",
                aggregate_type="portfolio_comment",
                aggregate_id=str(comment_id),
                payload={
                    "report_id": report["id"],
                    "comment_id": comment_id,
                    "portfolio_id": target["portfolio_id"],
                    "company_id": target["company_id"],
                    "reporter_user_id": reporter_user_id,
                    "reason_code": reason_code,
                },
                metadata={
                    "source": "portfolio_comment",
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            **report,
            "message": "댓글 신고가 접수되었습니다.",
        }
