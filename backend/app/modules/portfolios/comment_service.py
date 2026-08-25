from typing import Any

from sqlalchemy.orm import Session

from app.modules.event_outbox.service import EventOutboxService
from app.modules.portfolios import comment_repository


class PortfolioCommentTargetNotFoundError(ValueError):
    pass


class PortfolioCommentNotFoundError(ValueError):
    pass


class PortfolioCommentAccessDeniedError(ValueError):
    pass


class PortfolioCommentValidationError(ValueError):
    pass


def build_comment_response(
    comment: dict[str, Any],
    *,
    author: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": comment["id"],
        "portfolio_id": comment["portfolio_id"],
        "parent_id": comment["parent_id"],
        "content": comment["content"],
        "status": comment["status"],
        "author": {
            "id": author["id"],
            "name": author["name"],
            "nickname": author["nickname"],
        },
        "created_at": comment["created_at"],
        "updated_at": comment["updated_at"],
    }


class PortfolioCommentService:
    @staticmethod
    def list_comments(
        session: Session,
        *,
        portfolio_id: int,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        target = comment_repository.find_public_comment_target(
            session,
            portfolio_id=portfolio_id,
        )

        if target is None:
            raise PortfolioCommentTargetNotFoundError(
                "공개된 포트폴리오를 찾을 수 없습니다."
            )

        rows = comment_repository.list_visible_comments(
            session,
            portfolio_id=portfolio_id,
            limit=limit,
            offset=offset,
        )

        items = []

        for row in rows:
            items.append(
                {
                    "id": row["id"],
                    "portfolio_id": row["portfolio_id"],
                    "parent_id": row["parent_id"],
                    "content": row["content"],
                    "status": row["status"],
                    "author": {
                        "id": row["author_id"],
                        "name": row["author_name"],
                        "nickname": row["author_nickname"],
                    },
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )

        total = comment_repository.count_visible_comments(
            session,
            portfolio_id=portfolio_id,
        )

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    def create_comment(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
        content: str,
        parent_id: int | None,
    ) -> dict[str, Any]:
        target = comment_repository.find_public_comment_target(
            session,
            portfolio_id=portfolio_id,
        )

        if target is None:
            raise PortfolioCommentTargetNotFoundError(
                "공개된 포트폴리오를 찾을 수 없습니다."
            )

        if parent_id is not None:
            parent = comment_repository.find_comment(
                session,
                comment_id=parent_id,
            )

            if (
                parent is None
                or parent["portfolio_id"] != portfolio_id
                or parent["status"] != "visible"
                or parent["deleted_at"] is not None
            ):
                raise PortfolioCommentValidationError(
                    "답글을 작성할 대상 댓글을 찾을 수 없습니다."
                )

            if parent["parent_id"] is not None:
                raise PortfolioCommentValidationError(
                    "답글에는 다시 답글을 작성할 수 없습니다."
                )

        user_id = int(user["id"])

        try:
            comment = comment_repository.create_comment(
                session,
                portfolio_id=portfolio_id,
                user_id=user_id,
                parent_id=parent_id,
                content=content,
            )

            comment_count = (
                comment_repository.increment_comment_count(
                    session,
                    portfolio_id=portfolio_id,
                )
            )

            EventOutboxService.publish(
                session=session,
                event_name="PortfolioCommentCreated",
                aggregate_type="portfolio",
                aggregate_id=str(portfolio_id),
                payload={
                    "portfolio_id": portfolio_id,
                    "company_id": target["company_id"],
                    "comment_id": comment["id"],
                    "user_id": user_id,
                    "parent_id": parent_id,
                    "comment_count": comment_count,
                },
                metadata={
                    "source": "public_portfolio",
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        author = comment_repository.get_comment_author(
            session,
            user_id=user_id,
        )

        return build_comment_response(
            comment,
            author=author,
        )

    @staticmethod
    def update_comment(
        session: Session,
        *,
        user: dict[str, Any],
        comment_id: int,
        content: str,
    ) -> dict[str, Any]:
        existing = comment_repository.find_comment(
            session,
            comment_id=comment_id,
        )

        if (
            existing is None
            or existing["status"] != "visible"
            or existing["deleted_at"] is not None
        ):
            raise PortfolioCommentNotFoundError(
                "댓글을 찾을 수 없습니다."
            )

        user_id = int(user["id"])

        if existing["user_id"] != user_id:
            raise PortfolioCommentAccessDeniedError(
                "본인이 작성한 댓글만 수정할 수 있습니다."
            )

        target = comment_repository.find_public_comment_target(
            session,
            portfolio_id=existing["portfolio_id"],
        )

        if target is None:
            raise PortfolioCommentTargetNotFoundError(
                "공개된 포트폴리오를 찾을 수 없습니다."
            )

        try:
            updated = comment_repository.update_comment(
                session,
                comment_id=comment_id,
                user_id=user_id,
                content=content,
            )

            if updated is None:
                raise PortfolioCommentNotFoundError(
                    "댓글을 수정하지 못했습니다."
                )

            EventOutboxService.publish(
                session=session,
                event_name="PortfolioCommentUpdated",
                aggregate_type="portfolio",
                aggregate_id=str(existing["portfolio_id"]),
                payload={
                    "portfolio_id": existing["portfolio_id"],
                    "company_id": target["company_id"],
                    "comment_id": comment_id,
                    "user_id": user_id,
                },
                metadata={
                    "source": "public_portfolio",
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        author = comment_repository.get_comment_author(
            session,
            user_id=user_id,
        )

        return build_comment_response(
            updated,
            author=author,
        )

    @staticmethod
    def delete_comment(
        session: Session,
        *,
        user: dict[str, Any],
        comment_id: int,
    ) -> dict[str, Any]:
        existing = comment_repository.find_comment(
            session,
            comment_id=comment_id,
        )

        if (
            existing is None
            or existing["status"] != "visible"
            or existing["deleted_at"] is not None
        ):
            raise PortfolioCommentNotFoundError(
                "댓글을 찾을 수 없습니다."
            )

        user_id = int(user["id"])

        if existing["user_id"] != user_id:
            raise PortfolioCommentAccessDeniedError(
                "본인이 작성한 댓글만 삭제할 수 있습니다."
            )

        try:
            deleted = comment_repository.soft_delete_comment(
                session,
                comment_id=comment_id,
                user_id=user_id,
            )

            if deleted is None:
                raise PortfolioCommentNotFoundError(
                    "댓글을 삭제하지 못했습니다."
                )

            comment_count = (
                comment_repository.decrement_comment_count(
                    session,
                    portfolio_id=existing["portfolio_id"],
                )
            )

            EventOutboxService.publish(
                session=session,
                event_name="PortfolioCommentDeleted",
                aggregate_type="portfolio",
                aggregate_id=str(existing["portfolio_id"]),
                payload={
                    "portfolio_id": existing["portfolio_id"],
                    "comment_id": comment_id,
                    "user_id": user_id,
                    "comment_count": comment_count,
                },
                metadata={
                    "source": "public_portfolio",
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            "comment_id": comment_id,
            "portfolio_id": existing["portfolio_id"],
            "comment_count": comment_count,
            "message": "댓글이 삭제되었습니다.",
        }
