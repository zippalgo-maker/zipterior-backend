from typing import Any

from sqlalchemy.orm import Session

from app.modules.event_outbox.service import EventOutboxService
from app.modules.portfolios import like_repository


class PortfolioLikeTargetNotFoundError(ValueError):
    pass


class PublicPortfolioLikeService:
    @staticmethod
    def get_status(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
    ) -> dict[str, Any]:
        portfolio = (
            like_repository.find_public_portfolio_like_target(
                session,
                portfolio_id=portfolio_id,
            )
        )

        if portfolio is None:
            raise PortfolioLikeTargetNotFoundError(
                "공개된 포트폴리오를 찾을 수 없습니다."
            )

        liked = like_repository.has_portfolio_like(
            session,
            user_id=int(user["id"]),
            portfolio_id=portfolio_id,
        )

        return {
            "portfolio_id": portfolio_id,
            "liked": liked,
            "like_count": int(portfolio["like_count"]),
        }

    @staticmethod
    def like(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
    ) -> dict[str, Any]:
        portfolio = (
            like_repository.find_public_portfolio_like_target(
                session,
                portfolio_id=portfolio_id,
            )
        )

        if portfolio is None:
            raise PortfolioLikeTargetNotFoundError(
                "공개된 포트폴리오를 찾을 수 없습니다."
            )

        user_id = int(user["id"])

        try:
            created = like_repository.create_portfolio_like(
                session,
                user_id=user_id,
                portfolio_id=portfolio_id,
            )

            if created:
                like_count = (
                    like_repository
                    .increment_portfolio_like_count(
                        session,
                        portfolio_id=portfolio_id,
                    )
                )

                EventOutboxService.publish(
                    session=session,
                    event_name="PortfolioLiked",
                    aggregate_type="portfolio",
                    aggregate_id=str(portfolio_id),
                    payload={
                        "portfolio_id": portfolio_id,
                        "company_id": portfolio["company_id"],
                        "user_id": user_id,
                        "like_count": like_count,
                    },
                    metadata={
                        "source": "public_portfolio",
                    },
                )
            else:
                like_count = (
                    like_repository.get_portfolio_like_count(
                        session,
                        portfolio_id=portfolio_id,
                    )
                )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            "portfolio_id": portfolio_id,
            "liked": True,
            "like_count": like_count,
            "message": (
                "포트폴리오 좋아요가 등록되었습니다."
                if created
                else "이미 좋아요한 포트폴리오입니다."
            ),
        }

    @staticmethod
    def unlike(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
    ) -> dict[str, Any]:
        portfolio = (
            like_repository.find_public_portfolio_like_target(
                session,
                portfolio_id=portfolio_id,
            )
        )

        if portfolio is None:
            raise PortfolioLikeTargetNotFoundError(
                "공개된 포트폴리오를 찾을 수 없습니다."
            )

        user_id = int(user["id"])

        try:
            deleted = like_repository.delete_portfolio_like(
                session,
                user_id=user_id,
                portfolio_id=portfolio_id,
            )

            if deleted:
                like_count = (
                    like_repository
                    .decrement_portfolio_like_count(
                        session,
                        portfolio_id=portfolio_id,
                    )
                )

                EventOutboxService.publish(
                    session=session,
                    event_name="PortfolioUnliked",
                    aggregate_type="portfolio",
                    aggregate_id=str(portfolio_id),
                    payload={
                        "portfolio_id": portfolio_id,
                        "company_id": portfolio["company_id"],
                        "user_id": user_id,
                        "like_count": like_count,
                    },
                    metadata={
                        "source": "public_portfolio",
                    },
                )
            else:
                like_count = (
                    like_repository.get_portfolio_like_count(
                        session,
                        portfolio_id=portfolio_id,
                    )
                )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            "portfolio_id": portfolio_id,
            "liked": False,
            "like_count": like_count,
            "message": (
                "포트폴리오 좋아요가 취소되었습니다."
                if deleted
                else "등록된 좋아요가 없습니다."
            ),
        }
