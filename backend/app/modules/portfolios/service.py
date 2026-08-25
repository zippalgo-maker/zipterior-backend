from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.modules.audit.service import AuditService
from app.modules.companies.service import (
    CompanyAccessDeniedError,
    CompanyMyPageService,
)
from app.modules.event_outbox.service import EventOutboxService
from app.modules.portfolios import repository
from app.modules.portfolios.schemas import (
    PortfolioCreateRequest,
    PortfolioComplexLocationRequest,
    PortfolioUpdateRequest,
)


class PortfolioNotFoundError(ValueError):
    pass


class PortfolioAccessDeniedError(ValueError):
    pass


class PortfolioValidationError(ValueError):
    pass


class PortfolioStateConflictError(ValueError):
    pass


class EmptyPortfolioUpdateError(ValueError):
    pass


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, (date, datetime)):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            key: json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]

    return value


class CompanyPortfolioService:
    @staticmethod
    def resolve_complex_location(
        session: Session,
        *,
        user: dict[str, Any],
        payload: PortfolioComplexLocationRequest,
    ) -> dict[str, Any]:
        company = CompanyPortfolioService.get_company(session, user)
        CompanyPortfolioService.require_editor(company)
        try:
            result = repository.upsert_complex_location(
                session,
                name=payload.name,
                road_address=payload.road_address or payload.address,
                jibun_address=payload.jibun_address,
                latitude=payload.latitude,
                longitude=payload.longitude,
            )
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise

    @staticmethod
    def match_complex_search_items(
        session: Session,
        *,
        user: dict[str, Any],
        items: list[dict],
    ) -> list[dict[str, Any]]:
        company = CompanyPortfolioService.get_company(session, user)
        CompanyPortfolioService.require_editor(company)

        return repository.match_complex_search_items(
            session,
            items,
        )

    @staticmethod
    def create_complex_registration_request(
        session: Session,
        *,
        user: dict[str, Any],
        payload: PortfolioComplexLocationRequest,
    ) -> dict[str, Any]:
        company = CompanyPortfolioService.get_company(session, user)
        CompanyPortfolioService.require_editor(company)

        try:
            result = repository.create_complex_registration_request(
                session,
                company_id=company["id"],
                name=payload.name,
                road_address=payload.road_address or payload.address,
                jibun_address=payload.jibun_address,
                latitude=payload.latitude,
                longitude=payload.longitude,
            )
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise

    @staticmethod
    def get_company(
        session: Session,
        user: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return CompanyMyPageService.get_me(
                session=session,
                user=user,
            )
        except CompanyAccessDeniedError as exc:
            raise PortfolioAccessDeniedError(
                str(exc)
            ) from exc

    @staticmethod
    def require_editor(
        company: dict[str, Any],
    ) -> None:
        if company["member_role"] not in {
            "owner",
            "manager",
        }:
            raise PortfolioAccessDeniedError(
                "업체 대표 또는 관리자만 포트폴리오를 변경할 수 있습니다."
            )

    @staticmethod
    def validate_apartment_relation(
        session: Session,
        *,
        complex_id: int | None,
        apartment_type_id: int | None,
    ) -> None:
        if apartment_type_id is not None and complex_id is None:
            raise PortfolioValidationError(
                "평형을 선택하려면 아파트 단지도 함께 선택해야 합니다."
            )

        if complex_id is not None:
            complex_record = repository.find_active_complex(
                session,
                complex_id,
            )

            if complex_record is None:
                raise PortfolioValidationError(
                    "사용할 수 없는 아파트 단지입니다."
                )

        if apartment_type_id is not None:
            apartment_type = repository.find_apartment_type(
                session,
                apartment_type_id,
            )

            if apartment_type is None:
                raise PortfolioValidationError(
                    "존재하지 않는 평형 정보입니다."
                )

            if apartment_type["complex_id"] != complex_id:
                raise PortfolioValidationError(
                    "선택한 평형이 해당 아파트 단지에 속하지 않습니다."
                )

    @staticmethod
    def validate_budget(
        *,
        budget_min: Decimal | None,
        budget_max: Decimal | None,
    ) -> None:
        if (
            budget_min is not None
            and budget_max is not None
            and budget_min > budget_max
        ):
            raise PortfolioValidationError(
                "최소 예산은 최대 예산보다 클 수 없습니다."
            )

    @staticmethod
    def list_portfolios(
        session: Session,
        *,
        user: dict[str, Any],
    ) -> list[dict[str, Any]]:
        company = CompanyPortfolioService.get_company(
            session,
            user,
        )

        return repository.list_company_portfolios(
            session,
            company_id=company["id"],
        )

    @staticmethod
    def get_portfolio(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
    ) -> dict[str, Any]:
        company = CompanyPortfolioService.get_company(
            session,
            user,
        )

        portfolio = repository.find_company_portfolio(
            session,
            company_id=company["id"],
            portfolio_id=portfolio_id,
        )

        if portfolio is None:
            raise PortfolioNotFoundError(
                "포트폴리오를 찾을 수 없습니다."
            )

        return portfolio

    @staticmethod
    def create_portfolio(
        session: Session,
        *,
        user: dict[str, Any],
        payload: PortfolioCreateRequest,
    ) -> dict[str, Any]:
        company = CompanyPortfolioService.get_company(
            session,
            user,
        )
        CompanyPortfolioService.require_editor(company)

        values = payload.model_dump()

        CompanyPortfolioService.validate_apartment_relation(
            session,
            complex_id=values.get("complex_id"),
            apartment_type_id=values.get(
                "apartment_type_id"
            ),
        )

        CompanyPortfolioService.validate_budget(
            budget_min=values.get("budget_min"),
            budget_max=values.get("budget_max"),
        )

        try:
            portfolio_id = repository.create_portfolio(
                session=session,
                company_id=company["id"],
                created_by_user_id=user["id"],
                values=values,
            )

            audit_id = AuditService.record(
                session=session,
                admin_user_id=None,
                action_type="portfolio.created",
                target_type="portfolio",
                target_id=portfolio_id,
                after_data={
                    **json_safe(values),
                    "company_id": company["id"],
                    "status": "draft",
                },
                reason="업체 포트폴리오 임시저장 생성",
                metadata={
                    "source": "company_portfolio",
                    "actor_user_id": user["id"],
                    "company_id": company["id"],
                    "member_role": company["member_role"],
                },
            )

            EventOutboxService.publish(
                session=session,
                event_name="PortfolioCreated",
                aggregate_type="portfolio",
                aggregate_id=str(portfolio_id),
                payload={
                    "portfolio_id": portfolio_id,
                    "company_id": company["id"],
                    "actor_user_id": user["id"],
                    "status": "draft",
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

        portfolio = repository.find_company_portfolio(
            session,
            company_id=company["id"],
            portfolio_id=portfolio_id,
        )

        if portfolio is None:
            raise PortfolioNotFoundError(
                "생성된 포트폴리오를 조회하지 못했습니다."
            )

        return portfolio

    @staticmethod
    def update_portfolio(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
        payload: PortfolioUpdateRequest,
    ) -> dict[str, Any]:
        company = CompanyPortfolioService.get_company(
            session,
            user,
        )
        CompanyPortfolioService.require_editor(company)

        portfolio = repository.find_company_portfolio(
            session,
            company_id=company["id"],
            portfolio_id=portfolio_id,
        )

        if portfolio is None:
            raise PortfolioNotFoundError(
                "포트폴리오를 찾을 수 없습니다."
            )

        if portfolio["status"] not in {
            "draft",
            "rejected",
            "hidden",
        }:
            raise PortfolioStateConflictError(
                "검수 중이거나 공개된 포트폴리오는 수정할 수 없습니다."
            )

        changes = payload.model_dump(
            exclude_unset=True,
        )

        if not changes:
            raise EmptyPortfolioUpdateError(
                "수정할 정보가 없습니다."
            )

        if "title" in changes and changes["title"] is None:
            raise PortfolioValidationError(
                "포트폴리오 제목은 비울 수 없습니다."
            )

        final_complex_id = changes.get(
            "complex_id",
            portfolio["complex_id"],
        )
        final_apartment_type_id = changes.get(
            "apartment_type_id",
            portfolio["apartment_type_id"],
        )

        if (
            "complex_id" in changes
            and final_complex_id
            != portfolio["complex_id"]
            and "apartment_type_id" not in changes
        ):
            final_apartment_type_id = None
            changes["apartment_type_id"] = None

        CompanyPortfolioService.validate_apartment_relation(
            session,
            complex_id=final_complex_id,
            apartment_type_id=final_apartment_type_id,
        )

        final_budget_min = changes.get(
            "budget_min",
            portfolio["budget_min"],
        )
        final_budget_max = changes.get(
            "budget_max",
            portfolio["budget_max"],
        )

        CompanyPortfolioService.validate_budget(
            budget_min=final_budget_min,
            budget_max=final_budget_max,
        )

        before_data = {
            key: json_safe(portfolio.get(key))
            for key in changes
        }

        try:
            updated = repository.update_portfolio(
                session=session,
                company_id=company["id"],
                portfolio_id=portfolio_id,
                changes=changes,
            )

            if not updated:
                raise PortfolioNotFoundError(
                    "포트폴리오를 수정하지 못했습니다."
                )

            updated_portfolio = (
                repository.find_company_portfolio(
                    session,
                    company_id=company["id"],
                    portfolio_id=portfolio_id,
                )
            )

            if updated_portfolio is None:
                raise PortfolioNotFoundError(
                    "수정된 포트폴리오를 조회하지 못했습니다."
                )

            after_data = {
                key: json_safe(
                    updated_portfolio.get(key)
                )
                for key in changes
            }

            audit_id = AuditService.record(
                session=session,
                admin_user_id=None,
                action_type="portfolio.updated",
                target_type="portfolio",
                target_id=portfolio_id,
                before_data=before_data,
                after_data=after_data,
                reason="업체 포트폴리오 수정",
                metadata={
                    "source": "company_portfolio",
                    "actor_user_id": user["id"],
                    "company_id": company["id"],
                    "member_role": company["member_role"],
                    "changed_fields": sorted(changes),
                },
            )

            EventOutboxService.publish(
                session=session,
                event_name="PortfolioUpdated",
                aggregate_type="portfolio",
                aggregate_id=str(portfolio_id),
                payload={
                    "portfolio_id": portfolio_id,
                    "company_id": company["id"],
                    "actor_user_id": user["id"],
                    "changed_fields": sorted(changes),
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

        return updated_portfolio

    @staticmethod
    def submit_portfolio(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
    ) -> dict[str, Any]:
        company = CompanyPortfolioService.get_company(
            session,
            user,
        )
        CompanyPortfolioService.require_editor(company)

        portfolio = repository.find_company_portfolio(
            session,
            company_id=company["id"],
            portfolio_id=portfolio_id,
        )

        if portfolio is None:
            raise PortfolioNotFoundError(
                "포트폴리오를 찾을 수 없습니다."
            )

        if portfolio["status"] not in {
            "draft",
            "rejected",
        }:
            raise PortfolioStateConflictError(
                "임시저장 또는 반려된 포트폴리오만 제출할 수 있습니다."
            )

        if not portfolio["title"]:
            raise PortfolioValidationError(
                "포트폴리오 제목이 필요합니다."
            )

        if not portfolio["description"]:
            raise PortfolioValidationError(
                "포트폴리오 상세 설명이 필요합니다."
            )

        try:
            submitted = repository.submit_portfolio(
                session=session,
                company_id=company["id"],
                portfolio_id=portfolio_id,
            )

            if not submitted:
                raise PortfolioStateConflictError(
                    "포트폴리오를 검수 요청 상태로 변경하지 못했습니다."
                )

            audit_id = AuditService.record(
                session=session,
                admin_user_id=None,
                action_type="portfolio.submitted",
                target_type="portfolio",
                target_id=portfolio_id,
                before_data={
                    "status": portfolio["status"],
                },
                after_data={
                    "status": "pending",
                },
                reason="업체 포트폴리오 관리자 검수 요청",
                metadata={
                    "source": "company_portfolio",
                    "actor_user_id": user["id"],
                    "company_id": company["id"],
                    "member_role": company["member_role"],
                },
            )

            EventOutboxService.publish(
                session=session,
                event_name="PortfolioSubmitted",
                aggregate_type="portfolio",
                aggregate_id=str(portfolio_id),
                payload={
                    "portfolio_id": portfolio_id,
                    "company_id": company["id"],
                    "actor_user_id": user["id"],
                    "status": "pending",
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
            "status": "pending",
            "message": "포트폴리오 검수 요청이 완료되었습니다.",
        }

    @staticmethod
    def delete_portfolio(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
    ) -> dict[str, Any]:
        company = CompanyPortfolioService.get_company(
            session,
            user,
        )
        CompanyPortfolioService.require_editor(company)

        portfolio = repository.find_company_portfolio(
            session,
            company_id=company["id"],
            portfolio_id=portfolio_id,
        )

        if portfolio is None:
            raise PortfolioNotFoundError(
                "포트폴리오를 찾을 수 없습니다."
            )

        if portfolio["status"] not in {
            "draft",
            "rejected",
            "hidden",
        }:
            raise PortfolioStateConflictError(
                "검수 중이거나 공개된 포트폴리오는 삭제할 수 없습니다."
            )

        try:
            deleted = repository.soft_delete_portfolio(
                session=session,
                company_id=company["id"],
                portfolio_id=portfolio_id,
            )

            if not deleted:
                raise PortfolioStateConflictError(
                    "포트폴리오를 삭제하지 못했습니다."
                )

            audit_id = AuditService.record(
                session=session,
                admin_user_id=None,
                action_type="portfolio.deleted",
                target_type="portfolio",
                target_id=portfolio_id,
                before_data={
                    "title": portfolio["title"],
                    "status": portfolio["status"],
                },
                after_data={
                    "deleted": True,
                },
                reason="업체 포트폴리오 삭제",
                metadata={
                    "source": "company_portfolio",
                    "actor_user_id": user["id"],
                    "company_id": company["id"],
                    "member_role": company["member_role"],
                },
            )

            EventOutboxService.publish(
                session=session,
                event_name="PortfolioDeleted",
                aggregate_type="portfolio",
                aggregate_id=str(portfolio_id),
                payload={
                    "portfolio_id": portfolio_id,
                    "company_id": company["id"],
                    "actor_user_id": user["id"],
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
            "message": "포트폴리오가 삭제되었습니다.",
        }

    @staticmethod
    def hide_portfolio(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
    ) -> dict[str, Any]:
        """v2.5.0: 업체가 스스로 승인된 포트폴리오를 비공개로 돌린다(재검수
        없음) -- 지도 마커/공개 화면에서 즉시 빠진다."""
        company = CompanyPortfolioService.get_company(session, user)
        CompanyPortfolioService.require_editor(company)

        portfolio = repository.find_company_portfolio(
            session, company_id=company["id"], portfolio_id=portfolio_id
        )
        if portfolio is None:
            raise PortfolioNotFoundError("포트폴리오를 찾을 수 없습니다.")
        if portfolio["status"] != "approved":
            raise PortfolioStateConflictError(
                "승인된 포트폴리오만 비공개로 전환할 수 있습니다."
            )

        try:
            hidden = repository.hide_portfolio(
                session, company_id=company["id"], portfolio_id=portfolio_id
            )
            if not hidden:
                raise PortfolioStateConflictError(
                    "포트폴리오를 비공개로 전환하지 못했습니다."
                )
            AuditService.record(
                session=session,
                admin_user_id=None,
                action_type="portfolio.hidden",
                target_type="portfolio",
                target_id=portfolio_id,
                before_data={"status": portfolio["status"]},
                after_data={"status": "hidden"},
                reason="업체 자체 비공개 전환",
                metadata={
                    "source": "company_portfolio",
                    "actor_user_id": user["id"],
                    "company_id": company["id"],
                },
            )
            session.commit()
        except Exception:
            session.rollback()
            raise

        return {"portfolio_id": portfolio_id, "status": "hidden", "message": "포트폴리오를 비공개로 전환했습니다."}

    @staticmethod
    def show_portfolio(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
    ) -> dict[str, Any]:
        """v2.5.0: 업체가 스스로 비공개(hidden)로 돌렸던 포트폴리오를 다시
        공개한다 -- 이미 한 번 승인됐던 것이라 관리자 재검수 없이 바로
        approved로 돌아간다."""
        company = CompanyPortfolioService.get_company(session, user)
        CompanyPortfolioService.require_editor(company)

        portfolio = repository.find_company_portfolio(
            session, company_id=company["id"], portfolio_id=portfolio_id
        )
        if portfolio is None:
            raise PortfolioNotFoundError("포트폴리오를 찾을 수 없습니다.")
        if portfolio["status"] != "hidden":
            raise PortfolioStateConflictError(
                "비공개 상태의 포트폴리오만 다시 공개할 수 있습니다."
            )

        try:
            shown = repository.show_portfolio(
                session, company_id=company["id"], portfolio_id=portfolio_id
            )
            if not shown:
                raise PortfolioStateConflictError(
                    "포트폴리오를 공개로 전환하지 못했습니다."
                )
            AuditService.record(
                session=session,
                admin_user_id=None,
                action_type="portfolio.unhidden",
                target_type="portfolio",
                target_id=portfolio_id,
                before_data={"status": portfolio["status"]},
                after_data={"status": "approved"},
                reason="업체 자체 공개 전환",
                metadata={
                    "source": "company_portfolio",
                    "actor_user_id": user["id"],
                    "company_id": company["id"],
                },
            )
            session.commit()
        except Exception:
            session.rollback()
            raise

        return {"portfolio_id": portfolio_id, "status": "approved", "message": "포트폴리오를 다시 공개했습니다."}

    @staticmethod
    def bulk_status(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_ids: list[int],
        action: str,
    ) -> dict[str, Any]:
        """v2.5.0: 업체 포트폴리오 관리 화면 체크박스(개별/전체선택) 일괄
        처리 -- submit(검수요청)/hide(비공개)/show(공개)만 허용한다. 관리자의
        승인 권한을 우회하지 않도록 승인(approve) 자체는 여기 포함하지 않음."""
        handlers = {
            "submit": CompanyPortfolioService.submit_portfolio,
            "hide": CompanyPortfolioService.hide_portfolio,
            "show": CompanyPortfolioService.show_portfolio,
        }
        handler = handlers.get(action)
        if handler is None:
            raise PortfolioValidationError(f"알 수 없는 처리입니다: {action}")

        succeeded: list[int] = []
        failed: list[dict[str, Any]] = []
        for portfolio_id in portfolio_ids:
            try:
                handler(session, user=user, portfolio_id=portfolio_id)
                succeeded.append(portfolio_id)
            except (
                PortfolioNotFoundError,
                PortfolioStateConflictError,
                PortfolioValidationError,
            ) as exc:
                failed.append({"portfolio_id": portfolio_id, "error": str(exc)})
        return {"succeeded": succeeded, "failed": failed}

# ============================================================
# v2.1.8 Structured portfolio spaces
#
# Core service는 업체/관리자/향후 Excel+ZIP import가
# 동일 저장 규칙을 재사용하기 위한 공통 계층이다.
# ============================================================

class PortfolioSpaceNotFoundError(ValueError):
    pass


class PortfolioSpaceHasImagesError(ValueError):
    pass


class PortfolioSpaceCoreService:
    @staticmethod
    def list_spaces(
        session: Session,
        *,
        portfolio_id: int,
    ) -> list[dict[str, Any]]:
        return repository.list_portfolio_spaces(
            session,
            portfolio_id=portfolio_id,
        )

    @staticmethod
    def create_space(
        session: Session,
        *,
        portfolio_id: int,
        payload,
    ) -> dict[str, Any]:
        space_number = repository.next_portfolio_space_number(
            session,
            portfolio_id=portfolio_id,
            space_code=payload.space_code,
        )

        sort_order = payload.sort_order

        if sort_order is None:
            sort_order = repository.next_portfolio_space_sort_order(
                session,
                portfolio_id=portfolio_id,
            )

        space_id = repository.create_portfolio_space(
            session,
            portfolio_id=portfolio_id,
            space_code=payload.space_code,
            space_name=payload.space_name,
            space_number=space_number,
            description=payload.description,
            sort_order=sort_order,
        )

        space = repository.find_portfolio_space(
            session,
            portfolio_id=portfolio_id,
            space_id=space_id,
        )

        if space is None:
            raise PortfolioSpaceNotFoundError(
                "생성된 공간을 조회하지 못했습니다."
            )

        return space

    @staticmethod
    def update_space(
        session: Session,
        *,
        portfolio_id: int,
        space_id: int,
        payload,
    ) -> dict[str, Any]:
        current = repository.find_portfolio_space(
            session,
            portfolio_id=portfolio_id,
            space_id=space_id,
        )

        if current is None:
            raise PortfolioSpaceNotFoundError(
                "포트폴리오 공간을 찾을 수 없습니다."
            )

        changes = payload.model_dump(exclude_unset=True)

        if not changes:
            raise EmptyPortfolioUpdateError(
                "수정할 공간 정보가 없습니다."
            )

        if (
            "space_name" in changes
            and changes["space_name"] is None
        ):
            raise PortfolioValidationError(
                "공간명은 비울 수 없습니다."
            )

        updated = repository.update_portfolio_space(
            session,
            portfolio_id=portfolio_id,
            space_id=space_id,
            changes=changes,
        )

        if not updated:
            raise PortfolioSpaceNotFoundError(
                "포트폴리오 공간을 수정하지 못했습니다."
            )

        result = repository.find_portfolio_space(
            session,
            portfolio_id=portfolio_id,
            space_id=space_id,
        )

        if result is None:
            raise PortfolioSpaceNotFoundError(
                "수정된 공간을 조회하지 못했습니다."
            )

        return result

    @staticmethod
    def delete_space(
        session: Session,
        *,
        portfolio_id: int,
        space_id: int,
    ) -> None:
        space = repository.find_portfolio_space(
            session,
            portfolio_id=portfolio_id,
            space_id=space_id,
        )

        if space is None:
            raise PortfolioSpaceNotFoundError(
                "포트폴리오 공간을 찾을 수 없습니다."
            )

        image_count = repository.count_portfolio_space_images(
            session,
            portfolio_id=portfolio_id,
            space_id=space_id,
        )

        if image_count > 0:
            raise PortfolioSpaceHasImagesError(
                "사진이 등록된 공간은 바로 삭제할 수 없습니다. "
                "사진을 먼저 삭제하거나 다른 공간으로 이동해 주세요."
            )

        deleted = repository.delete_portfolio_space(
            session,
            portfolio_id=portfolio_id,
            space_id=space_id,
        )

        if not deleted:
            raise PortfolioSpaceNotFoundError(
                "포트폴리오 공간을 삭제하지 못했습니다."
            )


class CompanyPortfolioSpaceService:
    EDITABLE_STATUSES = {
        "draft",
        "rejected",
        "hidden",
    }

    @staticmethod
    def _get_context(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
        require_editable: bool,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        company = CompanyPortfolioService.get_company(
            session,
            user,
        )

        if require_editable:
            CompanyPortfolioService.require_editor(company)

        portfolio = repository.find_company_portfolio(
            session,
            company_id=company["id"],
            portfolio_id=portfolio_id,
        )

        if portfolio is None:
            raise PortfolioNotFoundError(
                "포트폴리오를 찾을 수 없습니다."
            )

        if (
            require_editable
            and portfolio["status"]
            not in CompanyPortfolioSpaceService.EDITABLE_STATUSES
        ):
            raise PortfolioStateConflictError(
                "검수 중이거나 공개된 포트폴리오의 "
                "공간 정보는 변경할 수 없습니다."
            )

        return company, portfolio

    @staticmethod
    def list_spaces(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
    ) -> list[dict[str, Any]]:
        CompanyPortfolioSpaceService._get_context(
            session,
            user=user,
            portfolio_id=portfolio_id,
            require_editable=False,
        )

        return PortfolioSpaceCoreService.list_spaces(
            session,
            portfolio_id=portfolio_id,
        )

    @staticmethod
    def create_space(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
        payload,
    ) -> dict[str, Any]:
        company, _ = CompanyPortfolioSpaceService._get_context(
            session,
            user=user,
            portfolio_id=portfolio_id,
            require_editable=True,
        )

        try:
            result = PortfolioSpaceCoreService.create_space(
                session,
                portfolio_id=portfolio_id,
                payload=payload,
            )

            AuditService.record(
                session=session,
                admin_user_id=None,
                action_type="portfolio.space.created",
                target_type="portfolio_space",
                target_id=result["id"],
                after_data=json_safe(result),
                reason="업체 포트폴리오 공간 생성",
                metadata={
                    "source": "company_portfolio",
                    "portfolio_id": portfolio_id,
                    "company_id": company["id"],
                    "actor_user_id": user["id"],
                },
            )

            session.commit()
            return result

        except Exception:
            session.rollback()
            raise

    @staticmethod
    def update_space(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
        space_id: int,
        payload,
    ) -> dict[str, Any]:
        company, _ = CompanyPortfolioSpaceService._get_context(
            session,
            user=user,
            portfolio_id=portfolio_id,
            require_editable=True,
        )

        before = repository.find_portfolio_space(
            session,
            portfolio_id=portfolio_id,
            space_id=space_id,
        )

        try:
            result = PortfolioSpaceCoreService.update_space(
                session,
                portfolio_id=portfolio_id,
                space_id=space_id,
                payload=payload,
            )

            AuditService.record(
                session=session,
                admin_user_id=None,
                action_type="portfolio.space.updated",
                target_type="portfolio_space",
                target_id=space_id,
                before_data=json_safe(before or {}),
                after_data=json_safe(result),
                reason="업체 포트폴리오 공간 수정",
                metadata={
                    "source": "company_portfolio",
                    "portfolio_id": portfolio_id,
                    "company_id": company["id"],
                    "actor_user_id": user["id"],
                },
            )

            session.commit()
            return result

        except Exception:
            session.rollback()
            raise

    @staticmethod
    def delete_space(
        session: Session,
        *,
        user: dict[str, Any],
        portfolio_id: int,
        space_id: int,
    ) -> dict[str, Any]:
        company, _ = CompanyPortfolioSpaceService._get_context(
            session,
            user=user,
            portfolio_id=portfolio_id,
            require_editable=True,
        )

        before = repository.find_portfolio_space(
            session,
            portfolio_id=portfolio_id,
            space_id=space_id,
        )

        try:
            PortfolioSpaceCoreService.delete_space(
                session,
                portfolio_id=portfolio_id,
                space_id=space_id,
            )

            AuditService.record(
                session=session,
                admin_user_id=None,
                action_type="portfolio.space.deleted",
                target_type="portfolio_space",
                target_id=space_id,
                before_data=json_safe(before or {}),
                after_data={"deleted": True},
                reason="업체 포트폴리오 공간 삭제",
                metadata={
                    "source": "company_portfolio",
                    "portfolio_id": portfolio_id,
                    "company_id": company["id"],
                    "actor_user_id": user["id"],
                },
            )

            session.commit()

        except Exception:
            session.rollback()
            raise

        return {
            "portfolio_id": portfolio_id,
            "space_id": space_id,
            "message": "포트폴리오 공간이 삭제되었습니다.",
        }

