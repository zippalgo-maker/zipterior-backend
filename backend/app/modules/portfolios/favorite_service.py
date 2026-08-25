from typing import Any

from sqlalchemy.orm import Session

from app.modules.event_outbox.service import EventOutboxService
from app.modules.portfolios import (
    favorite_repository,
    public_repository,
)
from app.modules.portfolios.public_service import (
    build_public_portfolio,
)


class PortfolioFavoriteTargetNotFoundError(ValueError):
    pass


class PortfolioFavoriteService:
    @staticmethod
    def get_status(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
    ) -> dict[str, Any]:
        target = favorite_repository.find_public_favorite_target(
            session,
            portfolio_id=portfolio_id,
        )

        if target is None:
            raise PortfolioFavoriteTargetNotFoundError(
                "공개된 포트폴리오를 찾을 수 없습니다."
            )

        favorited = favorite_repository.has_favorite(
            session,
            user_id=int(user["id"]),
            portfolio_id=portfolio_id,
        )

        return {
            "portfolio_id": portfolio_id,
            "favorited": favorited,
        }

    @staticmethod
    def add(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
    ) -> dict[str, Any]:
        target = favorite_repository.find_public_favorite_target(
            session,
            portfolio_id=portfolio_id,
        )

        if target is None:
            raise PortfolioFavoriteTargetNotFoundError(
                "공개된 포트폴리오를 찾을 수 없습니다."
            )

        user_id = int(user["id"])

        try:
            created = favorite_repository.create_favorite(
                session,
                user_id=user_id,
                portfolio_id=portfolio_id,
            )

            if created:
                EventOutboxService.publish(
                    session=session,
                    event_name="PortfolioFavorited",
                    aggregate_type="portfolio",
                    aggregate_id=str(portfolio_id),
                    payload={
                        "portfolio_id": portfolio_id,
                        "company_id": target["company_id"],
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

        return {
            "portfolio_id": portfolio_id,
            "favorited": True,
            "message": (
                "포트폴리오가 즐겨찾기에 등록되었습니다."
                if created
                else "이미 즐겨찾기에 등록된 포트폴리오입니다."
            ),
        }

    @staticmethod
    def remove(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
    ) -> dict[str, Any]:
        user_id = int(user["id"])

        try:
            deleted = favorite_repository.delete_favorite(
                session,
                user_id=user_id,
                portfolio_id=portfolio_id,
            )

            if deleted:
                EventOutboxService.publish(
                    session=session,
                    event_name="PortfolioUnfavorited",
                    aggregate_type="portfolio",
                    aggregate_id=str(portfolio_id),
                    payload={
                        "portfolio_id": portfolio_id,
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

        return {
            "portfolio_id": portfolio_id,
            "favorited": False,
            "message": (
                "포트폴리오 즐겨찾기가 해제되었습니다."
                if deleted
                else "등록된 즐겨찾기가 없습니다."
            ),
        }

    @staticmethod
    def list_mine(
        session: Session,
        *,
        user: dict[str, Any],
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        user_id = int(user["id"])

        rows = favorite_repository.list_user_favorites(
            session,
            user_id=user_id,
            limit=limit,
            offset=offset,
        )

        items = []

        for row in rows:
            keywords = (
                public_repository
                .list_public_portfolio_keywords(
                    session,
                    portfolio_id=row["id"],
                )
            )

            portfolio = build_public_portfolio(
                row,
                keywords=keywords,
            )

            items.append(
                {
                    "favorited_at": row["favorited_at"],
                    "portfolio": portfolio,
                }
            )

        total = favorite_repository.count_user_favorites(
            session,
            user_id=user_id,
        )

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
