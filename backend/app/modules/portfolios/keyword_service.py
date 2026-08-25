from typing import Any

from sqlalchemy.orm import Session

from app.modules.audit.service import AuditService
from app.modules.event_outbox.service import EventOutboxService
from app.modules.portfolios import keyword_repository
from app.modules.portfolios import repository as portfolio_repository
from app.modules.portfolios.service import (
    CompanyPortfolioService,
    PortfolioNotFoundError,
    PortfolioStateConflictError,
)


EDITABLE_PORTFOLIO_STATUSES = {
    "draft",
    "rejected",
    "hidden",
}

MAX_KEYWORDS_PER_PORTFOLIO = 10


class PortfolioKeywordValidationError(ValueError):
    pass


class CompanyPortfolioKeywordService:
    @staticmethod
    def list_available(
        session: Session,
    ) -> list[dict[str, Any]]:
        return keyword_repository.list_active_keywords(
            session
        )

    @staticmethod
    def _get_company_portfolio(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        company = CompanyPortfolioService.get_company(
            session,
            user,
        )

        portfolio = portfolio_repository.find_company_portfolio(
            session,
            company_id=company["id"],
            portfolio_id=portfolio_id,
        )

        if portfolio is None:
            raise PortfolioNotFoundError(
                "포트폴리오를 찾을 수 없습니다."
            )

        return company, portfolio

    @staticmethod
    def list_selected(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
    ) -> dict[str, Any]:
        CompanyPortfolioKeywordService._get_company_portfolio(
            session,
            user=user,
            portfolio_id=portfolio_id,
        )

        keywords = (
            keyword_repository.list_portfolio_keywords(
                session,
                portfolio_id=portfolio_id,
            )
        )

        return {
            "portfolio_id": portfolio_id,
            "keywords": keywords,
        }

    @staticmethod
    def replace_selected(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
        keyword_ids: list[int],
    ) -> dict[str, Any]:
        company, portfolio = (
            CompanyPortfolioKeywordService
            ._get_company_portfolio(
                session,
                user=user,
                portfolio_id=portfolio_id,
            )
        )

        CompanyPortfolioService.require_editor(company)

        if portfolio["status"] not in (
            EDITABLE_PORTFOLIO_STATUSES
        ):
            raise PortfolioStateConflictError(
                "검수 중이거나 공개된 포트폴리오의 "
                "키워드는 변경할 수 없습니다."
            )

        if len(keyword_ids) > MAX_KEYWORDS_PER_PORTFOLIO:
            raise PortfolioKeywordValidationError(
                "포트폴리오 키워드는 최대 "
                f"{MAX_KEYWORDS_PER_PORTFOLIO}개까지 "
                "선택할 수 있습니다."
            )

        active_keywords = (
            keyword_repository.find_active_keywords_by_ids(
                session,
                keyword_ids=keyword_ids,
            )
        )

        active_keyword_ids = {
            keyword["id"]
            for keyword in active_keywords
        }

        requested_keyword_ids = set(keyword_ids)

        if active_keyword_ids != requested_keyword_ids:
            invalid_ids = sorted(
                requested_keyword_ids
                - active_keyword_ids
            )

            raise PortfolioKeywordValidationError(
                "존재하지 않거나 비활성화된 "
                "키워드가 포함되어 있습니다: "
                + ", ".join(
                    str(keyword_id)
                    for keyword_id in invalid_ids
                )
            )

        before_keywords = (
            keyword_repository.list_portfolio_keywords(
                session,
                portfolio_id=portfolio_id,
            )
        )

        before_ids = [
            keyword["id"]
            for keyword in before_keywords
        ]

        try:
            keyword_repository.replace_portfolio_keywords(
                session,
                portfolio_id=portfolio_id,
                keyword_ids=keyword_ids,
            )

            selected_keywords = (
                keyword_repository.list_portfolio_keywords(
                    session,
                    portfolio_id=portfolio_id,
                )
            )

            after_ids = [
                keyword["id"]
                for keyword in selected_keywords
            ]

            audit_id = AuditService.record(
                session=session,
                admin_user_id=None,
                action_type="portfolio.keywords_updated",
                target_type="portfolio",
                target_id=portfolio_id,
                before_data={
                    "keyword_ids": before_ids,
                },
                after_data={
                    "keyword_ids": after_ids,
                },
                reason="업체 포트폴리오 키워드 변경",
                metadata={
                    "source": "company_portfolio",
                    "actor_user_id": user["id"],
                    "company_id": company["id"],
                    "member_role": company["member_role"],
                },
            )

            EventOutboxService.publish(
                session=session,
                event_name="PortfolioKeywordsUpdated",
                aggregate_type="portfolio",
                aggregate_id=str(portfolio_id),
                payload={
                    "portfolio_id": portfolio_id,
                    "company_id": company["id"],
                    "actor_user_id": user["id"],
                    "keyword_ids": after_ids,
                    "audit_id": audit_id,
                },
                metadata={
                    "source": "company_portfolio",
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            "portfolio_id": portfolio_id,
            "keyword_count": len(selected_keywords),
            "keywords": selected_keywords,
            "message": (
                "포트폴리오 키워드가 저장되었습니다."
            ),
        }
